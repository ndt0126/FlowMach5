"""Command-line encrypted sender/receiver transport over the Mach5 relay."""
from __future__ import annotations
import argparse, asyncio, base64, json, os, ssl
from dataclasses import asdict
from pathlib import Path
from urllib.request import Request, urlopen
import websockets
import certifi
from mach5.client.receiver import Receiver
from mach5.filesystem.manifest import CHUNK_SIZE, Entry, scan
from mach5.security.channel import Channel, Handshake

def pack(value: dict) -> bytes: return json.dumps(value, separators=(",", ":")).encode()
def unpack(value: bytes) -> dict: return json.loads(value)
def tls_context() -> ssl.SSLContext: return ssl.create_default_context(cafile=certifi.where())

def create_sharing(endpoint: str, enrollment_token: str, summary: str) -> str:
    """Create an opaque relay record and return a pasteable invitation URL.

    The path summary lives in the fragment, so normal HTTP requests and proxy
    logs receive neither it nor any future invitation key material.
    """
    request = Request(endpoint.rstrip("/") + "/v1/sharings", method="POST", headers={"Authorization": f"Bearer {enrollment_token}"})
    with urlopen(request, timeout=15) as response:
        sharing_id = json.loads(response.read())["id"]
    return endpoint.rstrip("/") + f"/s/{sharing_id}#v1.{summary}"

async def sender(url: str, sharing: str, source: Path, approval: str | None) -> None:
    entries, _, digest = scan(source); index = {e.path: e for e in entries}
    hs = Handshake.create()
    async with websockets.connect(f"{url.rstrip('/')}/{sharing}/sender", max_size=2*1024*1024, ssl=tls_context()) as ws:
        await ws.send("hello:" + base64.urlsafe_b64encode(hs.public()).decode())
        async for frame in ws:
            if isinstance(frame, str) and frame.startswith("hello:"):
                key, code = hs.derive(base64.urlsafe_b64decode(frame[6:])); print(f"Receiver confirmation code: {code}")
                if approval is None: approval = input("Enter the receiver code to approve: ").replace(" ", "")
                if approval != code: raise RuntimeError("approval code did not match receiver")
                await ws.send("approve:" + code); break
        s2r, r2s = Channel(key, b"s2r"), Channel(key, b"r2s")
        await ws.send(s2r.seal(pack({"t":"manifest", "id":digest, "entries":[asdict(e) for e in entries], "wrapper":source.name})))
        while True:
            request = unpack(r2s.open(await ws.recv()))
            if request["t"] == "get":
                entry = index.get(request["path"])
                if not entry or entry.kind != "file": raise RuntimeError("invalid receiver request")
                path = source / entry.path if source.is_dir() else source
                with path.open("rb") as f:
                    offset = 0
                    while block := f.read(CHUNK_SIZE):
                        await ws.send(s2r.seal(pack({"t":"chunk","p":entry.path,"o":offset,"d":base64.b64encode(block).decode()})))
                        ack = unpack(r2s.open(await ws.recv()))
                        if ack != {"t": "ack", "p": entry.path, "o": offset}:
                            raise RuntimeError("invalid receiver acknowledgement")
                        offset += len(block)
                await ws.send(s2r.seal(pack({"t":"end","p":entry.path})))
            elif request["t"] == "done": return

async def receiver(url: str, sharing: str, destination: Path) -> None:
    hs = Handshake.create()
    async with websockets.connect(f"{url.rstrip('/')}/{sharing}/receiver", max_size=2*1024*1024, ssl=tls_context()) as ws:
        await ws.send("hello:" + base64.urlsafe_b64encode(hs.public()).decode())
        async for frame in ws:
            if isinstance(frame, str) and frame.startswith("hello:"):
                key, code = hs.derive(base64.urlsafe_b64decode(frame[6:])); print(f"Enter this code on sender: {code}"); break
        s2r, r2s = Channel(key, b"s2r"), Channel(key, b"r2s")
        while True:
            frame = await ws.recv()
            if frame == "approved": break
        manifest = unpack(s2r.open(await ws.recv()))
        entries = [Entry(**e) for e in manifest["entries"]]; receive = Receiver(destination, manifest["wrapper"], entries, manifest["id"])
        try:
            for entry in entries:
                if entry.kind != "file": continue
                await ws.send(r2s.seal(pack({"t":"get", "path":entry.path})))
                while True:
                    event = unpack(s2r.open(await ws.recv()))
                    if event["t"] == "chunk":
                        receive.write_chunk(event["p"], event["o"], base64.b64decode(event["d"]))
                        await ws.send(r2s.seal(pack({"t":"ack", "p":event["p"], "o":event["o"]})))
                    elif event["t"] == "end": receive.finalize(event["p"]); break
            if not receive.complete(): raise RuntimeError("transfer incomplete")
            await ws.send(r2s.seal(pack({"t":"done"})))
        finally: receive.close()

def main() -> None:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(required=True, dest="cmd"); s=sub.add_parser("send"); r=sub.add_parser("receive"); c=sub.add_parser("create")
    for q in (s,r): q.add_argument("--relay", required=True); q.add_argument("--sharing", required=True)
    s.add_argument("--source", type=Path, required=True); s.add_argument("--approve"); r.add_argument("--destination", type=Path, required=True)
    c.add_argument("--source", type=Path, required=True); c.add_argument("--endpoint", required=True)
    a=p.parse_args()
    if a.cmd == "create":
        token = os.environ.get("MACH5_ENROLLMENT_TOKEN")
        if not token: p.error("MACH5_ENROLLMENT_TOKEN must be set locally to create a sharing")
        _, summary, _ = scan(a.source); print(create_sharing(a.endpoint, token, summary.encode())); return
    asyncio.run(sender(a.relay,a.sharing,a.source,a.approve) if a.cmd=="send" else receiver(a.relay,a.sharing,a.destination))

if __name__ == "__main__": main()
