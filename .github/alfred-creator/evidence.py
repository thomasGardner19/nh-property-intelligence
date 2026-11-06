"""Trusted, dependency-free Creator evidence helpers. Never execute generated code."""
from __future__ import annotations

import hashlib
import http.client
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("artifact_policy", HERE / "pack_artifact.py")
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)
REPOSITORY = "thomasGardner19/nh-property-intelligence"
CHECKS = ("archive_policy", "nonempty_changes", "json_syntax")
LIMITATIONS = ["DESKTOP_NOT_RUN", "GENERATED_CODE_NOT_EXECUTED", "DOWNSTREAM_CI_NOT_ASSUMED"]
MAX_RESULT = 16 * 1024
MAX_ARCHIVE = 4 * 1024 * 1024
MAX_REPORT = 8 * 1024
MAX_PR_RESPONSE = 64 * 1024
JSON_SUFFIXES = {".json", ".pbip", ".pbir", ".pbism"}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def bounded_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1
                and 0 < meta.st_size <= limit, "INVALID_FILE")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(limit + 1)
        require(0 < len(data) <= limit, "FILE_BUDGET")
        return data
    finally:
        os.close(fd)


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "DUPLICATE_JSON_KEY")
            out[key] = value
        return out

    def constant(_):
        raise ValueError("NONFINITE_JSON")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=constant)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, data, limit):
    raw = (json.dumps(data, sort_keys=True, separators=(",", ":"),
                      allow_nan=False) + "\n").encode()
    require(len(raw) <= limit, "OUTPUT_BUDGET")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return digest(raw)


def outputs(values):
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                require(re.fullmatch(r"[a-z][a-z0-9_]*", key) is not None
                        and re.fullmatch(r"[a-z0-9_]+", str(value)) is not None,
                        "INVALID_OUTPUT")
                handle.write(f"{key}={value}\n")


def validate(bundle, root, report):
    checks = dict.fromkeys(CHECKS, "not_run")
    manifest = []
    bundle_hash = None
    passed = False
    try:
        raw = bounded_read(bundle, MAX_ARCHIVE)
        bundle_hash = digest(raw)
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            # Read the very bytes whose digest was recorded, not a later file.
            archive = staging / "input.zip"
            archive.write_bytes(raw)
            extracted = staging / "source"
            extracted.mkdir()
            POLICY.unpack(archive, extracted)
            checks["archive_policy"] = "pass"
            changed = False
            for source in sorted((extracted / "powerbi").rglob("*")):
                if not source.is_file():
                    continue
                name = source.relative_to(extracted).as_posix()
                data = source.read_bytes()
                manifest.append({"path": name, "sha256": digest(data), "bytes": len(data)})
                original = root / name
                # Trusted checkout supplies baseline only; symlinks are not followed.
                if original.is_symlink() or not original.is_file() or original.read_bytes() != data:
                    changed = True
            checks["nonempty_changes"] = "pass" if changed else "fail"
            checks["json_syntax"] = "pass"
            for entry in manifest:
                source = extracted / entry["path"]
                if source.suffix.lower() in JSON_SUFFIXES:
                    strict_json(source.read_bytes())
            passed = changed
    except Exception:  # noqa: BLE001 - untrusted archive errors must not expose raw content
        # Preserve fixed statuses only; never expose generated text in errors.
        if checks["archive_policy"] == "not_run":
            checks["archive_policy"] = "fail"
        elif checks["json_syntax"] == "pass":
            checks["json_syntax"] = "fail"
        else:
            checks["nonempty_changes"] = "fail"
    status = "pass" if passed else "fail"
    document = {"validation": status, "bundle_sha256": bundle_hash,
                "checks": checks, "manifest": manifest, "limitations": LIMITATIONS}
    write_json(report, document, 64 * 1024)
    outputs({"validation": status, **checks})
    if bundle_hash:
        outputs({"bundle_sha256": bundle_hash})
    return passed


def apply_validated(bundle, root, expected):
    require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None, "BAD_DIGEST")
    raw = bounded_read(bundle, MAX_ARCHIVE)
    require(digest(raw) == expected, "BUNDLE_DIGEST_MISMATCH")
    with tempfile.TemporaryDirectory() as directory:
        frozen = Path(directory) / "bundle.zip"
        frozen.write_bytes(raw)
        POLICY.unpack(frozen, root)


