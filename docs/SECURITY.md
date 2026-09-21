# Security status

This repository supplies a bounded, TLS-protected blind relay and local
asynchronous source scanning. The relay accepts one sender and one receiver
per opaque sharing ID. Each endpoint generates an ephemeral X25519 key, derives
a session key through HKDF, and displays a six-digit out-of-band confirmation
derived from that shared secret. The sender must enter that exact receiver code
before the relay forwards encrypted frames. IDs have 256 bits of random entropy
and expire after 24 hours. New sharing creation needs a provisioned enrollment
token.

Payload frames use ChaCha20-Poly1305 and the relay cannot read the manifest or
file bytes. The short code is confirmation only, not a cryptographic key.
This remains a prototype: its custom pairing protocol has not received an
independent security audit, and robust reconnect/revocation semantics are not
complete. Do not use it for sensitive files yet.

Scanning follows no symlinks and rejects special files. It hashes files while
checking size/mtime stability. Python cannot provide an OS-enforced guarantee
that a process with the user’s permissions will never mutate a source; this
prototype intentionally contains no source mutation APIs.
