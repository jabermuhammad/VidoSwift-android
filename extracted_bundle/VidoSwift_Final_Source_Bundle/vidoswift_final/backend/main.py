from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

APP_VERSION = "1.0.0"
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
JOB_SEMAPHORE = asyncio.Semaphore(max(1, MAX_CONCURRENT_JOBS))

app = FastAPI(title="VidoSwift API", version=APP_VERSION, description="Video metadata and authorized downloads for VidoSwift Download Studio")
allowed_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4096)

QUALITY_HEIGHTS = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080, "1440p": 1440, "2160p": 2160}

def validate_public_url(raw: str) -> str:
    raw = raw.strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Enter a valid http or https video URL.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise HTTPException(status_code=400, detail="Local network URLs are not supported.")
    try:
        # Block direct IPs and DNS names resolving to local/private addresses (SSRF protection).
        addresses = {ipaddress.ip_address(host)} if _is_ip(host) else {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        if not addresses or any(not addr.is_global for addr in addresses):
            raise HTTPException(status_code=400, detail="Private or local network URLs are not supported.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="The URL host could not be resolved.")
    return raw

def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False

def ydl_options(**extra):
    return {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 20, "retries": 2, "fragment_retries": 2, "extractor_retries": 1, "ignoreerrors": False, "restrictfilenames": True, **extra}

def _extract(url: str) -> dict:
    try:
        with yt_dlp.YoutubeDL(ydl_options(skip_download=True, extract_flat=False)) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as exc:
        message = str(exc)
        # Keep responses helpful without leaking a full traceback or server paths.
        if "Unsupported URL" in message:
            detail = "This website or URL format is not supported by the current yt-dlp version."
        elif any(k in message.lower() for k in ("private video", "login", "sign in", "cookies")):
            detail = "This video may require sign-in or cookies, which this server does not currently receive."
        elif "429" in message or "too many requests" in message.lower():
            detail = "The source is rate-limiting requests. Please wait and retry."
        else:
            detail = "Could not read this video. The source may be unavailable, restricted, or unsupported."
        raise HTTPException(status_code=422, detail=detail) from exc

def _format_options(info: dict) -> list[dict]:
    available_heights = []
    for f in info.get("formats") or []:
        h = f.get("height")
        if h and (f.get("vcodec") or "none") != "none":
            available_heights.append(int(h))
    if not available_heights:
        # Some extractors expose a single top-level format without a formats list.
        h = info.get("height")
        if h:
            available_heights.append(int(h))
    max_height = max(available_heights, default=720)
    candidates = [h for h in QUALITY_HEIGHTS.values() if h <= max_height]
    if not candidates:
        candidates = [360]
    formats = []
    for height in candidates:
        formats.append({"id": f"{height}p", "label": f"{height}p", "quality": f"{height}p", "detail": "MP4 · Video + audio", "ext": "mp4", "filesize": _estimate_size(info, height)})
    # A source with only very low resolution still gets one sensible best-available option.
    if not formats:
        formats = [{"id": "best", "label": "Best available", "quality": "best", "detail": "Source quality", "ext": "mp4", "filesize": None}]
    return formats

def _estimate_size(info: dict, height: int):
    for f in sorted(info.get("formats") or [], key=lambda x: x.get("height") or 0, reverse=True):
        if f.get("height") and f.get("height") <= height and (f.get("vcodec") or "none") != "none":
            return f.get("filesize") or f.get("filesize_approx")
    return info.get("filesize") or info.get("filesize_approx")

@app.get("/")
def root():
    return {"service": "VidoSwift API", "version": APP_VERSION, "health": "/v1/health"}

@app.get("/v1/health")
def health():
    return {"status": "ok", "service": "vidoswift-api", "version": APP_VERSION}

@app.head("/v1/health")
def health_head():
    return Response(status_code=200, headers={"X-Service-Status": "ok"})

@app.post("/v1/analyze")
async def analyze(body: AnalyzeRequest):
    url = validate_public_url(body.url)
    async with JOB_SEMAPHORE:
        info = await asyncio.to_thread(_extract, url)
    return {
        "title": info.get("title") or "Video",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader") or info.get("channel"),
        "webpage_url": info.get("webpage_url") or url,
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "formats": _format_options(info),
    }

@app.get("/v1/download")
async def download(url: str = Query(min_length=8, max_length=4096), quality: str = Query(default="720p", max_length=16)):
    url = validate_public_url(url)
    if quality not in {*QUALITY_HEIGHTS.keys(), "best"}:
        raise HTTPException(status_code=400, detail="Unsupported quality option.")
    temp_dir = Path(tempfile.mkdtemp(prefix="vidoswift-"))
    outtmpl = str(temp_dir / "%(title).120B-%(id)s.%(ext)s")
    if quality == "best":
        selector = "best[ext=mp4]/best"
    else:
        h = QUALITY_HEIGHTS[quality]
        # Prefer MP4 streams; fall back to best available under the chosen height.
        selector = f"best[height<={h}][ext=mp4]/best[height<={h}]/best[ext=mp4]/best"
    opts = ydl_options(format=selector, outtmpl=outtmpl, noplaylist=True, merge_output_format="mp4", continuedl=True, progress=False)
    try:
        async with JOB_SEMAPHORE:
            await asyncio.to_thread(_download_to_temp, url, opts)
        files = [p for p in temp_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl", ".json"))]
        media = [p for p in files if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v"}]
        if not media:
            raise HTTPException(status_code=422, detail="The source did not produce a playable video file. The server may need FFmpeg for this format.")
        path = max(media, key=lambda p: p.stat().st_size)
        suffix = path.suffix.lower()
        media_type = {".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska", ".mov": "video/quicktime", ".m4v": "video/mp4"}.get(suffix, "application/octet-stream")
        safe_name = re.sub(r"[^A-Za-z0-9._ -]", "", path.stem).strip().replace(" ", "_")[:100] or "vidoswift-video"
        return FileResponse(path, media_type=media_type, filename=f"{safe_name}{suffix}", background=BackgroundTask(_cleanup, temp_dir))
    except HTTPException:
        _cleanup(temp_dir)
        raise
    except Exception as exc:
        _cleanup(temp_dir)
        message = str(exc).lower()
        if "ffmpeg" in message:
            detail = "This format needs FFmpeg, which is not installed on the backend. Install FFmpeg and redeploy."
        elif "429" in message or "too many requests" in message:
            detail = "The source is rate-limiting downloads. Please wait and retry."
        else:
            detail = "The download failed. The source may block server downloads or the selected format may no longer be available."
        raise HTTPException(status_code=422, detail=detail) from exc

def _download_to_temp(url: str, opts: dict):
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

def _cleanup(path: Path):
    try:
        for child in path.iterdir():
            try:
                child.unlink(missing_ok=True)
            except OSError:
                pass
        path.rmdir()
    except OSError:
        pass
