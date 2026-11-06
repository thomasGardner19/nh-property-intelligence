"""Bounded artifact transport for the supervised Alfred Creator MVP.

A Codex job has no repository-write credentials. It produces only allowed
Power BI files; a separate GitHub Actions job (without model credentials)
validates and publishes them as a draft PR.

This script must be loaded from trusted checkout before Codex executes.
No external dependencies and no subprocess calls.
"""
from __future__ import annotations

import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILES = 100
MAX_FILE = 512 * 1024
MAX_TOTAL = 3 * 1024 * 1024
SUFFIXES = {".md", ".json", ".pbip", ".pbir", ".pbism", ".tmdl",
            ".csv", ".m", ".yaml", ".yml", ".txt", ".pbit"}


class Refused(ValueError):
    pass


def allowed(name: str) -> bool:
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        return False
    p = PurePosixPath(name)
    return (not p.is_absolute() and len(p.parts) >= 2
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


def unpack(zip_path: Path, root: Path) -> int:
    count, total = 0, 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        entries = zf.infolist()
        if not 0 < len(entries) <= MAX_FILES:
            raise Refused("ARTIFACT_COUNT")
        names = set()
        payloads = []
        for info in entries:
            name = info.filename
            typ = (info.external_attr >> 16) & 0o170000
            if (not allowed(name) or name in names or info.is_dir()
                    or typ not in (0, stat.S_IFREG)
                    or not 0 < info.file_size <= MAX_FILE):
                raise Refused("UNAPPROVED_ARTIFACT_MEMBER")
            names.add(name)
            total += info.file_size
            if total > MAX_TOTAL:
                raise Refused("ARTIFACT_BUDGET")
            raw = zf.read(info)
            if len(raw) != info.file_size:
                raise Refused("ARTIFACT_SIZE_MISMATCH")
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
