# Mach5

Mach5 is a source-run macOS/Windows transfer project. Its local controller
runs on loopback, so closing the browser does not end its Python process.

## Current implementation status

The prototype includes asynchronous bounded source scans, stable SHA-256
manifests, explicit empty directories, Unicode path summaries, unsafe-path
validation, durable receiver state, encrypted relay frames, and a
command-line sender/receiver transfer path. The native picker,
browser drag-and-drop, link-creation UI, reconnecting sender state, and
cross-platform validation are still outstanding. The browser UI therefore
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