def collect_report(source, destination):
    # Narrative is explicitly untrusted even when the source file was written
    # by the action. It is never parsed as test results or shell instructions.
    try:
        raw = bounded_read(source, MAX_REPORT)
        text = raw.decode("utf-8")
    except Exception:  # noqa: BLE001 - malformed model narrative is simply unavailable
        return False
    write_json(destination, {"trust": "codex_self_report", "text": text}, 64 * 1024)
    outputs({"report_available": "true"})
    return True


def identity(env):
    require(env.get("GITHUB_REPOSITORY") == REPOSITORY, "BAD_REPOSITORY")
    require(env.get("GITHUB_REF") == "refs/heads/main", "BAD_REF")
    require(env.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "BAD_EVENT")
    sha = env.get("GITHUB_SHA", "")
    require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "BAD_SOURCE_SHA")
    values = []
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        value = env.get(key, "")
        require(re.fullmatch(r"[1-9][0-9]{0,15}", value) is not None, "BAD_RUN_IDENTITY")
        values.append(int(value))
    return {"schema_version": 1, "task": "NHPI-18", "repository": REPOSITORY,
            "run_id": values[0], "run_attempt": values[1], "source_sha": sha}


def verify_pr_document(document, env):
    """Verify an actual draft snapshot, never infer draft state from action output."""
    run = identity(env)
    number = env.get("PR_NUMBER", "")
    head_sha = env.get("PR_HEAD_SHA", "")
    require(re.fullmatch(r"[1-9][0-9]{0,9}", number) is not None, "BAD_PR_NUMBER")
    require(re.fullmatch(r"[0-9a-f]{40}", head_sha) is not None, "BAD_PR_SHA")
    url = f"https://github.com/{REPOSITORY}/pull/{number}"
    branch = f"alfred/creator-issue-18-{run['run_id']}-{run['run_attempt']}"
    require(type(document) is dict, "BAD_PR_DOCUMENT")
    require(type(document.get("number")) is int and document["number"] == int(number)
            and document.get("html_url") == url and env.get("PR_URL") == url,
            "PR_IDENTITY_MISMATCH")
    require(document.get("draft") is True and document.get("state") == "open"
            and document.get("merged") is False and document.get("merged_at") is None,
            "PR_NOT_OPEN_DRAFT")
    base, head = document.get("base"), document.get("head")
    require(type(base) is dict and type(head) is dict, "BAD_PR_REFS")
    require(type(base.get("repo")) is dict and type(head.get("repo")) is dict
            and base["repo"].get("full_name") == REPOSITORY
            and head["repo"].get("full_name") == REPOSITORY, "PR_REPOSITORY_MISMATCH")
    # Refuse a rebase onto a newer main commit: trusted checks used source_sha.
    require(base.get("ref") == "main" and base.get("sha") == run["source_sha"]
            and head.get("ref") == branch and head.get("sha") == head_sha,
            "PR_REF_MISMATCH")


