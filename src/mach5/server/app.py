"""Blind, bounded WebSocket rendezvous relay.

Payload frames are forwarded only between a sender and its single approved
receiver. This service deliberately has no filesystem payload storage.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect

ROLE = Literal["sender", "receiver"]
MAX_FRAME = 2 * 1024 * 1024
EXPIRY_SECONDS = 24 * 60 * 60

@dataclass
class Sharing:
    token: str
    expires_at: float
    sender: WebSocket | None = None
    receiver: WebSocket | None = None
    approval_code: str | None = None
    approved: bool = False
    hellos: dict[str, str] = field(default_factory=dict)

class Registry:
    def __init__(self) -> None: self.items: dict[str, Sharing] = {}
    def create(self) -> Sharing:
        token = secrets.token_urlsafe(32); item = Sharing(token, time.time() + EXPIRY_SECONDS)
        self.items[token] = item; return item
    def get(self, token: str) -> Sharing:
        item = self.items.get(token)
        if not item or item.expires_at < time.time():
            self.items.pop(token, None); raise HTTPException(404, "sharing unavailable")
        return item

registry = Registry()
app = FastAPI(title="Mach5 relay", docs_url=None, redoc_url=None)

@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok", "protocol": "1"}

@app.post("/v1/sharings")
def create_sharing(authorization: str | None = Header(default=None)) -> dict[str, object]:
    expected = os.environ.get("MACH5_ENROLLMENT_TOKEN")
    if not expected or not secrets.compare_digest(authorization or "", f"Bearer {expected}"):
        raise HTTPException(401, "enrollment required")
    item = registry.create()
    return {"id": item.token, "expires_at": int(item.expires_at)}

@app.websocket("/ws/{sharing_id}/{role}")
async def relay(websocket: WebSocket, sharing_id: str, role: ROLE) -> None:
    if role not in ("sender", "receiver"): await websocket.close(1008); return
    try: item = registry.get(sharing_id)
    except HTTPException: await websocket.close(1008); return
    await websocket.accept()
    if getattr(item, role) is not None: await websocket.close(1008); return
    setattr(item, role, websocket)
    peer = item.receiver if role == "sender" else item.sender
    other_role = "receiver" if role == "sender" else "sender"
    if peer and other_role in item.hellos: await websocket.send_text(item.hellos[other_role])
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect": break
            data = message.get("bytes") or message.get("text", "")
            if len(data) > MAX_FRAME: await websocket.close(1009); break
            if role == "sender" and isinstance(data, str) and data.startswith("approve:"):
                if len(data) == 14 and data[8:].isdigit():
                    item.approved = True
                    if item.receiver: await item.receiver.send_text("approved")
                continue
            peer = item.receiver if role == "sender" else item.sender
            # Public keys are harmless but must be bounded; all later frames are E2E encrypted.
            handshake = isinstance(data, str) and data.startswith("hello:") and len(data) <= 128
            if handshake: item.hellos[role] = data
            if peer and (item.approved or handshake):
                if isinstance(data, bytes): await peer.send_bytes(data)
                else: await peer.send_text(data)
    except WebSocketDisconnect: pass
    finally:
        if getattr(item, role) is websocket: setattr(item, role, None)

def main() -> None:
    import uvicorn
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", type=int, default=8751)
    args = parser.parse_args(); uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
