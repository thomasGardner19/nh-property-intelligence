import importlib.util
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / ".github/alfred-creator/pack_artifact.py"
spec = importlib.util.spec_from_file_location("pack_under_test", SOURCE)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class ArtifactPolicyTests(unittest.TestCase):
    def forged_size_archive(self, path, content, claimed=b"{}"):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("powerbi/data.json", content)
        raw = bytearray(path.read_bytes())
        central = raw.index(b"PK\x01\x02")
        for offset in (14, central + 16):
            struct.pack_into("<I", raw, offset, zlib.crc32(claimed))
        for offset in (22, central + 24):
            struct.pack_into("<I", raw, offset, len(claimed))
        path.write_bytes(raw)

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

    def test_noncanonical_names_refused(self):
        for name in ("./powerbi/data.json", "powerbi/./data.json",
                     "powerbi//data.json", "powerbi/data.json/",
                     "powerbi/data.json/."):
            with self.subTest(name=name):
                self.assertFalse(M.allowed(name))

    def test_archive_aliases_refused_before_writes(self):
        for alias in ("./powerbi/data.json", "powerbi/./data.json",
                      "powerbi//data.json", "powerbi/data.json/",
                      "powerbi/data.json/."):
            with self.subTest(alias=alias), tempfile.TemporaryDirectory() as temp:
                p = Path(temp)
                with zipfile.ZipFile(p/"alias.zip", "w") as archive:
                    archive.writestr("powerbi/data.json", "original")
                    archive.writestr(alias, "replacement")
                with self.assertRaises(M.Refused):
                    M.unpack(p/"alias.zip", p)
                self.assertFalse((p/"powerbi").exists())

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

    def test_forged_size_and_prefix_crc_refused_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            archive = p / "lying.zip"
            self.forged_size_archive(archive, b"{}" + b" " * (16 * 1024 * 1024))
            self.assertLess(archive.stat().st_size, 32 * 1024)
            # This is the dangerous behavior that trusting ZipExtFile hid:
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(z.infolist()[0].file_size, 2)
            with self.assertRaises(M.Refused):
                M.unpack(archive, p)
            self.assertFalse((p / "powerbi").exists())

    def test_forged_size_hits_small_decompression_limit(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            archive = p / "lying.zip"
            self.forged_size_archive(archive, b"{}" + b" " * (16 * 1024 * 1024))
            original = zlib.decompressobj
            limits = []

            class BoundedInflater:
                def __init__(self, *args):
                    self.real = original(*args)

                def decompress(self, data, limit):
                    limits.append(limit)
                    return self.real.decompress(data, limit)

                def __getattr__(self, key):
                    return getattr(self.real, key)

            with (patch.object(M.zlib, "decompressobj", BoundedInflater),
                  self.assertRaises(M.Refused)):
                M.unpack(archive, p)
            self.assertEqual(limits, [3])

    def test_maximum_legitimate_file_and_utf8_name_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            data = b"a" * M.MAX_FILE
            with zipfile.ZipFile(p / "full.zip", "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("powerbi/r\u00e9sum\u00e9.txt", data)
            self.assertEqual(M.unpack(p / "full.zip", p), 1)
            self.assertEqual((p / "powerbi/r\u00e9sum\u00e9.txt").read_bytes(), data)

    def test_unsupported_compression_refused(self):
        for method in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as temp:
                p = Path(temp)
                with zipfile.ZipFile(p / "unsupported.zip", "w", method) as z:
                    z.writestr("powerbi/data.json", "{}")
                with self.assertRaises(M.Refused):
                    M.unpack(p / "unsupported.zip", p)
                self.assertFalse((p / "powerbi").exists())

    def test_encryption_and_descriptor_flags_refused(self):
        for flags in (1, 8):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as temp:
                p = Path(temp)
                archive = p / "flags.zip"
                with zipfile.ZipFile(archive, "w") as z:
                    z.writestr("powerbi/data.json", "{}")
                raw = bytearray(archive.read_bytes())
                central = raw.index(b"PK\x01\x02")
                for offset in (6, central + 8):
                    struct.pack_into("<H", raw, offset, flags)
                archive.write_bytes(raw)
                with self.assertRaises(M.Refused):
                    M.unpack(archive, p)

    def test_header_mismatch_and_bad_crc_refused(self):
        for mismatch in (True, False):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as temp:
                p = Path(temp)
                archive = p / "header.zip"
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr("powerbi/data.json", "{}")
                raw = bytearray(archive.read_bytes())
                central = raw.index(b"PK\x01\x02")
                struct.pack_into("<I", raw, 14, 123)
                if not mismatch:
                    struct.pack_into("<I", raw, central + 16, 123)
                archive.write_bytes(raw)
                with self.assertRaises(M.Refused):
                    M.unpack(archive, p)
                self.assertFalse((p / "powerbi").exists())

    def test_truncated_or_trailing_deflate_refused(self):
        for difference in (-1, 1):
            with self.subTest(difference=difference), tempfile.TemporaryDirectory() as temp:
                p = Path(temp)
                archive = p / "deflate.zip"
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr("powerbi/data.json", "{}")
                raw = bytearray(archive.read_bytes())
                central = raw.index(b"PK\x01\x02")
                compressed = struct.unpack_from("<I", raw, 18)[0]
                for offset in (18, central + 20):
                    struct.pack_into("<I", raw, offset, compressed + difference)
                archive.write_bytes(raw)
                with self.assertRaises(M.Refused):
                    M.unpack(archive, p)
                self.assertFalse((p / "powerbi").exists())

    def test_archive_input_budget_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            archive = p / "large.zip"
            archive.write_bytes(b"x" * (M.MAX_ARCHIVE + 1))
            with self.assertRaises(M.Refused):
                M.unpack(archive, p)


if __name__ == "__main__":
    unittest.main()

