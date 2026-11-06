# Creator evidence contract (source-only, not activated)

This follow-up preserves the canonical archive policy and main-only dispatch
binding. It does not implement issue #18's PBIP, invoke Codex, configure a key,
merge a workflow, deploy Alfred, or authorize a paid run.

## Three separate jobs

1. **codex** has repository-read permissions and the dedicated model credential
   supplied to the pinned official action. Its supported `output-file` input
   writes the final report to runner temporary storage. Source is packed under
   the existing suffix/path/budget policy. The separate report is explicitly
   `codex_self_report`, never trusted test evidence. Missing, oversized (>8 KiB),
   linked or non-UTF-8 reports are omitted rather than interpreted or truncated.
2. **validate** starts a fresh runner with repository-read access only and no
   model secret or repository-write permission. It uses the dispatch commit's
   reviewed Python helper. It validates paths/archive budgets, detects at least
   one changed/new file against that checkout, parses JSON-family source, and
   records per-file SHA-256 hashes. It never executes generated files, installs
   generated dependencies, loads generated tests, or interprets M/TMDL. The
   exact validated bundle bytes pass onward by immutable artifact ID and hash.
3. **publish** starts another fresh runner without a model credential. It freezes
   its reviewed helpers from the pinned checkout before artifact handling or PR
   creation can change the worktree. It verifies the bundle hash and path policy,
   then publishes only a draft PR if both earlier jobs succeeded. It uses
   create-pull-request's number, URL, head SHA and operation outputs, not a
   model-provided URL. A closed/no-op action is not called a newly created draft.

All checkouts use the same dispatch `github.sha`. All three jobs require main
and literal issue `18`. The publisher's `always()` condition allows failed-run
results; its PR step additionally requires successful generation and validation.
The suffix policy is unchanged. Deleted files are not transported by this MVP.

## What the trusted checks actually mean

- `archive_policy`: the existing bounded zip/path/file-type policy accepted the
  bundle. The input zip itself is additionally limited to 4 MiB.
- `nonempty_changes`: at least one transported file is new or differs from the
  pinned checkout. This is not evidence that the requested feature is complete.
- `json_syntax`: `.json`, `.pbip`, `.pbir` and `.pbism` payloads decode as UTF-8
  JSON without duplicate keys or NaN/Infinity. No schema compatibility, external
  reference, Power BI Desktop, TMDL/M semantic or business-metric validation is
  claimed. This check is vacuously successful if the bundle contains no JSON.

A passing validator is **not PBIP acceptance**. The limitations are mandatory.
Normal downstream PR CI is not assumed: GitHub suppresses ordinary push/PR
workflow events caused by `GITHUB_TOKEN`. No broader credential is requested to
work around this. Alfred/owner QA still has to inspect the generated deliverable.
The API key's billing is separate from any ChatGPT subscription allowance.

## Result schema v1

Artifact name: `creator-result-<run_id>-<run_attempt>`.
Archive contents: exactly one regular `result.json`, at most 16,384 bytes.
JSON has exactly these fields:

- `schema_version`: integer `1`.
- `task`: `NHPI-18`.
- `repository`: `thomasGardner19/nh-property-intelligence`.
- `run_id`, `run_attempt`: positive integers.
- `source_sha`: 40 lowercase hexadecimal characters, the dispatched main commit.
- `generation`: `success`, `failure`, `cancelled`, `skipped`, or `unknown`.
- `validation`: `pass`, `fail`, or `not_run`.
- `publication`: `draft_created`, `no_changes`, `failed`, or `not_run`.
- `bundle_sha256`: 64 lowercase hex characters only if validation passed;
  otherwise null.
- `checks`: exactly `archive_policy`, `nonempty_changes`, `json_syntax`, each
  `pass`, `fail`, or `not_run`.
- `pr`: null, or exactly `number` (positive integer), `url` (the fixed NHPI
  `/pull/<number>` URL), `head_sha` (40 lowercase hex).
- `self_report_available`: boolean, indicates an upload ID was returned. The
  report's contents and claims remain untrusted.
- `limitations`: exactly `DESKTOP_NOT_RUN`, `GENERATED_CODE_NOT_EXECUTED`,
  `DOWNSTREAM_CI_NOT_ASSUMED`, in that order.
