# Croc integration

Mach5 is moving to croc's established transfer engine. The initial adapter is
`python -m mach5.client.croc`; it supervises a native croc subprocess and uses
croc's native pairing, encryption, multiplexing, and progress. It does not use
the experimental Mach5 WebSocket protocol or its custom crypto.

Target version: [croc v11.5.3](https://github.com/schollz/croc/releases/tag/v11.5.3).
Install the official binary for your OS. Set `MACH5_CROC_BINARY` if it is not on
PATH. Mac and Windows use the same Python adapter.

```sh
python -m mach5.client.croc --relay YOUR_RELAY:9009 send /path/to/source
python -m mach5.client.croc --relay YOUR_RELAY:9009 receive /path/to/destination
```

Use croc's native prompts to exchange its generated code. An operator can
provide `CROC_PASS` in the process environment for a private relay. Croc accepts
`CROC_SECRET` in the process environment as an alternative to entering the
pairing code interactively. Never commit these values. The adapter does not
enable automatic acceptance or overwriting.

The relay address is a croc TCP endpoint, not the existing Mach5 HTTPS URL.
The existing WebSocket server cannot relay croc traffic.

The hosted relay is `mach5.jvjsc.com:9009`, with transfer ports 9010–9013.
It runs as PM2 process `m5-croc` using `/root/match5/croc-v11.5.3/croc`.
Its relay credential is stored separately at `/root/match5/croc-relay.secret`
with mode 600 and supplied through `CROC_PASS`. PM2's saved process state also
contains that environment and must remain mode 600. The existing `m5` service
is separate. `pm2 restart m5-croc` restarts only croc; `pm2 stop m5-croc` stops
its relay. PM2 startup is enabled through the server's existing `pm2-root`
service. This runtime currently runs as root.

For a public-relay smoke test, supply `MACH5_TEST_RELAY` and `CROC_PASS` in the
test process environment. The test does not start a local relay in this mode.
Its output redacts test credentials. Neither the credential nor a transfer
code belongs in source control or shell history.
The smoke test allows 1,200 seconds by default; `MACH5_TEST_TIMEOUT` overrides
the total endpoint wait budget in seconds for slower connections.

## Reproducible smoke test

Validated on macOS ARM64 with croc 11.5.3 on September 21, 2026:
1,003 files and both directories matched exactly, with source contents
unchanged. The 16 MiB random file and 1,000 small files completed with the other
fixtures in 21.25 seconds including relay/client startup. This was a loopback
relay test, not an internet throughput measurement or a Windows test.

The official macOS ARM64 release archive was checked against its GitHub asset
SHA-256: `cfa99d0f669ab604a19e7ea7ddbd8993adb9eeff1ab8524c902c9c6f65491dff`.

```sh
python tests/croc_smoke.py /absolute/path/to/croc
```

This starts an isolated loopback relay and two real croc processes. It sends a
16 MiB random file, 1,000 small files, a Unicode filename, a zero-byte file, and
an empty directory. It compares every path and SHA-256 digest and checks the
source again. Test-only automatic acceptance applies solely to generated
fixtures. Temporary test processes are terminated even on failure.

The private public relay is deployed. A macOS-to-relay-to-macOS run established
four data connections but exceeded its original 600-second limit after the
large file and part of the small-file set arrived. A subsequent connection
attempts failed with `could not secure channel`; receiver diagnostics reported
`flate: corrupt input before offset 7` while decoding a message. Public completion and reliable
reconnection are not yet established; this is not a Windows test or a speed
claim. Croc's TCP ports also need to be permitted by the work network: the
existing HTTPS site does not tunnel these connections.

Remaining acceptance work: complete public self-hosted transfer, interruption/resumption,
Windows execution, browser UI integration, and mapping the requested receiver
approval flow to croc. Native croc pairing currently replaces the custom
six-digit handshake. Threading and transfer scheduling belong to croc; Python
does not create an unbounded worker per file.