def verify_pr(env):
    """Fixed read-only GitHub GET; do not follow redirects or mutate draft state."""
    identity(env)
    number = env.get("PR_NUMBER", "")
    require(re.fullmatch(r"[1-9][0-9]{0,9}", number) is not None, "BAD_PR_NUMBER")
    token = env.get("GH_TOKEN", "")
    require(bool(token), "MISSING_READ_TOKEN")
    con = http.client.HTTPSConnection("api.github.com", timeout=20)
    try:
        con.request("GET", f"/repos/{REPOSITORY}/pulls/{number}", headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nhpi-creator-evidence/1"})
        response = con.getresponse()
        require(response.status == 200, "PR_READ_FAILED")
        raw = response.read(MAX_PR_RESPONSE + 1)
        require(0 < len(raw) <= MAX_PR_RESPONSE, "PR_RESPONSE_BUDGET")
    finally:
        con.close()
    verify_pr_document(strict_json(raw), env)
    outputs({"draft_verified": "true"})


def result_document(env):
    doc = identity(env)
    generation = env.get("GENERATION", "unknown")
    require(generation in ("success", "failure", "cancelled", "skipped", "unknown"),
            "BAD_GENERATION")
    job = env.get("VALIDATOR_JOB", "skipped")
    require(job in ("success", "failure", "cancelled", "skipped"), "BAD_VALIDATOR_JOB")
    require(generation == "success" or job == "skipped", "INCONSISTENT_JOBS")
    validation = "not_run" if job == "skipped" else "fail"
    checks = dict.fromkeys(CHECKS, "not_run")
    bundle_hash = None
    if job != "skipped":
        for key in CHECKS:
            value = env.get(key.upper(), "not_run") or "not_run"
            require(value in ("pass", "fail", "not_run"), "BAD_CHECK")
            checks[key] = value
    if generation == "success" and job == "success":
        require(all(v == "pass" for v in checks.values()), "MISSING_VALIDATION")
        bundle_hash = env.get("BUNDLE_SHA256", "")
        require(re.fullmatch(r"[0-9a-f]{64}", bundle_hash) is not None, "BAD_BUNDLE_SHA")
        validation = "pass"
    publication, pr = "not_run", None
    failure = "NONE"
    if generation != "success":
        failure = "GENERATION_FAILED"
    elif validation != "pass":
        failure = "VALIDATION_FAILED"
    else:
        publication = "failed"
        failure = "PUBLICATION_FAILED"
        if env.get("PR_OUTCOME") == "success":
            number = env.get("PR_NUMBER", "")
            url = env.get("PR_URL", "")
            head = env.get("PR_HEAD_SHA", "")
            operation = env.get("PR_OPERATION", "")
            require(operation in ("", "none", "created", "updated", "closed"), "BAD_PR_OPERATION")
            # The pinned action defaults to 'none' and emits a head SHA even
            # when it has no PR. Only number/URL indicate retained PR identity.
            if operation == "closed" or (operation in ("", "none") and not (number or url)):
                publication, failure = "no_changes", "NO_CHANGES"
            elif (env.get("PR_VERIFY_OUTCOME") == "success"
                  and env.get("PR_DRAFT_VERIFIED") == "true"):
                require(re.fullmatch(r"[1-9][0-9]{0,9}", number) is not None,
                        "BAD_PR_NUMBER")
                require(url == f"https://github.com/{REPOSITORY}/pull/{number}", "BAD_PR_URL")
                require(re.fullmatch(r"[0-9a-f]{40}", head) is not None, "BAD_PR_SHA")
                pr = {"number": int(number), "url": url, "head_sha": head}
                # Both are snapshots; only the action's created operation is
                # evidence of creation rather than a verified existing draft.
                publication = "draft_created" if operation == "created" else "draft_verified"
                failure = "NONE"
    report_id = env.get("REPORT_ARTIFACT_ID", "")
    report_available = bool(re.fullmatch(r"[1-9][0-9]{0,15}", report_id))
    doc.update(generation=generation, validation=validation, publication=publication,
               bundle_sha256=bundle_hash, checks=checks, pr=pr,
               self_report_available=report_available, limitations=LIMITATIONS,
               failure_code=failure)
    return doc


def main():
    try:
        mode = sys.argv[1]
        if mode == "validate" and len(sys.argv) == 5:
            return 0 if validate(*map(Path, sys.argv[2:])) else 1
        if mode == "apply" and len(sys.argv) == 5:
            apply_validated(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
        elif mode == "report" and len(sys.argv) == 4:
            collect_report(Path(sys.argv[2]), Path(sys.argv[3]))
        elif mode == "verify-pr" and len(sys.argv) == 2:
            verify_pr(os.environ)
        elif mode == "result" and len(sys.argv) == 3:
            sha = write_json(Path(sys.argv[2]), result_document(os.environ), MAX_RESULT)
            outputs({"sha256": sha})
        else:
            raise ValueError("BAD_ARGUMENTS")
        return 0
    except Exception:  # noqa: BLE001 - CLI trust boundary returns only a fixed error code
        print("REFUSED_CREATOR_EVIDENCE", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
