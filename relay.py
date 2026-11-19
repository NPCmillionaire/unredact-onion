"""Talk to the clearnet app on behalf of the onion edition.

Two things cross over, and nothing else:
  - the shared totals (files checked / files scrubbed): a bump after each scan
    or clean, and a cached read for the home page
  - contact-form messages, which the clearnet app emails to the site owner

Both need UNREDACT_RELAY_TOKEN (the clearnet app's shared secret). Without it
the totals stay hidden and the contact form says to use email instead.

Env:
  UNREDACT_UPSTREAM      clearnet base URL (default https://unredact.tools)
  UNREDACT_RELAY_TOKEN   shared secret, same value as on the clearnet app
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

UPSTREAM = os.environ.get("UNREDACT_UPSTREAM", "https://unredact.tools").rstrip("/")
TOKEN = os.environ.get("UNREDACT_RELAY_TOKEN", "").strip()
TIMEOUT = 8
TOTALS_TTL = 60  # seconds the home page reuses a totals read
CONTACT_LIMIT = 20  # messages per hour across all onion visitors (they share no IP)

_totals: tuple[float, dict | None] = (0.0, None)
_sent: list[float] = []


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # we read the Location ourselves
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _post(path: str, data: dict | None = None):
    body = urllib.parse.urlencode(data or {}).encode()
    req = urllib.request.Request(UPSTREAM + path, data=body, method="POST", headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "unredact-onion",
    })
    try:
        return _opener.open(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as exc:  # a 303 lands here once redirects are off
        return exc


def bump(kind: str) -> None:
    """Add one to a shared total. Runs after the response; failures are ignored."""
    if not TOKEN:
        return
    try:
        _post(f"/api/totals/{kind}").close()
    except OSError:
        pass


def totals() -> dict | None:
    """The shared totals, cached for a minute, or None when unavailable."""
    global _totals
    at, value = _totals
    if time.time() - at < TOTALS_TTL:
        return value
    value = None
    if TOKEN:
        try:
            req = urllib.request.Request(UPSTREAM + "/api/info",
                                         headers={"User-Agent": "unredact-onion"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                value = json.load(r).get("totals")
        except (OSError, ValueError):
            pass
    _totals = (time.time(), value)
    return value


def contact(name: str, email: str, topic: str, message: str) -> str:
    """Relay a contact message. Returns "sent" or an error code the page explains."""
    if not TOKEN:
        return "off"
    now = time.time()
    _sent[:] = [t for t in _sent if t > now - 3600]
    if len(_sent) >= CONTACT_LIMIT:
        return "busy"
    _sent.append(now)
    try:
        r = _post("/api/contact", {"name": name, "email": email, "topic": topic,
                                   "message": "(sent from the onion mirror)\n\n" + message})
        where = r.headers.get("Location", "")
        r.close()
    except OSError:
        return "send"
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(where).query, keep_blank_values=True)
    if "sent" in q:
        return "sent"
    return (q.get("error") or ["send"])[0]
