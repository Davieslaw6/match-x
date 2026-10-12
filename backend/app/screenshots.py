import hashlib, io, secrets
from decimal import Decimal
from pathlib import Path
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import select
from .ai.tools import ResolveIn, resolve_team
from .config import settings
from .models_data import Fixture
from .models_extra import UploadedFile

MAX_BYTES, MAX_PIXELS, EXT = 8 * 1024 * 1024, 25_000_000, {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
def sniff(b: bytes):
    if b.startswith(b"\x89PNG\r\n\x1a\n"): return "PNG"
    if b.startswith(b"\xff\xd8\xff"): return "JPEG"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP": return "WEBP"

def clean(data: bytes):
    """Validate magic bytes, size and pixel limits, then re-encode to strip metadata."""
    if len(data) > MAX_BYTES: raise ValueError("file exceeds the 8 MB limit")
    fmt = sniff(data)
    if not fmt: raise ValueError("unsupported file type; use PNG, JPEG or WebP")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        if img.format != fmt: raise ValueError("file content does not match its type")
        w, h = img.size
        if w * h > MAX_PIXELS: raise ValueError("image dimensions are too large")  # checked before pixels are decoded
        img.load(); buf = io.BytesIO(); img.convert("RGB").save(buf, format=fmt)
    except (Image.DecompressionBombError, OSError, SyntaxError) as e: raise ValueError("invalid or oversized image") from e
    return buf.getvalue(), fmt, w, h

def store(db, data: bytes) -> UploadedFile:
    blob, fmt, w, h = clean(data); digest = hashlib.sha256(blob).hexdigest()
    row = db.scalar(select(UploadedFile).where(UploadedFile.sha256 == digest))
    if row: return row
    d = Path(settings.upload_dir); d.mkdir(parents=True, exist_ok=True, mode=0o700); name = f"{secrets.token_hex(16)}.{EXT[fmt]}"
    (d / name).write_bytes(blob); (d / name).chmod(0o600)
    row = UploadedFile(sha256=digest, stored_name=name, mime=fmt, width=w, height=h); db.add(row); db.commit(); return row

class Entry(BaseModel):
    home: str = Field(max_length=100); away: str = Field(max_length=100); market: str = Field(max_length=20); outcome: str = Field(max_length=40)
    odds: Decimal = Field(gt=1, le=10000, max_digits=9, decimal_places=3); booking_ref: str | None = Field(None, max_length=40)
    confidence: dict[str, float] = Field(default_factory=dict)
class Slip(BaseModel): entries: list[Entry] = Field(max_length=30)

class MockExtractor:
    """Test double. A real vision adapter (LLM or Tesseract) is not built."""
    def __init__(self, payload): self.payload = payload
    def extract(self, image: bytes) -> dict: return self.payload
_extractor = None
def get_extractor(): return _extractor

def match(db, slip: Slip):
    res = {"matched": [], "uncertain": [], "unmatched": []}
    for e in slip.entries:
        h, a = resolve_team(db, ResolveIn(query=e.home)), resolve_team(db, ResolveIn(query=e.away)); item = {**e.model_dump(mode="json")}
        if "none" in (h["status"], a["status"]): item["reason"] = "team not found"; res["unmatched"].append(item); continue
        if h["status"] != "match" or a["status"] != "match":
            item["reason"] = "ambiguous team"; item["candidates"] = h.get("candidates", []) + a.get("candidates", []); res["uncertain"].append(item); continue
        fx = db.scalar(select(Fixture).where(Fixture.home_team_id == h["team_id"], Fixture.away_team_id == a["team_id"], Fixture.status == "scheduled").order_by(Fixture.kickoff_utc))
        low = [k for k, v in e.confidence.items() if v < 0.6]
        if fx is None or low: item["reason"] = "no upcoming fixture found" if fx is None else f"low confidence: {', '.join(low)}"; res["uncertain"].append(item); continue
        item["fixture_id"] = fx.id; res["matched"].append(item)
    return res
