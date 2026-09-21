from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator

CHUNK_SIZE = 1024 * 1024
RESERVED_DIRECTORY = ".foldertransfer"


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    path: str
    kind: str
    size: int = 0
    sha256: str = ""


@dataclass(frozen=True)
class PathSummary:
    max_relative_utf8: int
    max_component_utf8: int
    max_relative_utf16: int
    max_component_utf16: int

    def encode(self) -> str:
        def varint(value: int) -> bytes:
            out = bytearray()
            while True:
                byte = value & 0x7F
                value >>= 7
                out.append(byte | (0x80 if value else 0))
                if not value:
                    return bytes(out)
        return base64.urlsafe_b64encode(b"\x01" + b"".join(varint(v) for v in asdict(self).values())).rstrip(b"=").decode()

    @classmethod
    def decode(cls, encoded: str) -> "PathSummary":
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except Exception as exc:
            raise ManifestError("malformed path summary") from exc
        if not raw or raw[0] != 1:
            raise ManifestError("unsupported path summary version")
        values, pos = [], 1
        for _ in range(4):
            value, shift = 0, 0
            while True:
                if pos >= len(raw) or shift > 63:
                    raise ManifestError("malformed path summary")
                byte = raw[pos]; pos += 1
                value |= (byte & 0x7F) << shift; shift += 7
                if not byte & 0x80: break
            values.append(value)
        if pos != len(raw): raise ManifestError("malformed path summary")
        return cls(*values)


def _units(value: str) -> tuple[int, int]:
    return len(value.encode("utf-8")), len(value.encode("utf-16-le")) // 2


def validate_relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or value.startswith("/") or ":" in value:
        raise ManifestError("path must be a nonempty relative POSIX path")
    path = PurePosixPath(value)
    if any(part in ("", ".", "..", RESERVED_DIRECTORY) for part in path.parts):
        raise ManifestError("unsafe or reserved relative path")
    return path


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def scan(source: Path) -> tuple[list[Entry], PathSummary, str]:
    source = source.resolve(strict=True)
    if source.is_symlink(): raise ManifestError("symlink sources are unsupported")
    roots = [source] if source.is_file() else sorted(source.rglob("*"))
    entries: list[Entry] = []
    for node in roots:
        rel = node.name if source.is_file() else node.relative_to(source).as_posix()
        st = node.lstat()
        if stat.S_ISLNK(st.st_mode): raise ManifestError(f"symlink unsupported: {rel}")
        if node.is_dir(): entries.append(Entry(rel, "directory")); continue
        if not node.is_file(): raise ManifestError(f"special file unsupported: {rel}")
        before = (st.st_size, st.st_mtime_ns)
        digest = _hash(node)
        after = node.stat()
        if before != (after.st_size, after.st_mtime_ns): raise ManifestError(f"source changed while reading: {rel}")
        entries.append(Entry(rel, "file", st.st_size, digest))
    parts = [(p, _units(p)) for e in entries for p in [e.path] for p in [p]]
    components = [_units(c) for e in entries for c in PurePosixPath(e.path).parts]
    summary = PathSummary(max((x[1][0] for x in parts), default=0), max((x[0] for x in components), default=0), max((x[1][1] for x in parts), default=0), max((x[1] for x in components), default=0))
    payload = json.dumps([asdict(e) for e in entries], ensure_ascii=False, separators=(",", ":")).encode()
    return entries, summary, hashlib.sha256(payload).hexdigest()


def write_manifest(path: Path, entries: list[Entry]) -> None:
    path.write_text(json.dumps([asdict(e) for e in entries], ensure_ascii=False), encoding="utf-8")
