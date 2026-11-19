"""End-to-end checks for the onion edition, run in-process with no Tor needed.

uv run pytest -q
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as onion

SAMPLE = (Path(__file__).resolve().parents[2] / "unredact.tools"
          / "site" / "sample" / "vacation.jpg")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(onion, "ROOT", tmp_path / "sessions")
    with TestClient(onion.app) as c:
        yield c


def token(html: str) -> str:
    m = re.search(r'name="token" value="([^"]+)"', html)
    assert m, "no session token in report"
    return m.group(1)


def link(html: str) -> str:
    m = re.search(r'href="/download/([^"]+)"', html)
    assert m, "no download link"
    return m.group(1)


def test_home(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<script" not in r.text
    assert "unred42id" in r.text
    assert 'href="/pgp.txt"' in r.text
    assert r.headers["content-security-policy"].startswith("default-src 'none'")
    assert r.headers["cache-control"] == "no-store"


def test_pgp(client):
    r = client.get("/pgp.txt")
    assert r.status_code == 200
    assert "BEGIN PGP PUBLIC KEY BLOCK" in r.text


def test_missing_file_is_html(client):
    r = client.post("/scan")
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("text/html")
    assert "incomplete" in r.text


def test_scan_clean_download(client):
    r = client.post("/scan", files={"file": ("vacation.jpg", SAMPLE.read_bytes(),
                                             "image/jpeg")})
    assert r.status_code == 200
    assert "CRITICAL" in r.text
    tok = token(r.text)

    r = client.post("/clean", data={"token": tok, "redact_text": "true",
                                    "redact_codes": "true"})
    assert r.status_code == 200
    assert "findings" in r.text
    dl = link(r.text)

    r = client.get(f"/download/{dl}")
    assert r.status_code == 200
    assert r.content[:2] == b"\xff\xd8"  # JPEG
    assert "clean" in r.headers["content-disposition"]

    assert client.get(f"/download/{dl}").status_code == 404  # one-shot
    assert not list(onion.ROOT.iterdir())  # session dir removed


def test_upload_with_clean_in_name(client):
    """A filename containing '.clean' must not be mistaken for the output."""
    payload = {"file": ("report.clean.jpg", SAMPLE.read_bytes(), "image/jpeg")}
    r = client.post("/scan", files=payload)
    assert r.status_code == 200
    tok = token(r.text)
    r = client.post("/clean", data={"token": tok})
    assert r.status_code == 200
    r = client.get(f"/download/{link(r.text)}")
    assert r.status_code == 200
    assert r.content[:2] == b"\xff\xd8"
    assert len(r.content) < len(SAMPLE.read_bytes())  # cleaned, not the original


def test_bad_token(client):
    for bad in ("../etc", "..", "missing"):
        r = client.post("/clean", data={"token": bad})
        assert r.status_code in (400, 404)
        assert r.headers["content-type"].startswith("text/html")


def test_sweep(client):
    onion.ROOT.mkdir(parents=True, exist_ok=True)
    old = onion.ROOT / "old"
    new = onion.ROOT / "new"
    old.mkdir()
    new.mkdir()
    past = time.time() - onion.SESSION_TTL - 10
    os.utime(old, (past, past))
    onion._sweep()
    assert not old.exists()
    assert new.exists()


def test_new_pages(client):
    for path in ("/contact", "/donate", "/about"):
        r = client.get(path)
        assert r.status_code == 200 and "<script" not in r.text
        assert 'href="/donate"' in r.text
    assert "bc1q8hdtgw3f8fan587ey3jqy073d0wv2k07vu98d9" in client.get("/donate").text


def test_contact_relays(client, monkeypatch):
    seen = []
    monkeypatch.setattr(onion.relay, "contact", lambda *a: seen.append(a) or "sent")
    r = client.post("/contact", data={"name": "A", "topic": "bug", "message": "hi"})
    assert "message was sent" in r.text and seen[0][2:] == ("bug", "hi")
    assert "write a message" in client.post("/contact", data={"message": " "}).text
    assert "message was sent" in client.post("/contact", data={"message": "x", "website": "b"}).text
    assert len(seen) == 1  # blank message and honeypot never reach the relay


def test_totals_shown_only_when_large(client, monkeypatch):
    monkeypatch.setattr(onion.relay, "totals", lambda: {"checked": 99, "scrubbed": 5})
    assert "files checked" not in client.get("/").text
    monkeypatch.setattr(onion.relay, "totals", lambda: {"checked": 1500, "scrubbed": 120})
    assert "1,500</b> files checked · <b>120</b> scrubbed" in client.get("/").text


def test_scan_and_clean_bump_totals(client, monkeypatch):
    bumps = []
    monkeypatch.setattr(onion.relay, "bump", bumps.append)
    r = client.post("/scan", files={"file": ("vacation.jpg", SAMPLE.read_bytes(), "image/jpeg")})
    client.post("/clean", data={"token": token(r.text)})
    assert bumps == ["checked", "scrubbed"]


def test_relay_contact_reads_redirect(monkeypatch):
    class Resp:
        def __init__(self, loc): self.headers = {"Location": loc}
        def close(self): pass
    monkeypatch.setattr(onion.relay, "TOKEN", "t")
    monkeypatch.setattr(onion.relay, "_sent", [])
    monkeypatch.setattr(onion.relay, "_post", lambda p, d=None: Resp("/contact?sent#form"))
    assert onion.relay.contact("", "", "general", "hi") == "sent"
    monkeypatch.setattr(onion.relay, "_post", lambda p, d=None: Resp("/contact?error=invalid#form"))
    assert onion.relay.contact("", "", "general", "hi") == "invalid"
    monkeypatch.setattr(onion.relay, "TOKEN", "")
    assert onion.relay.contact("", "", "general", "hi") == "off"
