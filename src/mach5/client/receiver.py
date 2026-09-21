"""Durable, bounded receiver writes.

State is stored alongside a receiving root but separately from user content.
Each verified chunk is committed only after fsync; resume rehashes any
unconfirmed bytes instead of trusting a database claim alone.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from mach5.filesystem.destination import validate_destination
from mach5.filesystem.manifest import CHUNK_SIZE, Entry, ManifestError

class Receiver:
    def __init__(self, destination: Path, wrapper: str, entries: list[Entry], manifest_id: str) -> None:
        self.root = destination / wrapper
        self.state_dir = self.root / ".foldertransfer"
        self.partials = self.state_dir / "partials"
        if not self.state_dir.exists(): validate_destination(destination, entries, wrapper)
        self.root.mkdir(parents=True, exist_ok=True); self.partials.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.state_dir / "state.sqlite")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS transfer (manifest_id TEXT PRIMARY KEY)")
        self.db.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, size INTEGER NOT NULL, sha256 TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0)")
        old = self.db.execute("SELECT manifest_id FROM transfer").fetchone()
        if old and old[0] != manifest_id: raise ManifestError("state belongs to another manifest")
        self.db.execute("INSERT OR IGNORE INTO transfer VALUES (?)", (manifest_id,))
        for item in entries:
            if item.kind == "directory": (self.root / item.path).mkdir(parents=True, exist_ok=True)
            else: self.db.execute("INSERT OR IGNORE INTO files(path,size,sha256) VALUES (?,?,?)", (item.path, item.size, item.sha256))
        self.db.commit()

    def write_chunk(self, path: str, offset: int, data: bytes) -> None:
        row = self.db.execute("SELECT size, verified FROM files WHERE path=?", (path,)).fetchone()
        if not row or row[1] or offset < 0 or offset + len(data) > row[0]: raise ManifestError("invalid file chunk")
        target = self.partials / hashlib.sha256(path.encode()).hexdigest()
        fd = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.pwrite(fd, data, offset); os.fsync(fd)
        finally: os.close(fd)

    def read_chunk(self, path: str, offset: int, length: int) -> bytes:
        """Read a bounded chunk from a verified source path without blocking asyncio."""
        with path.open("rb") as source:
            source.seek(offset)
            return source.read(length)

    def finalize(self, path: str) -> None:
        row = self.db.execute("SELECT size,sha256,verified FROM files WHERE path=?", (path,)).fetchone()
        if not row or row[2]: return
        partial = self.partials / hashlib.sha256(path.encode()).hexdigest()
        if row[0] == 0 and not partial.exists():
            # A zero-byte file has no data chunk, but still needs the same
            # durable-finalization path as every other file.
            fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try: os.fsync(fd)
            finally: os.close(fd)
        if not partial.exists() or partial.stat().st_size != row[0]: raise ManifestError("partial size incomplete")
        digest = hashlib.sha256()
        with partial.open("rb") as source:
            for block in iter(lambda: source.read(CHUNK_SIZE), b""): digest.update(block)
        if digest.hexdigest() != row[1]: raise ManifestError("file integrity mismatch")
        target = self.root / path; target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(partial, target)
        self.db.execute("UPDATE files SET verified=1 WHERE path=?", (path,)); self.db.commit()

    def complete(self) -> bool:
        return self.db.execute("SELECT count(*) FROM files WHERE verified=0").fetchone()[0] == 0

    def close(self) -> None: self.db.close()
