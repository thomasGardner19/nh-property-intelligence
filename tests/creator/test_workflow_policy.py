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
        for job in ("codex", "publish"):
            with self.subTest(job=job):
                condition = self.workflow["jobs"][job]["if"]
                self.assertIn("github.ref == 'refs/heads/main'", condition)
                self.assertIn("inputs.issue_number == '18'", condition)
                self.assertNotIn("||", condition)

    def test_both_checkouts_are_pinned_to_dispatch_commit(self):
        for job in ("codex", "publish"):
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


if __name__ == "__main__":
    unittest.main()
