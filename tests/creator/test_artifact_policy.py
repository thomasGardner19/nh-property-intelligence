import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / ".github/alfred-creator/pack_artifact.py"
spec = importlib.util.spec_from_file_location("pack_under_test", SOURCE)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class ArtifactPolicyTests(unittest.TestCase):
    def test_accepted_names(self):
        self.assertTrue(M.allowed("powerbi/NH_Property_Intelligence.Report/definition/report.json"))
        self.assertTrue(M.allowed("powerbi/README.md"))
        self.assertFalse(M.allowed("../powerbi/report.json"))
        self.assertFalse(M.allowed("powerbi/../.github/workflows/evil.yml"))
        self.assertFalse(M.allowed(".github/workflows/evil.yml"))
        self.assertFalse(M.allowed("powerbi/secret.key"))
        self.assertFalse(M.allowed("powerbi/.env"))
        self.assertFalse(M.allowed("powerbi\\..\\evil.md"))

    def test_pack_and_unpack_verified_source(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            a, b = Path(src), Path(dst)
            target = a / "powerbi/Report/definition.pbir"
            target.parent.mkdir(parents=True)
            target.write_text('{"version":"4.0"}')
            archive = a / "bundle.zip"
            self.assertEqual(M.pack(a, archive), 1)
            self.assertEqual(M.unpack(archive, b), 1)
            self.assertEqual((b/"powerbi/Report/definition.pbir").read_bytes(),
                             target.read_bytes())

    def test_no_source_files_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p/"powerbi").mkdir()
            with self.assertRaises(M.Refused):
                M.pack(p, p/"archive.zip")

    def test_source_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            (p/"powerbi").mkdir()
            (p/"powerbi/secret.md").symlink_to("/etc/passwd")
            with self.assertRaises(M.Refused):
                M.pack(p, p/"archive.zip")

    def test_source_hardlink_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            (p/"powerbi").mkdir()
            f=p/"powerbi/data.csv"
            f.write_text("synthetic")
            (p/"powerbi/data2.csv").hardlink_to(f)
            with self.assertRaises(M.Refused):
                M.pack(p, p/"archive.zip")

    def test_zip_traversal_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            z=p/"malicious.zip"
            with zipfile.ZipFile(z, "w") as archive:
                archive.writestr("powerbi/../../.github/workflows/evil.yml", "data")
            with self.assertRaises(M.Refused):
                M.unpack(z, p)

    def test_duplicate_archive_entries_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            with zipfile.ZipFile(p/"duplicate.zip","w") as archive:
                archive.writestr("powerbi/data.json", "one")
                archive.writestr("powerbi/data.json", "two")
            with self.assertRaises(M.Refused):
                M.unpack(p/"duplicate.zip", p)

    def test_dangling_symlink_target_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            (p/"powerbi").mkdir()
            (p/"powerbi/data.json").symlink_to("/nonexistent-target")
            with zipfile.ZipFile(p/"safe.zip","w") as z:
                z.writestr("powerbi/data.json", '{"safe":true}')
            with self.assertRaises(M.Refused):
                M.unpack(p/"safe.zip",p)

    def test_existing_nested_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            p=Path(temp)
            (p/"powerbi").mkdir()
            (p/"powerbi/link").symlink_to(outside,target_is_directory=True)
            with zipfile.ZipFile(p/"safe.zip","w") as z:
                z.writestr("powerbi/link/data.json", "untrusted")
            with self.assertRaises(M.Refused):
                M.unpack(p/"safe.zip",p)

    def test_oversized_member_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            with zipfile.ZipFile(p/"big.zip","w") as z:
                z.writestr("powerbi/big.json", "a" * (M.MAX_FILE + 1))
            with self.assertRaises(M.Refused):
                M.unpack(p/"big.zip", p)


if __name__ == "__main__":
    unittest.main()
