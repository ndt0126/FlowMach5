"""Opt-in real croc smoke test: python tests/croc_smoke.py /path/to/croc.

Uses a loopback relay, fresh random credentials, generated data and separate
OS processes. No public relay or production enrollment credential is used.
"""
import hashlib
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time


def snapshot(root):
    result = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result[relative] = None
        else:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            result[relative] = digest.hexdigest()
    return result


def main():
    binary = str(Path(sys.argv[1]).resolve())
    root = Path(tempfile.mkdtemp(prefix="mach5-croc-smoke-"))
    source, destination = root / "source", root / "destination"
    (source / "nested" / "empty").mkdir(parents=True)
    destination.mkdir()
    (source / "zero.txt").touch()
    (source / "日本語.txt").write_text("Unicode file contents", encoding="utf-8")
    for number in range(1000):
        (source / "nested" / f"file-{number:04}.txt").write_bytes(secrets.token_bytes(128))
    with (source / "large.bin").open("wb") as output:
        for _ in range(16):
            output.write(secrets.token_bytes(1024 * 1024))
    expected = snapshot(source)
    # Reserve-check a private test port block before asking croc to bind it.
    ports = [19209, 19210, 19211, 19212, 19213]
    for port in ports:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    env = dict(os.environ, CROC_PASS=secrets.token_hex(24),
               CROC_SECRET=secrets.token_hex(24), CROC_RELAY="127.0.0.1:19209",
               CROC_RELAY6="", XDG_CONFIG_HOME=str(root / "config"))
    processes = []
    started = time.monotonic()
    # Output is intentionally discarded: croc can print the pairing secret.
    def spawn(args, cwd=None):
        process = subprocess.Popen([binary, *args], cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append(process)
        return process
    try:
        relay = spawn(["relay", "--host", "127.0.0.1", "--ports", ",".join(map(str, ports))])
        deadline = time.monotonic() + 10
        while True:
            try:
                with socket.create_connection(("127.0.0.1", ports[0]), timeout=.2):
                    break
            except OSError:
                if relay.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("local croc relay did not start")
                time.sleep(.1)
        common = ["--relay", "127.0.0.1:19209", "--relay6", "", "--yes", "--disable-clipboard"]
        sender = spawn([*common, "send", "--no-local", "--transport", "relay", str(source)])
        receiver = spawn([*common, "--out", str(destination)])
        for process in (sender, receiver):
            if process.wait(timeout=180) != 0:
                raise RuntimeError("croc endpoint failed (secret-bearing output suppressed)")
        actual = snapshot(destination / source.name)
        assert actual == expected, "received paths or SHA-256 hashes differ"
        assert snapshot(source) == expected, "source contents changed"
        print(f"PASS: 1003 files, 16 MiB large file, Unicode and empty directories; {time.monotonic()-started:.2f}s")
        print(f"Fixture and received output: {root}")
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
