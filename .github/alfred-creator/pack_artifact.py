"""Bounded artifact transport for the supervised Alfred Creator MVP.

A Codex job has no repository-write credentials. It produces only allowed
Power BI files; a separate GitHub Actions job (without model credentials)
validates and publishes them as a draft PR.

This script must be loaded from trusted checkout before Codex executes.
No external dependencies and no subprocess calls.
"""
from __future__ import annotations

import stat
import struct
import sys
import zipfile
import zlib
from pathlib import Path, PurePosixPath

MAX_FILES = 100
MAX_FILE = 512 * 1024
MAX_TOTAL = 3 * 1024 * 1024
MAX_ARCHIVE = 4 * 1024 * 1024
SUFFIXES = {".md", ".json", ".pbip", ".pbir", ".pbism", ".tmdl",
            ".csv", ".m", ".yaml", ".yml", ".txt", ".pbit"}


class Refused(ValueError):
    pass


def allowed(name: str) -> bool:
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        return False
    p = PurePosixPath(name)
    # PurePosixPath collapses dot segments and repeated separators. Reject
    # those spellings so distinct zip names cannot overwrite one target.
    return (name == p.as_posix() and not p.is_absolute() and len(p.parts) >= 2
            and p.parts[0] == "powerbi"
            and all(x not in ("", ".", "..") and not x.startswith(".")
                    for x in p.parts)
            and p.suffix.lower() in SUFFIXES
            and len(name) <= 240)


def pack(root: Path, dest: Path) -> int:
    base = root / "powerbi"
    if not base.is_dir() or base.is_symlink():
        raise Refused("POWERBI_DIRECTORY_MISSING_OR_LINKED")
    files = []
    total = 0
    for p in sorted(base.rglob("*")):
        relative = p.relative_to(root).as_posix()
        s = p.lstat()
        if stat.S_ISDIR(s.st_mode):
            if s.st_mode & 0o002:
                raise Refused("WORLD_WRITABLE_DIRECTORY")
            continue
        if not (stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and allowed(relative)
                and 0 < s.st_size <= MAX_FILE):
            raise Refused("UNAPPROVED_SOURCE_FILE")
        total += s.st_size
        files.append(p)
        if total > MAX_TOTAL or len(files) > MAX_FILES:
            raise Refused("ARTIFACT_BUDGET")
    if not files:
        raise Refused("NO_GENERATED_FILES")
    with zipfile.ZipFile(dest, "x", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            relative = p.relative_to(root).as_posix()
            zf.write(p, arcname=relative)
    return len(files)


def read_member(source, info: zipfile.ZipInfo) -> bytes:
    """Inflate with an output bound independent of untrusted ZIP size claims.

    ZipExtFile truncates to the declared file_size before checking the CRC.
    A bounded ZipExtFile read alone can therefore accept a forged short prefix.
    Our packer emits seekable, non-ZIP64 archives without data descriptors;
    accept only that simple format and require the complete compressed stream.
    """
    source.seek(info.header_offset)
    header = source.read(30)
    if len(header) != 30:
        raise Refused("ARTIFACT_LOCAL_HEADER")
    signature, _, flags, method, _, _, crc, compressed, size, namesize, extra = (
        struct.unpack("<4s5H3I2H", header)
    )
    if (signature != b"PK\x03\x04" or flags != info.flag_bits or flags & ~0x800
            or method != info.compress_type or crc != info.CRC
            or compressed != info.compress_size or size != info.file_size
            or not 0 < compressed <= MAX_ARCHIVE):
        raise Refused("ARTIFACT_LOCAL_HEADER")
    name = source.read(namesize)
    encoding = "utf-8" if flags & 0x800 else "cp437"
    if name != info.filename.encode(encoding):
        raise Refused("ARTIFACT_LOCAL_NAME")
    source.seek(extra, 1)
    if method == zipfile.ZIP_STORED and compressed != size:
        raise Refused("ARTIFACT_SIZE_MISMATCH")
    data = source.read(compressed)
    if len(data) != compressed:
        raise Refused("ARTIFACT_COMPRESSED_SIZE")
    if method == zipfile.ZIP_DEFLATED:
        inflater = zlib.decompressobj(-15)
        try:
            # Never flush: a flush without a limit could inflate the remainder.
            raw = inflater.decompress(data, size + 1)
        except zlib.error as exc:
            raise Refused("ARTIFACT_DEFLATE") from exc
        if not inflater.eof or inflater.unconsumed_tail or inflater.unused_data:
            raise Refused("ARTIFACT_DEFLATE_BOUNDARY")
    else:
        raw = data
    if len(raw) != size or zlib.crc32(raw) != crc:
        raise Refused("ARTIFACT_SIZE_OR_CRC_MISMATCH")
    return raw


def unpack(zip_path: Path, root: Path) -> int:
    with zip_path.open("rb") as source:
        source.seek(0, 2)
        if not 0 < source.tell() <= MAX_ARCHIVE:
            raise Refused("ARTIFACT_ARCHIVE_BUDGET")
        source.seek(0)
        return unpack_source(source, root)


def unpack_source(source, root: Path) -> int:
    count, total = 0, 0
    with zipfile.ZipFile(source, "r") as zf:
        entries = zf.infolist()
        if not 0 < len(entries) <= MAX_FILES:
            raise Refused("ARTIFACT_COUNT")
        names = set()
        payloads = []
        for info in entries:
            name = info.filename
            typ = (info.external_attr >> 16) & 0o170000
            if (not allowed(name) or info.orig_filename != name
                    or name in names or info.is_dir()
                    or typ not in (0, stat.S_IFREG)
                    or info.flag_bits & ~0x800
                    or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    or not 0 < info.file_size <= MAX_FILE):
                raise Refused("UNAPPROVED_ARTIFACT_MEMBER")
            names.add(name)
            total += info.file_size
            if total > MAX_TOTAL:
                raise Refused("ARTIFACT_BUDGET")
            raw = read_member(source, info)
            payloads.append((name, raw))
        for name, raw in payloads:
            target = root.joinpath(*PurePosixPath(name).parts)
            # The publisher checkout is fresh and trusted. Reject symlinks
            # and unknown pre-existing files instead of following them.
            parent = target.parent
            for ancestor in (root, *list(parent.parents)[::-1], parent):
                if (ancestor == root or root in ancestor.parents) and ancestor.is_symlink():
                    raise Refused("UNTRUSTED_PARENT")
            parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                raise Refused("TARGET_LINK")
            if target.exists() and not target.is_file():
                raise Refused("UNTRUSTED_TARGET")
            target.write_bytes(raw)
            count += 1
    return count


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in ("pack", "unpack"):
        print("usage: pack_artifact.py pack|unpack <repo> <zip-file>", file=sys.stderr)
        return 2
    action, repo, zipfile_name = sys.argv[1:]
    try:
        root = Path(repo).resolve(strict=True)
        if action == "pack":
            n = pack(root, Path(zipfile_name))
        else:
            n = unpack(Path(zipfile_name), root)
    except (Refused, OSError, zipfile.BadZipFile) as exc:
        print(f"REFUSED {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"PASS_CREATOR_{action.upper()} FILES={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

