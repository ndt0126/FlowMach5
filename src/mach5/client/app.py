"""Loopback-only controller for asynchronous immutable source scans."""
from __future__ import annotations

import argparse
import asyncio
import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from mach5.filesystem.manifest import ManifestError, scan

@dataclass
class Card:
    id: str
    source: Path
    state: str = "scanning"
    error: str | None = None
    files: int = 0
    bytes: int = 0
    manifest_digest: str | None = None
    summary: str | None = None

cards: dict[str, Card] = {}
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mach5-scan")
app = FastAPI(title="Mach5 local", docs_url=None, redoc_url=None)

class SourceRequest(BaseModel): path: str

async def prepare(card: Card) -> None:
    try:
        entries, summary, digest = await asyncio.get_running_loop().run_in_executor(pool, scan, card.source)
        card.files = sum(e.kind == "file" for e in entries); card.bytes = sum(e.size for e in entries)
        card.manifest_digest, card.summary, card.state = digest, summary.encode(), "ready"
    except (ManifestError, OSError) as exc: card.state, card.error = "scan_failed", str(exc)

@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}

@app.get("/api/sharings")
def list_cards() -> list[dict]:
    return [{**asdict(card), "source": str(card.source)} for card in cards.values()]

@app.post("/api/sharings", status_code=202)
async def add_source(request: SourceRequest) -> dict[str, str]:
    source = Path(request.path).expanduser()
    if not source.exists(): raise HTTPException(400, "source does not exist")
    card = Card(secrets.token_urlsafe(12), source); cards[card.id] = card
    asyncio.create_task(prepare(card)); return {"id": card.id}

@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return '''<!doctype html><title>Mach5</title><h1>Mach5</h1><p>Choose a file or folder path. Each submission becomes an independent sharing.</p><input id=p placeholder="/path/to/source"><button onclick="add()">Prepare sharing</button><pre id=o></pre><script>async function add(){await fetch('/api/sharings',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({path:p.value})});}async function refresh(){o.textContent=JSON.stringify(await (await fetch('/api/sharings')).json(),null,2)}setInterval(refresh,750);refresh()</script>'''

def main() -> None:
    import uvicorn
    parser = argparse.ArgumentParser(); parser.add_argument("--port", type=int, default=8750)
    args = parser.parse_args(); uvicorn.run(app, host="127.0.0.1", port=args.port)

if __name__ == "__main__":
    main()
