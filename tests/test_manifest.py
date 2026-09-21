from pathlib import Path
import pytest
from mach5.filesystem.destination import validate_destination
from mach5.filesystem.manifest import Entry, ManifestError, PathSummary, scan, validate_relative_path
from mach5.client.receiver import Receiver
from mach5.security.channel import Channel, Handshake

def test_summary_roundtrip_and_unicode(tmp_path: Path):
    (tmp_path / "é😀.txt").write_text("x")
    entries, summary, _ = scan(tmp_path)
    assert PathSummary.decode(summary.encode()) == summary
    assert summary.max_relative_utf16 >= 6
    validate_destination(tmp_path / "out", entries, "received")

@pytest.mark.parametrize("path", ["../x", "/x", "C:x", "a\\b", ".foldertransfer/x"])
def test_unsafe_paths_rejected(path: str):
    with pytest.raises(ManifestError): validate_relative_path(path)

def test_windows_collision_rejected(tmp_path: Path):
    with pytest.raises(ManifestError): validate_destination(tmp_path, [Entry("A.txt", "file"), Entry("a.TXT", "file")], "content")

def test_receiver_durable_partial_and_integrity(tmp_path: Path):
    import hashlib
    data = b"large-ish data" * 100
    entry = Entry("nested/file.bin", "file", len(data), hashlib.sha256(data).hexdigest())
    receiver = Receiver(tmp_path, "received", [Entry("nested", "directory"), entry], "manifest-1")
    receiver.write_chunk(entry.path, 0, data[:20]); receiver.close()
    receiver = Receiver(tmp_path, "received", [Entry("nested", "directory"), entry], "manifest-1")
    receiver.write_chunk(entry.path, 20, data[20:]); receiver.finalize(entry.path)
    assert receiver.complete() and (tmp_path / "received/nested/file.bin").read_bytes() == data

def test_confirmed_encrypted_channel():
    left, right = Handshake.create(), Handshake.create()
    left_key, left_code = left.derive(right.public()); right_key, right_code = right.derive(left.public())
    assert left_key == right_key and left_code == right_code
    sealed = Channel(left_key, b"sender-to-receiver").seal(b"private manifest")
    assert Channel(right_key, b"sender-to-receiver").open(sealed) == b"private manifest"
