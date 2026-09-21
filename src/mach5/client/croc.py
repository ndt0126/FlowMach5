"""Thin croc subprocess adapter. Pairing and file transport belong to croc."""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
from pathlib import Path


async def transfer(binary: str, relay: str, source: Path | None = None,
                   destination: Path | None = None) -> int:
    executable = shutil.which(binary)
    if not executable:
        raise RuntimeError("Install croc v11.5.3 or pass --binary with its path")
    if not relay:
        raise ValueError("An explicit croc relay is required")
    args = [executable, "--relay", relay, "--relay6", "", "--disable-clipboard"]
    if source is not None:
        source = source.absolute()
        if not source.exists() or source.is_symlink():
            raise ValueError("Select an existing regular file or directory")
        args += ["send", "--no-local", "--transport", "relay", str(source)]
    else:
        if destination is None or not destination.is_dir():
            raise ValueError("Choose an existing receiving directory")
        args += ["--out", str(destination.absolute())]
    # Inherit the terminal for croc's native confirmation and progress UI.
    # CROC_SECRET and CROC_PASS are read by croc from its environment; never
    # interpolate them into command arguments or print them from this adapter.
    process = await asyncio.create_subprocess_exec(*args)
    try:
        return await process.wait()
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Mach5 using croc's transfer engine")
    parser.add_argument("--binary", default=os.environ.get("MACH5_CROC_BINARY", "croc"))
    parser.add_argument("--relay", required=True, help="croc TCP relay host:port")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("send").add_argument("source", type=Path)
    commands.add_parser("receive").add_argument("destination", type=Path)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(transfer(args.binary, args.relay,
        source=args.source if args.command == "send" else None,
        destination=args.destination if args.command == "receive" else None)))


if __name__ == "__main__":
    main()
