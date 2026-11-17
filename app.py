"""unredact.tools — onion edition.

A no-JavaScript, text-first front end for the unredact.tools scanner. Meant to
be served only from a Tor hidden service (127.0.0.1:8011), so the clearnet app
keeps its richer UI while onion visitors get something that loads in one request
and works in w3m/lynx.

Flow:  GET /        form
       POST /scan   report (file parked in a private session dir)
       POST /clean  sanitize + re-scan, then a link
       GET /download/<token>  serve once, delete

Privacy: sessions live under a 0700 dir in the service's private /tmp, expire
after SESSION_TTL seconds, and are swept on every request. The download route
deletes the session as soon as the file has been sent.
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from starlette.background import BackgroundTask
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from unredact_tools.image import VisualOpts
from unredact_tools.scanner import sanitize, scan
# shared limits and helpers so the two front ends behave the same
from unredact_tools.web.app import HINTS, MAX_MB, WORKERS, _safe_name

import render

SESSION_TTL = 300  # seconds an upload is kept so it can be cleaned
ROOT = Path(tempfile.gettempdir()) / "unredact-onion"
PGP_KEY = Path(__file__).resolve().parent / "pgp.asc"

app = FastAPI(title="unredact.tools onion", docs_url=None, redoc_url=None,
              openapi_url=None)


@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'")
    return resp


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _sweep() -> None:
    """Drop sessions past their TTL; keep the directory from growing."""
    try:
        entries = sorted(ROOT.iterdir(), key=_mtime)
    except FileNotFoundError:
        return
    now = time.time()
    for i, p in enumerate(entries):
        if now - _mtime(p) > SESSION_TTL or len(entries) - i > 64:
            shutil.rmtree(p, ignore_errors=True)


def _session(name: str) -> tuple[str, Path]:
    _sweep()
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    d = ROOT / token
    d.mkdir(mode=0o700)
    (d / "session.json").write_text(json.dumps({"src": name}), encoding="utf-8")
    return token, d / name


def _dir(token: str) -> Path:
    if not token or "/" in token or token.startswith("."):
        raise HTTPException(400, "bad session")
    d = ROOT / token
    if not d.is_dir():
        raise HTTPException(404, "that upload expired — scan the file again")
    return d


def _meta(d: Path) -> dict:
    try:
        value = json.loads((d / "session.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _member(d: Path, name: object) -> Path | None:
    """Resolve a bare filename inside the session dir; reject anything else."""
    if not isinstance(name, str) or not name or "/" in name or name.startswith("."):
        return None
    return d / name


async def _save(upload: UploadFile, dest: Path) -> int:
    limit, size = MAX_MB * 1024 * 1024, 0
    try:
        with open(dest, "wb") as out:
            while chunk := await upload.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"file is over the {MAX_MB} MB limit")
                out.write(chunk)
    except BaseException:
        shutil.rmtree(dest.parent, ignore_errors=True)
        raise
    if size == 0:
        shutil.rmtree(dest.parent, ignore_errors=True)
        raise HTTPException(400, "empty file")
    return size


@app.get("/", response_class=HTMLResponse)
def home():
    return render.home()


@app.get("/about", response_class=HTMLResponse)
def about():
    return render.about()


@app.get("/pgp.txt", response_class=PlainTextResponse)
def pgp_key():
    """Site contact / release-signing key, linked from every page footer."""
    if not PGP_KEY.is_file():
        raise HTTPException(404, "no pgp key published")
    return PGP_KEY.read_text(encoding="utf-8")


@app.post("/scan", response_class=HTMLResponse)
async def do_scan(file: UploadFile = File(...), fast: bool = Form(False)):
    name = _safe_name(file.filename)
    token, path = _session(name)
    try:
        await _save(file, path)
        async with WORKERS:
            report = await run_in_threadpool(scan, str(path), not fast, not fast)
    except BaseException:
        shutil.rmtree(path.parent, ignore_errors=True)
        raise
    hints = sorted({opt for f in report.findings
                    for key, opt in HINTS.items() if key in f.title})
    return render.report(report, name, token, hints)


@app.post("/clean", response_class=HTMLResponse)
async def do_clean(
    token: str = Form(""),
    pdf_mode: str = Form("raster"),
    blur_faces: bool = Form(False),
    redact_codes: bool = Form(False),
    redact_text: bool = Form(False),
    redact_plates: bool = Form(False),
    desync: bool = Form(False),
    keep_dots: bool = Form(False),
):
    if pdf_mode not in ("raster", "text"):
        raise HTTPException(400, "pdf_mode must be raster or text")
    d = _dir(token)
    src = _member(d, _meta(d).get("src"))
    if src is None or not src.is_file():
        raise HTTPException(404, "that upload expired — scan the file again")

    opts = VisualOpts(blur_faces=blur_faces, redact_codes=redact_codes,
                      redact_text=redact_text, redact_plates=redact_plates,
                      desync=desync, remove_dots=not keep_dots)
    notes: list[str] = []

    def work():
        before = scan(str(src))
        out = sanitize(str(src), None, pdf_mode=pdf_mode, visual=opts, notes=notes)
        return before, out, scan(out)

    try:
        async with WORKERS:
            before, out, after = await run_in_threadpool(work)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc))

    meta = _meta(d)
    meta["clean"] = Path(out).name
    (d / "session.json").write_text(json.dumps(meta), encoding="utf-8")

    remaining = [f for f in after.sorted_findings()
                 if f.severity != "info" and f.category != "structure"]
    before_n = sum(1 for f in before.findings if f.severity != "info")
    return render.cleaned(src.name, Path(out).name, before_n, len(remaining),
                          remaining, notes, token)


@app.get("/download/{token}")
def download(token: str):
    d = _dir(token)
    out = _member(d, _meta(d).get("clean"))
    if out is None or not out.is_file():
        raise HTTPException(404, "nothing to download — scan and clean a file first")
    media = mimetypes.guess_type(out.name)[0] or "application/octet-stream"
    return FileResponse(out, filename=out.name, media_type=media,
                        background=BackgroundTask(shutil.rmtree, d, True))


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return HTMLResponse(render.error(exc.status_code, str(exc.detail)),
                        status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return HTMLResponse(render.error(400, "that form was incomplete — go back and upload a file"),
                        status_code=400)


@app.exception_handler(Exception)
async def crash(request: Request, exc: Exception):
    return HTMLResponse(render.error(500, "something went wrong on this file"),
                        status_code=500)
