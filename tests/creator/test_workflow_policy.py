"""Source-only workflow contract checks. No job dispatch or provider access."""
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/alfred-creator-codex.yml"


class WorkflowPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # BaseLoader avoids YAML 1.1 treating the Actions key 'on' as boolean.
        cls.workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)

    def test_dispatch_is_the_only_trigger(self):
        self.assertEqual(set(self.workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(set(self.workflow["on"]["workflow_dispatch"]["inputs"]),
                         {"issue_number"})

    def test_each_executing_job_is_main_and_issue_bound(self):
        for job in ("codex", "validate", "publish"):
            with self.subTest(job=job):
                condition = self.workflow["jobs"][job]["if"]
                self.assertIn("github.ref == 'refs/heads/main'", condition)
                self.assertIn("inputs.issue_number == '18'", condition)
                self.assertNotIn("||", condition)

    def test_both_checkouts_are_pinned_to_dispatch_commit(self):
        for job in ("codex", "validate", "publish"):
            with self.subTest(job=job):
                checkouts = [s for s in self.workflow["jobs"][job]["steps"]
                             if s.get("uses", "").startswith("actions/checkout@")]
                self.assertEqual(len(checkouts), 1)
                self.assertEqual(checkouts[0]["with"]["ref"], "${{ github.sha }}")
                self.assertEqual(checkouts[0]["with"]["persist-credentials"], "false")

    def test_publisher_cannot_have_model_credential(self):
        publisher = self.workflow["jobs"]["publish"]
        self.assertNotIn("CODEX_CREATOR_API_KEY", str(publisher))
        self.assertEqual(self.workflow["jobs"]["codex"]["permissions"],
                         {"contents": "read"})

    def test_publisher_creates_only_draft_powerbi_pr(self):
        steps = self.workflow["jobs"]["publish"]["steps"]
        publishers = [s for s in steps if s.get("uses", "").startswith(
            "peter-evans/create-pull-request@")]
        self.assertEqual(len(publishers), 1)
        settings = publishers[0]["with"]
        self.assertEqual(settings["draft"], "true")
        self.assertEqual(settings["add-paths"], "powerbi")
        self.assertEqual(settings["base"], "main")


    def test_only_three_jobs_and_no_validator_secrets(self):
        jobs = self.workflow["jobs"]
        self.assertEqual(set(jobs), {"codex", "validate", "publish"})
        self.assertEqual(jobs["validate"]["permissions"], {"contents": "read"})
        self.assertNotIn("secrets.", str(jobs["validate"]))
        self.assertNotIn("openai/codex-action", str(jobs["validate"]))
        self.assertNotIn("peter-evans", str(jobs["validate"]))

    def test_codex_output_file_and_separate_report(self):
        steps = self.workflow["jobs"]["codex"]["steps"]
        model = next(s for s in steps if s.get("id") == "codex")
        self.assertEqual(model["with"]["output-file"], "${{ runner.temp }}/codex-final.txt")
        report = next(s for s in steps if s.get("id") == "report_upload")
        self.assertIn("always()", report["if"])
        self.assertEqual(report["with"]["name"],
                         "creator-self-report-${{ github.run_id }}-${{ github.run_attempt }}")

    def test_handoffs_use_immutable_artifact_ids_not_names(self):
        for job in ("validate", "publish"):
            for step in self.workflow["jobs"][job]["steps"]:
                if step.get("uses", "").startswith("actions/download-artifact@"):
                    self.assertIn("artifact-ids", step["with"])
                    self.assertNotIn("name", step["with"])
                    self.assertEqual(step["with"]["merge-multiple"], "true")

    def test_publication_requires_validation_success(self):
        publish = self.workflow["jobs"]["publish"]
        self.assertEqual(publish["needs"], ["codex", "validate"])
        self.assertIn("always()", publish["if"])
        pr = next(s for s in publish["steps"] if s.get("id") == "pr")
        self.assertIn("needs.codex.result == 'success'", pr["if"])
        self.assertIn("needs.validate.result == 'success'", pr["if"])
        self.assertIn("success()", pr["if"])

    def test_publisher_uses_frozen_helpers_and_no_generated_programs(self):
        for step in self.workflow["jobs"]["publish"]["steps"]:
            command = step.get("run", "")
            if "python3" in command:
                self.assertIn('-I -B "$RUNNER_TEMP/publisher-tools/evidence.py"', command)
                self.assertNotIn("powerbi/", command.split("python3", 1)[1].split("\n", 1)[0])
        validator = str(self.workflow["jobs"]["validate"]["steps"])
        self.assertNotIn("pytest", validator)
        self.assertNotIn("pip install", validator)

    def test_final_artifact_is_always_available_when_builder_succeeds(self):
        steps = self.workflow["jobs"]["publish"]["steps"]
        result = next(s for s in steps if s.get("id") == "result")
        upload = next(s for s in steps if s.get("id") == "result_upload")
        self.assertIn("always()", result["if"])
        self.assertIn("always()", upload["if"])
        self.assertEqual(upload["with"]["path"], "${{ runner.temp }}/result/result.json")
        self.assertEqual(upload["with"]["name"],
                         "creator-result-${{ github.run_id }}-${{ github.run_attempt }}")
        self.assertNotIn("CODEX_FINAL", str(result["env"]))

    def test_artifact_provenance_anchor_is_in_fixed_trusted_publisher(self):
        publish = self.workflow["jobs"]["publish"]
        self.assertEqual(publish["name"], "Publish reviewed Creator result")
        anchor = publish["steps"][-1]
        self.assertEqual(anchor["name"], "Creator result artifact ${{ steps.result_upload.outputs.artifact-id }} sha256 ${{ steps.result.outputs.sha256 }}")
        self.assertEqual(anchor["run"], "true")
        self.assertIn("steps.result_upload.outcome == 'success'", anchor["if"])
        self.assertIn("steps.result.outcome == 'success'", anchor["if"])
        self.assertIn("always()", anchor["if"])

    def test_all_actions_remain_commit_pinned(self):
        import re
        for job in self.workflow["jobs"].values():
            for step in job["steps"]:
                if "uses" in step:
                    self.assertIsNotNone(re.fullmatch(r"[a-zA-Z0-9_/-]+@[0-9a-f]{40}", step["uses"]))


if __name__ == "__main__":
    unittest.main()