- `failure_code`: `NONE`, `GENERATION_FAILED`, `VALIDATION_FAILED`,
  `PUBLICATION_FAILED`, or `NO_CHANGES`.

Consistency rules:

- Generation other than success requires a skipped validator and therefore
  validation/checks `not_run`, publication `not_run`, null PR/bundle and
  `GENERATION_FAILED`.
- Validation `pass` requires successful generation and validator job, all three
  checks `pass`, and a bundle digest. A failed/cancelled validator can retain
  completed check results, but cannot promote validation to pass.
- Validation not passed implies null PR/bundle, publication `not_run`, and
  `VALIDATION_FAILED` when generation succeeded. `not_run` has all checks
  `not_run`. A skipped validator after successful generation is a failed pipeline,
  not successful publication.
- Only passed validation permits publication. `draft_created` has a PR and
  `NONE`; `no_changes` has no PR and `NO_CHANGES`; `failed` has no PR and
  `PUBLICATION_FAILED`. Prior validation remains visible after publication fails.

## Provenance: artifact names are not trust boundaries

The generator and validator can produce artifacts in the same run. An attacker
must not be able to label an arbitrary upload `creator-result-*` and have Alfred
accept it. A matching artifact name alone, or a digest inside that artifact, is
insufficient.

The trusted publisher has the fixed GitHub job display name:

`Publish reviewed Creator result`

After the result builder writes exact JSON bytes, it emits their SHA-256. After
upload-artifact succeeds and returns an artifact ID, a final no-op step has this
exact name:

`Creator result artifact <artifact-id> sha256 <result-json-sha256>`

Both outputs come from trusted steps on the publisher runner. The consumer must
read GitHub's jobs/steps API for the exact run attempt, require a unique fixed
publisher job and successful anchor step, then bind the anchored artifact ID,
exact artifact name, run identity, source SHA and digest of actual JSON bytes.
The publisher job can have a failed conclusion when an earlier publication step
failed; the anchor step itself must have completed successfully. Validate the
known workflow path/ref and dispatch identity, not just a familiar job name.

Generation can forge its own report, upload an artifact with a misleading name,
fail uploads through name collisions, or tamper with its own runner after model
execution. It cannot add a successful step to the different trusted publisher
job. Collisions, missing outputs, missing/duplicate anchors or mismatched identity
must fail closed. The validator passes its own immutable artifact ID to the
publisher; the publisher never selects the validated bundle by a name suggested
by generated content. All downloads require a nonempty numeric artifact ID.

This is workflow provenance, **not cryptographic attestation**. It trusts GitHub,
reviewed workflow/source, pinned actions, runner isolation and repository owners.
Compromised repository-write authority or an unreviewed main workflow is outside
this mechanism's protection. The bridge's independent verification is required
before this can be called end-to-end trusted evidence.

## Failure, retention and access

Collection/result/upload use `always()` where useful, but cancellation, runner
loss, checkout failure or artifact service failure can still prevent a result.
The bridge must return missing/invalid/expired evidence alongside actual run
state; it must not synthesize successful checks, a PR, or a failure packet.
Never resubmit an uncertain dispatch automatically.

Artifacts request 30-day retention, subject to repository policy. This is a
bounded durable record, not permanent storage. Successful PR bodies also retain
the run link and limited trusted-check summary. Raw narrative is separate from
machine-readable evidence. No model report enters a shell command or trusted
check result. GitHub Actions read permission suffices for artifact/jobs reads;
this design does not add PR or contents write permissions to Alfred's bridge.
The existing dispatch credential still needs Actions write for submission.

## Offline verification

Use the pinned test requirement and run:

```sh
python3 -m pip install -r tests/creator/requirements.txt
python3 -I -B -m unittest discover -s tests/creator -p 'test_*.py' -v
```

Tests are synthetic and include failed generation, malformed/oversized bundles,
changed/no-change source, JSON errors, self-report isolation, bundle integrity,
publication failures, exact schema, fixed publisher anchor, immutable-ID handoff,
permissions and pinned action contracts. These are local source tests, not proof
of live Actions, credential configuration, a Codex run or Power BI compatibility.
