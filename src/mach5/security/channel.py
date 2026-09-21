"""X25519/HKDF/ChaCha20-Poly1305 session primitives.

The six-digit code is an out-of-band key confirmation derived from the same
shared secret; it is never used as encryption material.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

CONTEXT = b"mach5-v1/x25519-channel"

@dataclass
class Handshake:
    private: X25519PrivateKey
    @classmethod
    def create(cls) -> "Handshake": return cls(X25519PrivateKey.generate())
    def public(self) -> bytes: return self.private.public_key().public_bytes_raw()
    def derive(self, peer: bytes) -> tuple[bytes, str]:
        shared = self.private.exchange(X25519PublicKey.from_public_bytes(peer))
        material = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=CONTEXT).derive(shared)
        code = int.from_bytes(hmac.new(material, b"confirm", hashlib.sha256).digest()[:4], "big") % 1_000_000
        return material, f"{code:06d}"

class Channel:
    def __init__(self, key: bytes, direction: bytes) -> None:
        self.aead = ChaCha20Poly1305(key); self.prefix = hashlib.sha256(CONTEXT + direction).digest()[:4]; self.counter = 0
    def seal(self, plaintext: bytes) -> bytes:
        if self.counter >= 2**64: raise ValueError("nonce exhausted")
        nonce = self.prefix + self.counter.to_bytes(8, "big"); self.counter += 1
        return nonce + self.aead.encrypt(nonce, plaintext, CONTEXT)
    def open(self, frame: bytes) -> bytes:
        if len(frame) < 12 + 16 or frame[:4] != self.prefix: raise ValueError("invalid encrypted frame")
        return self.aead.decrypt(frame[:12], frame[12:], CONTEXT)
