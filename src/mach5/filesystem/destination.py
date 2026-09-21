from __future__ import annotations

import os
from pathlib import Path
from .manifest import Entry, ManifestError, RESERVED_DIRECTORY, validate_relative_path

WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

def validate_destination(destination: Path, entries: list[Entry], wrapper: str) -> None:
    validate_relative_path(wrapper)
    seen: set[str] = set()
    for entry in entries:
        relative = validate_relative_path(entry.path)
        for part in relative.parts:
            stem = part.split(".")[0].upper()
            if part.rstrip(". ") != part or stem in WINDOWS_RESERVED:
                raise ManifestError(f"Windows-incompatible name: {entry.path}")
        target = destination / wrapper / Path(*relative.parts)
        try: target.relative_to(destination / wrapper)
        except ValueError as exc: raise ManifestError("destination escape") from exc
        key = str(relative).casefold()
        if key in seen: raise ManifestError(f"case collision: {entry.path}")
        seen.add(key)
        if target.exists(): raise ManifestError(f"destination already exists: {target}")
    if (destination / wrapper / RESERVED_DIRECTORY).exists():
        raise ManifestError("internal state directory already exists")
