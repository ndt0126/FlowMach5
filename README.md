# Mach5

Mach5 is a source-run macOS/Windows transfer project. Its local controller
runs on loopback, so closing the browser does not end its Python process.

## Current implementation status

Phase A foundation is implemented: asynchronous bounded source scans, stable
SHA-256 manifests, explicit empty directories, Unicode path summaries,
unsafe-path validation, a loopback controller, and a bounded blind relay
rendezvous service. The working native picker, browser drag-and-drop spike,
receiver SQLite state/resume, end-to-end encrypted data plane, and completed
internet transfer engine are not implemented yet. The browser UI therefore
uses an explicit path field and must not be presented as seamless drag/drop.

## Development

Use Python 3.11+:

```sh
python -m venv .venv
.venv/bin/pip install . pytest
PYTHONPATH=src .venv/bin/pytest
PYTHONPATH=src .venv/bin/python -m mach5.client.app
```

Run a relay for development with `MACH5_ENROLLMENT_TOKEN` set in the service
environment and `python -m mach5.server.app`. No license has been selected.
