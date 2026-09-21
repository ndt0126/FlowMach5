# Security status

This repository currently supplies a bounded, TLS-protected blind relay and
local asynchronous source scanning. The relay accepts one sender and one
receiver per opaque sharing ID; a receiver gets a six-digit out-of-band code,
which the sender must approve. IDs have 256 bits of random entropy and expire
after 24 hours. New sharing creation needs a provisioned enrollment token.

This is **not yet an end-to-end encrypted file transfer implementation**.
Payload frames are relayed after pairing, but client-side authenticated key
exchange, encrypted framing, durable receiver state, chunk recovery, and
revocation remain to be implemented. The short code is confirmation only, not
a cryptographic key. Do not use the prototype for sensitive files until an
audited PAKE or authenticated X25519 out-of-band design is integrated.

Scanning follows no symlinks and rejects special files. It hashes files while
checking size/mtime stability. Python cannot provide an OS-enforced guarantee
that a process with the user’s permissions will never mutate a source; this
prototype intentionally contains no source mutation APIs.
