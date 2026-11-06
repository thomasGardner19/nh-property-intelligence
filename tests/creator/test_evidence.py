"""Synthetic evidence and handoff tests. No model, network, or generated code execution."""
import copy
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("evidence", ROOT / ".github/alfred-creator/evidence.py")
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)


class EvidenceTests(unittest.TestCase):
    def env(self, **changes):
        value = {"GITHUB_REPOSITORY": E.REPOSITORY, "GITHUB_REF": "refs/heads/main",
                 "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "a" * 40,
                 "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
                 "GENERATION": "success", "VALIDATOR_JOB": "success",
                 "BUNDLE_SHA256": "b" * 64, "PR_OUTCOME": "success", "PR_OPERATION": "created",
                 "PR_NUMBER": "42", "PR_URL": f"https://github.com/{E.REPOSITORY}/pull/42",
                 "PR_HEAD_SHA": "c" * 40, "REPORT_ARTIFACT_ID": "456",
                 "PR_VERIFY_OUTCOME": "success", "PR_DRAFT_VERIFIED": "true",
                 **{key.upper(): "pass" for key in E.CHECKS}}
        value.update(changes)
        return value

    def pr_document(self):
        return {"number": 42, "html_url": f"https://github.com/{E.REPOSITORY}/pull/42",
                "draft": True, "state": "open", "merged": False, "merged_at": None,
                "base": {"ref": "main", "sha": "a" * 40,
                         "repo": {"full_name": E.REPOSITORY}},
                "head": {"ref": "alfred/creator-issue-18-123-2", "sha": "c" * 40,
                         "repo": {"full_name": E.REPOSITORY}}}

    def test_actual_draft_snapshot_requires_exact_identity_and_refs(self):
        E.verify_pr_document(self.pr_document(), self.env())
        cases = [(('draft',), False), (('draft',), 1), (('state',), 'closed'),
                 (('merged',), True), (('merged_at',), 'timestamp'),
                 (('number',), 43), (('number',), True),
                 (('html_url',), 'https://evil.test/pull/42'),
                 (('base', 'ref'), 'feature'), (('base', 'sha'), 'd' * 40),
                 (('base', 'repo', 'full_name'), 'other/repo'),
                 (('head', 'ref'), 'alfred/creator-issue-18-123-1'),
                 (('head', 'sha'), 'd' * 40), (('head', 'repo', 'full_name'), 'other/repo')]
        for keys, value in cases:
            with self.subTest(keys=keys, value=value):
                document = copy.deepcopy(self.pr_document())
                target = document
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                with self.assertRaises(ValueError):
                    E.verify_pr_document(document, self.env())

    def test_actual_draft_get_is_fixed_read_only_bounded_and_closes(self):
        raw = json.dumps(self.pr_document()).encode()
        response = mock.Mock(status=200)
        response.read.return_value = raw
        connection = mock.Mock()
        connection.getresponse.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'outputs'
            with (
                mock.patch.object(E.http.client, 'HTTPSConnection', return_value=connection) as factory,
                mock.patch.dict(os.environ, {'GITHUB_OUTPUT': str(output)}),
            ):
                E.verify_pr(self.env(GH_TOKEN='SYNTHETIC_ONLY'))
            self.assertEqual(output.read_text(), 'draft_verified=true\n')
        factory.assert_called_once_with('api.github.com', timeout=20)
        self.assertEqual(connection.request.call_args.args,
                         ('GET', f'/repos/{E.REPOSITORY}/pulls/42'))
        response.read.assert_called_once_with(E.MAX_PR_RESPONSE + 1)
        connection.close.assert_called_once_with()

    def test_draft_http_errors_redirects_oversize_and_transport_fail_closed(self):
        cases = [(302, b'{}'), (403, b'{}'), (200, b'x' * (E.MAX_PR_RESPONSE + 1)),
                 (200, b'[]'), (200, b'not json')]
        for status, raw in cases:
            with self.subTest(status=status, size=len(raw)):
                response = mock.Mock(status=status)
                response.read.return_value = raw
                connection = mock.Mock()
                connection.getresponse.return_value = response
                with (
                    mock.patch.object(E.http.client, 'HTTPSConnection', return_value=connection),
                    self.assertRaises(ValueError),
                ):
                    E.verify_pr(self.env(GH_TOKEN='SYNTHETIC_ONLY'))
                connection.close.assert_called_once_with()
                self.assertEqual(connection.request.call_count, 1)
        connection = mock.Mock()
        connection.getresponse.side_effect = TimeoutError('synthetic')
        with (
            mock.patch.object(E.http.client, 'HTTPSConnection', return_value=connection),
            self.assertRaises(TimeoutError),
        ):
            E.verify_pr(self.env(GH_TOKEN='SYNTHETIC_ONLY'))
        connection.close.assert_called_once_with()

    def test_created_updated_and_retained_pr_require_draft_read_success(self):
        for operation in ('created', 'updated', 'none', ''):
            for outcome, verified in [('failure', ''), ('skipped', ''), ('success', ''),
                                      ('success', 'false'), ('', 'true')]:
                with self.subTest(operation=operation, outcome=outcome, verified=verified):
                    doc = E.result_document(self.env(PR_OPERATION=operation,
                        PR_VERIFY_OUTCOME=outcome, PR_DRAFT_VERIFIED=verified))
                    self.assertEqual(doc['publication'], 'failed')
                    self.assertEqual(doc['failure_code'], 'PUBLICATION_FAILED')
                    self.assertEqual(doc['validation'], 'pass')
                    self.assertIsNone(doc['pr'])
            doc = E.result_document(self.env(PR_OPERATION=operation))
            expected = 'draft_created' if operation == 'created' else 'draft_verified'
            self.assertEqual(doc['publication'], expected)
            self.assertEqual(doc['pr']['number'], 42)
            self.assertEqual(doc['failure_code'], 'NONE')

    def bundle(self, root, entries):
        path = root / "bundle.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name, value in entries:
                archive.writestr(name, value)
        return path

    def test_valid_bundle_manifest_and_trusted_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self.bundle(root, [("powerbi/report.pbir", '{"version":"4.0"}')])
            report = root / "validation.json"
            self.assertTrue(E.validate(bundle, root, report))
            doc = json.loads(report.read_text())
            self.assertEqual(doc["checks"], dict.fromkeys(E.CHECKS, "pass"))
            self.assertEqual(doc["bundle_sha256"], hashlib.sha256(bundle.read_bytes()).hexdigest())
            self.assertEqual(doc["manifest"][0]["path"], "powerbi/report.pbir")
            self.assertFalse((root / "powerbi").exists())

    def test_no_change_bundle_fails_without_claiming_json_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "powerbi").mkdir()
            (root / "powerbi/data.json").write_text('{}')
            bundle = self.bundle(root, [("powerbi/data.json", '{}')])
            report = root / "validation.json"
            self.assertFalse(E.validate(bundle, root, report))
            self.assertEqual(json.loads(report.read_text())["checks"],
                             {"archive_policy": "pass", "nonempty_changes": "fail", "json_syntax": "pass"})

    def test_invalid_json_duplicate_and_nonfinite_are_failed(self):
        for text in ('{', '{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '\xff'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                bundle = self.bundle(root, [("powerbi/data.json", text.encode('latin1'))])
                report = root / "validation.json"
                self.assertFalse(E.validate(bundle, root, report))
                self.assertEqual(json.loads(report.read_text())["checks"]["json_syntax"], "fail")

    def test_alias_bad_extension_and_traversal_fail_archive_check(self):
        for path in ('powerbi/./data.json', '../data.json', 'powerbi/run.py'):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                bundle = self.bundle(root, [(path, '{}')])
                report = root / "validation.json"
                self.assertFalse(E.validate(bundle, root, report))
                checks = json.loads(report.read_text())["checks"]
                self.assertEqual(checks, {"archive_policy": "fail", "nonempty_changes": "not_run", "json_syntax": "not_run"})

    def test_missing_and_oversized_bundle_leave_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, report = root / "bundle.zip", root / "validation.json"
            self.assertFalse(E.validate(bundle, root, report))
            with bundle.open('wb') as handle:
                handle.truncate(E.MAX_ARCHIVE + 1)
            self.assertFalse(E.validate(bundle, root, report))
            self.assertEqual(json.loads(report.read_text())["validation"], "fail")

    def test_forged_deflate_size_fails_validation_before_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "forged.zip"
            with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("powerbi/data.json", b"{}" + b" " * (16 * 1024 * 1024))
            raw = bytearray(bundle.read_bytes())
            central = raw.index(b"PK\x01\x02")
            for offset in (14, central + 16):
                struct.pack_into("<I", raw, offset, zlib.crc32(b"{}"))
            for offset in (22, central + 24):
                struct.pack_into("<I", raw, offset, 2)
            bundle.write_bytes(raw)
            self.assertLess(len(raw), 32 * 1024)
            report = root / "validation.json"
            self.assertFalse(E.validate(bundle, root, report))
            doc = json.loads(report.read_text())
            self.assertEqual(doc["validation"], "fail")
            self.assertEqual(doc["checks"], {"archive_policy": "fail",
                             "nonempty_changes": "not_run", "json_syntax": "not_run"})
            self.assertEqual(doc["manifest"], [])
            self.assertFalse((root / "powerbi").exists())

    def test_generated_m_content_is_never_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Deliberately not meaningful M; this layer promises only JSON syntax.
            bundle = self.bundle(root, [("powerbi/query.m", "raise Exception('NEVER EXECUTE')")])
            self.assertTrue(E.validate(bundle, root, root / "validation.json"))
            self.assertIn("GENERATED_CODE_NOT_EXECUTED", json.loads((root / "validation.json").read_text())["limitations"])

    def test_apply_requires_exact_validated_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self.bundle(root, [("powerbi/data.json", '{}')])
            sha = E.digest(bundle.read_bytes())
            with self.assertRaisesRegex(ValueError, "BUNDLE_DIGEST_MISMATCH"):
                E.apply_validated(bundle, root, '0' * 64)
            self.assertFalse((root / 'powerbi').exists())
            E.apply_validated(bundle, root, sha)
            self.assertEqual((root / 'powerbi/data.json').read_text(), '{}')

    def test_apply_rechecks_path_policy_even_for_matching_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = self.bundle(root, [("powerbi/../outside.json", '{}')])
            with self.assertRaises(ValueError):
                E.apply_validated(bundle, root, E.digest(bundle.read_bytes()))
            self.assertFalse((root / 'outside.json').exists())

    def test_report_is_separately_labeled_untrusted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'raw.txt'
            source.write_text('All tests passed! $(touch /tmp/not-executed)')
            self.assertTrue(E.collect_report(source, root / 'report.json'))
            self.assertEqual(json.loads((root / 'report.json').read_text()),
                             {"trust": "codex_self_report", "text": source.read_text()})

    def test_missing_oversized_symlink_report_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, result = root / 'raw.txt', root / 'report.json'
            self.assertFalse(E.collect_report(source, result))
            source.write_text('x' * (E.MAX_REPORT + 1))
            self.assertFalse(E.collect_report(source, result))
            source.unlink()
            source.symlink_to(root / 'missing')
            self.assertFalse(E.collect_report(source, result))
            self.assertFalse(result.exists())

    def test_result_success_exact_contract_and_budget(self):
        doc = E.result_document(self.env())
        self.assertEqual(set(doc), {'schema_version', 'task', 'repository', 'run_id',
                         'run_attempt', 'source_sha', 'generation', 'validation',
                         'publication', 'bundle_sha256', 'checks', 'pr',
                         'self_report_available', 'limitations', 'failure_code'})
        self.assertEqual(doc['publication'], 'draft_created')
        self.assertEqual(doc['validation'], 'pass')
        self.assertEqual(doc['failure_code'], 'NONE')
        self.assertLess(len(json.dumps(doc).encode()), E.MAX_RESULT)

    def test_result_generation_failures_need_no_manifest(self):
        for state in ('failure', 'cancelled', 'skipped', 'unknown'):
            with self.subTest(state=state):
                doc = E.result_document(self.env(GENERATION=state, VALIDATOR_JOB='skipped'))
                self.assertEqual(doc['failure_code'], 'GENERATION_FAILED')
                self.assertEqual(doc['validation'], 'not_run')
                self.assertEqual(doc['checks'], dict.fromkeys(E.CHECKS, 'not_run'))
                self.assertEqual(doc['publication'], 'not_run')
                self.assertIsNone(doc['pr'])
                self.assertIsNone(doc['bundle_sha256'])

    def test_result_validation_failure_blocks_publication(self):
        doc = E.result_document(self.env(VALIDATOR_JOB='failure', JSON_SYNTAX='fail'))
        self.assertEqual(doc['failure_code'], 'VALIDATION_FAILED')
        self.assertEqual(doc['publication'], 'not_run')
        self.assertIsNone(doc['pr'])
        self.assertIsNone(doc['bundle_sha256'])

    def test_result_publication_failure_preserves_validation(self):
        for state in ('failure', 'cancelled', 'skipped', ''):
            with self.subTest(state=state):
                doc = E.result_document(self.env(PR_OUTCOME=state))
                self.assertEqual(doc['validation'], 'pass')
                self.assertEqual(doc['publication'], 'failed')
                self.assertEqual(doc['failure_code'], 'PUBLICATION_FAILED')
                self.assertIsNone(doc['pr'])

    def test_result_no_changes_is_not_draft_created(self):
        doc = E.result_document(self.env(PR_NUMBER='', PR_URL='', PR_HEAD_SHA='', PR_OPERATION=''))
        self.assertEqual(doc['publication'], 'no_changes')
        self.assertEqual(doc['failure_code'], 'NO_CHANGES')
        self.assertIsNone(doc['pr'])

    def test_pinned_action_none_without_pr_but_with_head_sha_is_no_changes(self):
        for operation in ('none', ''):
            with self.subTest(operation=operation):
                doc = E.result_document(self.env(PR_OPERATION=operation, PR_NUMBER='',
                    PR_URL='', PR_HEAD_SHA='c' * 40, PR_VERIFY_OUTCOME='skipped',
                    PR_DRAFT_VERIFIED=''))
                self.assertEqual(doc['publication'], 'no_changes')
                self.assertEqual(doc['failure_code'], 'NO_CHANGES')
                self.assertIsNone(doc['pr'])

    def test_pinned_action_none_with_retained_pr_requires_actual_verification(self):
        doc = E.result_document(self.env(PR_OPERATION='none'))
        self.assertEqual(doc['publication'], 'draft_verified')
        self.assertEqual(doc['pr']['number'], 42)
        self.assertEqual(doc['failure_code'], 'NONE')
        doc = E.result_document(self.env(PR_OPERATION='none', PR_VERIFY_OUTCOME='failure'))
        self.assertEqual(doc['publication'], 'failed')
        self.assertIsNone(doc['pr'])

    def test_partial_retained_identity_fails_verification(self):
        for changes in ({'PR_NUMBER': ''}, {'PR_URL': ''}):
            with self.subTest(changes=changes):
                env = self.env(PR_OPERATION='none', **changes)
                with self.assertRaises(ValueError):
                    E.verify_pr_document(self.pr_document(), env)
                env.update(PR_VERIFY_OUTCOME='failure', PR_DRAFT_VERIFIED='')
                doc = E.result_document(env)
                self.assertEqual(doc['publication'], 'failed')
                self.assertIsNone(doc['pr'])

    def test_result_bad_identity_and_inconsistent_checks_refused(self):
        for key, value in [('GITHUB_REF', 'refs/heads/feature'),
                           ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_REPOSITORY', 'other/repo'),
                           ('GITHUB_SHA', 'x' * 40), ('GITHUB_RUN_ID', '0'),
                           ('GITHUB_RUN_ATTEMPT', '1\n2'), ('JSON_SYNTAX', 'not_run'),
                           ('BUNDLE_SHA256', 'bad'), ('PR_URL', 'https://evil.invalid/pull/42'),
                           ('PR_HEAD_SHA', 'bad'), ('GENERATION', 'failure')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                E.result_document(self.env(**{key: value}))

    def test_self_report_never_promotes_failed_checks(self):
        doc = E.result_document(self.env(VALIDATOR_JOB='failure', JSON_SYNTAX='fail',
                                        CODEX_FINAL_MESSAGE='All tests passed'))
        self.assertTrue(doc['self_report_available'])
        self.assertEqual(doc['validation'], 'fail')
        self.assertIsNone(doc['pr'])

    def test_result_hash_is_hash_of_exact_uploaded_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sha = E.write_json(root / 'result.json', E.result_document(self.env()), E.MAX_RESULT)
            self.assertEqual(sha, E.digest((root / 'result.json').read_bytes()))
            with mock.patch.dict(os.environ, {'GITHUB_OUTPUT': str(root / 'outputs')}):
                E.outputs({'sha256': sha, 'bundle_sha256': 'b' * 64})
            self.assertIn('sha256=' + sha, (root / 'outputs').read_text())

    def test_trusted_cli_pipeline_and_failed_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / 'checkout'
            checkout.mkdir()
            bundle = self.bundle(root, [("powerbi/data.json", '{"synthetic":true}')])
            helper = str(ROOT / '.github/alfred-creator/evidence.py')
            output = root / 'outputs'
            env = {**os.environ, **self.env(), 'GITHUB_OUTPUT': str(output)}

            def run(*args):
                return subprocess.run([sys.executable, '-I', '-B', helper, *map(str, args)],
                                      env=env, check=True, capture_output=True)

            run('validate', bundle, checkout, root / 'validation.json')
            report = json.loads((root / 'validation.json').read_text())
            run('apply', bundle, checkout, report['bundle_sha256'])
            self.assertEqual((checkout / 'powerbi/data.json').read_text(), '{"synthetic":true}')
            env['BUNDLE_SHA256'] = report['bundle_sha256']
            run('result', root / 'success/result.json')
            doc = json.loads((root / 'success/result.json').read_text())
            self.assertEqual(doc['publication'], 'draft_created')
            self.assertIn('sha256=' + E.digest((root / 'success/result.json').read_bytes()),
                          output.read_text())
            env.update(GENERATION='failure', VALIDATOR_JOB='skipped', REPORT_ARTIFACT_ID='')
            run('result', root / 'failed/result.json')
            doc = json.loads((root / 'failed/result.json').read_text())
            self.assertEqual(doc['failure_code'], 'GENERATION_FAILED')
            self.assertEqual(doc['checks'], dict.fromkeys(E.CHECKS, 'not_run'))
            self.assertFalse(doc['self_report_available'])

    def test_closed_pr_action_is_no_changes_not_created(self):
        doc = E.result_document(self.env(PR_OPERATION='closed'))
        self.assertEqual(doc['publication'], 'no_changes')
        self.assertIsNone(doc['pr'])

    def test_write_result_budget_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, 'OUTPUT_BUDGET'):
            E.write_json(Path(directory) / 'result.json', {'text': 'x' * E.MAX_RESULT}, E.MAX_RESULT)


if __name__ == '__main__':
    unittest.main()
