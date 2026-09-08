# VPS deployment

PR #14 packages the validated PR #13 refresh as a short-lived Docker workload scheduled by systemd on the Hostinger VPS.

## Design

- `docker compose run --rm refresh` starts one isolated refresh container and exits when the Prefect flow finishes.
- The image contains application/dbt code but no credentials or `.env` files.
- `/opt/nh-property-intelligence/.env` contains non-secret Snowflake identifiers.
- `/opt/nh-property-intelligence/.env.secrets` contains runtime secrets provisioned from Bitwarden and must be mode `0600` and readable only by the deployment account.
- `deployment/run-refresh.sh` uses `flock` to prevent overlapping refreshes and records the last outcome in `deployment/last-run.status`.
- `nhpi-refresh.service` sends stdout/stderr to the normal systemd journal and preserves the container exit code.
- `nhpi-refresh.timer` runs monthly on the fifth day around 06:00 America/New_York, with up to 15 minutes of jitter and `Persistent=true` so a missed run fires after the VPS returns.

A dedicated Prefect server is intentionally unnecessary at this scale. Prefect still provides task states, retries, and structured flow logs inside each short-lived run.

## Initial VPS setup

Expected checkout: `/opt/nh-property-intelligence`.

1. Create a dedicated non-root deployment user (example: `nhpi`) and grant only the Docker access needed by this host.
2. Clone the repository to `/opt/nh-property-intelligence` and check out the desired release/main commit.
3. Copy `.env.example` to `.env` and fill the non-secret Snowflake account/user identifiers.
4. Provision `.env.secrets` from Bitwarden outside Git. Example contents:

   ```text
   SNOWFLAKE_PASSWORD=<role-restricted PAT or password>
   CENSUS_API_KEY=<optional Census key>
   ```

   Then run `chmod 600 .env .env.secrets` and ensure they are owned by the deployment user.
5. Build without passing secrets into the Docker build context:

   ```bash
   docker compose build refresh
   ```

6. Run one manual acceptance refresh:

   ```bash
   bash deployment/run-refresh.sh
   cat deployment/last-run.status
   ```

7. Verify fresh RAW ingestion timestamps and the `ANALYTICS.MART_TOWN_SCORECARD` rebuild in Snowflake.
8. Install the systemd units:

   ```bash
   sudo cp deployment/systemd/nhpi-refresh.service /etc/systemd/system/
   sudo cp deployment/systemd/nhpi-refresh.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now nhpi-refresh.timer
   systemctl list-timers nhpi-refresh.timer
   ```

## Secret rotation

Bitwarden remains the source of truth. Rotation is an explicit provisioning action: retrieve the updated secret locally/on the trusted VPS session, rewrite `.env.secrets`, restore mode `0600`, then run one manual refresh. The timer never requires an unlocked Bitwarden session and no Bitwarden master password/session token is persisted.

Do not put secrets in Dockerfiles, Compose YAML, GitHub Actions, command arguments, images, or Git.

## Operations

Last runner status:

```bash
cat /opt/nh-property-intelligence/deployment/last-run.status
```

Service logs:

```bash
journalctl -u nhpi-refresh.service --since '7 days ago'
```

Manual run:

```bash
sudo -u nhpi /usr/bin/bash /opt/nh-property-intelligence/deployment/run-refresh.sh
```

If a run is already active, a second invocation exits successfully with `status=skipped_overlap` instead of starting another warehouse refresh.

A failed container returns nonzero, making the systemd service failed and visible through `systemctl status`/`journalctl`. External notification integrations are intentionally deferred; systemd/journald and the status file are the PR #14 failure-visibility baseline.

## Acceptance gate

Before PR #14 is considered operationally complete, validate on the VPS or a VPS-equivalent Linux Docker host:

- container builds successfully;
- manual `run-refresh.sh` completes;
- Census/DRA/FHFA RAW ingestion timestamps advance;
- `dbt build` succeeds through the Prefect flow;
- `MART_TOWN_SCORECARD` rebuilds;
- a held lock causes a second runner to skip without starting another refresh;
- systemd service exit status and journal output reflect success/failure;
- timer is enabled with the expected next trigger.
