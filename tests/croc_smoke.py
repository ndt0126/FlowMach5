"""Opt-in real croc smoke test: python tests/croc_smoke.py /path/to/croc.

Uses generated data and separate OS processes. Defaults to a loopback relay
with fresh credentials; MACH5_TEST_RELAY and CROC_PASS select a private remote
relay. Pairing codes are always generated afresh.
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
    remote = os.environ.get("MACH5_TEST_RELAY")
    # Check local ports only when this test starts its own relay.
    ports = [19209, 19210, 19211, 19212, 19213]
    for port in ([] if remote else ports):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    password = os.environ.get("CROC_PASS") if remote else secrets.token_hex(24)
    if remote and not password:
        raise RuntimeError("Set CROC_PASS for a private remote relay test")
    address = remote or "127.0.0.1:19209"
    env = dict(os.environ, CROC_PASS=password,
               CROC_SECRET=secrets.token_hex(24), CROC_RELAY=address,
               CROC_RELAY6="", XDG_CONFIG_HOME=str(root / "config"))
    processes = []
    started = time.monotonic()
    timeout = float(os.environ.get("MACH5_TEST_TIMEOUT", "1200"))
    logs = []
    # Keep output in restricted temporary handles and redact secrets on failure.
    def spawn(args, cwd=None):
        log = tempfile.TemporaryFile()
        logs.append(log)
        process = subprocess.Popen([binary, *args], cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        processes.append(process)
        return process
    try:
        relay = None if remote else spawn(["relay", "--host", "127.0.0.1", "--ports", ",".join(map(str, ports))])
        deadline = time.monotonic() + 10
        while not remote:
            try:
                with socket.create_connection(("127.0.0.1", ports[0]), timeout=.2):
                    break
            except OSError:
                if relay.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("local croc relay did not start")
                time.sleep(.1)
        common = ["--relay", address, "--relay6", "", "--yes", "--disable-clipboard"]
        sender = spawn([*common, "send", "--no-local", "--transport", "relay", str(source)])
        receiver = spawn([*common, "--out", str(destination)])
        for process in (sender, receiver):
            timed_out = False
            try:
                failed = process.wait(timeout=max(.01, timeout - (time.monotonic() - started))) != 0
            except subprocess.TimeoutExpired:
                timed_out = failed = True
            if failed:
                log = logs[processes.index(process)]
                log.seek(0)
                message = log.read().decode(errors="replace")
                for secret in (password, env["CROC_SECRET"]):
                    message = message.replace(secret, "[REDACTED]")
                reason = "timed out" if timed_out else "failed"
                raise RuntimeError(f"croc endpoint {reason}: " + message[-2000:])
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
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
