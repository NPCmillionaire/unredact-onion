# unredact.tools — onion edition

A stripped-down front end for the unredact.tools scanner: **no JavaScript, no
cookies, no external assets**. Every page is one self-contained HTML document
with inline CSS, so it loads in a single request on a slow Tor circuit and
works in `w3m` and `lynx`.

Served only on the Tor hidden service; the clearnet app keeps its richer UI.
Source: **<https://github.com/NPCmillionaire/unredact-onion>** — the scanner
itself is [unredact.tools](https://github.com/NPCmillionaire/unredact.tools).

## Onion addresses

All four vanity keys for this service live in `~/onion-keys-undredact/`:

| address | status |
|---|---|
| `unred42id7l3elhrlj2oveau3vg2osq2w3qzguj4ajxrg3vycohoueyd.onion` | **live** — the hidden service (`/var/lib/tor/unredact_tools/`), and the address rendered in-page |
| `unredsk75gvi26vt4xmrqjisuxtbrjgc36nim6m33ad3vd6z3qjmy3qd.onion` | key on disk — not wired up yet |
| `unredux5hacbvpdxrbl3dxadg62satwy4345qtggfl6yygimocm6z2ad.onion` | key on disk — not wired up yet |
| `unredw5eluv3wdcmp45edf5lbuchoub637ywo3yyg6ykci3eiq47ilqd.onion` | key on disk — not wired up yet |

A legacy mirror from before the vanity keys is also still wired up and serving:

* `6ct7gmlmwzrih3yhn2fqhtj4lbhfllkhssk3p6z6dt2cax3ppv4wclid.onion` (`/var/lib/tor/unredact_tools_old/`)

These onions are public (no client auth) — the service is a public tool by
design. To turn one of the unused keys into another live mirror: copy its
directory to `/var/lib/tor/` (owner `tor:tor`, mode `0700`), add a
`HiddenServiceDir` block pointing at `127.0.0.1:8011` like the one in
*Deploy*, then `sudo systemctl reload tor`.

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
