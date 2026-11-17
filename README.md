# unredact.tools — onion edition

A stripped-down front end for the unredact.tools scanner: **no JavaScript, no
cookies, no external assets**. Every page is one self-contained HTML document
with inline CSS, so it loads in a single request on a slow Tor circuit and
works in `w3m` and `lynx`.

Served only on the Tor hidden service; the clearnet app keeps its richer UI.

## Pages

| route | what it does |
|---|---|
| `GET /` | upload form (file + fast-scan toggle) |
| `POST /scan` | server-rendered report: facts, findings, findability meter, clean form |
| `POST /clean` | sanitize + re-scan, returns a one-shot download link |
| `GET /download/<token>` | serves the cleaned file once, then deletes the session |
| `GET /about` | what it checks, privacy, limits |

## Run

```bash
cd ~/apps/unredact-onion
uv venv && uv sync          # or: python -m venv .venv && pip install -e ".[web,vision]" ../unredact.tools
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8011 --no-access-log
```

Open <http://127.0.0.1:8011/>.

## Deploy on the hidden service

`/etc/tor/torrc`:

```
HiddenServiceDir /var/lib/tor/unredact_tools/
HiddenServicePort 80 127.0.0.1:8011
```

Then install the unit and restart Tor:

```bash
sudo cp deploy/unredact-onion.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now unredact-onion.service
sudo systemctl restart tor.service
```

## Storage model

Scans need the upload twice — once to report, once to clean — so the file is
parked in a `0700` directory under the service's private `/tmp` for at most
`SESSION_TTL` (300 s). It is deleted when the cleaned copy is downloaded, when
the session expires, or when the service restarts. Scan-only uploads are never
written anywhere else, and nothing is logged.
