"""HTML for the onion edition. Plain strings, no template engine, no JS.

Every page is one self-contained document. The stylesheet is inline so a text
browser needs exactly one request, and layout never depends on color.
"""
from __future__ import annotations

from html import escape as e

from unredact_tools import __version__
from unredact_tools.model import FACT_LABELS, SEVERITIES

ONION = "unred42id7l3elhrlj2oveau3vg2osq2w3qzguj4ajxrg3vycohoueyd.onion"

CSS = """
:root{--fg:#d7d3cb;--dim:#8a857c;--line:#33312d;--bg:#141412;--hot:#ff8a1f}
@media (prefers-color-scheme:light){:root{--fg:#1d1b18;--dim:#6b6862;--line:#d8d3c8;--bg:#fbf9f4;--hot:#b45309}}
*{box-sizing:border-box}
html{background:var(--bg);color:var(--fg)}
body{font:15px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;margin:0 auto;max-width:74ch;padding:28px 20px 64px}
a{color:var(--fg);text-decoration:underline;text-underline-offset:2px}
a:hover{color:var(--hot)}
header{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:28px}
.brand{font-weight:700;text-decoration:none}
.brand .br{color:var(--dim)}
nav{font-size:13px;color:var(--dim)}
nav a{color:var(--dim)}
br.tb{display:none}
h1{font-size:21px;line-height:1.3;margin:0 0 10px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin:32px 0 10px;font-weight:700}
p{margin:0 0 14px}
.lede{color:var(--dim)}
form{border:1px solid var(--line);padding:16px;margin:20px 0}
fieldset{border:0;padding:0;margin:0 0 14px}
legend{color:var(--dim);font-size:13px;padding:0 0 6px}
label{display:block;font-size:14px;margin:6px 0}
input[type=checkbox]{margin-right:6px}
input[type=file]{width:100%;padding:8px 0;color:var(--fg)}
select{font:inherit;background:var(--bg);color:var(--fg);border:1px solid var(--line);padding:4px 6px}
button,.btn{font:inherit;display:inline-block;background:var(--fg);color:var(--bg);border:0;padding:9px 18px;cursor:pointer;text-decoration:none}
button:hover,.btn:hover{background:var(--hot);color:#141412}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;vertical-align:top;padding:7px 10px 7px 0;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:700;white-space:nowrap}
td.sev{white-space:nowrap}
.critical{color:var(--hot);font-weight:700}
.high{color:#d9a93a;font-weight:700}
.low,.info{color:var(--dim)}
.meter{white-space:pre;font-size:16px;margin:0 0 6px}
.meta{color:var(--dim);font-size:13px}
pre{overflow-x:auto;margin:0}
ul{margin:0 0 14px;padding-left:22px}
li{margin:0 0 4px}
footer{border-top:1px solid var(--line);margin-top:48px;padding-top:14px;color:var(--dim);font-size:12px}
footer p{margin:0 0 4px}
.note{border-left:3px solid var(--line);padding:8px 14px;margin:16px 0;color:var(--dim);font-size:13px}
"""

NAV = '<a href="/">scan</a> · <a href="/about">about</a>'


def page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        "<title>" + e(title) + " · unredact.tools</title>"
        f"<style>{CSS}</style></head><body>"
        '<header><a class="brand" href="/"><span class="br">[</span>unredact'
        '<span class="br">]</span><span class="meta"> onion</span></a>'
        f'<br class="tb"><nav>{NAV}</nav></header><main>{body}</main>'
        f"<footer><p>unredact.tools · onion edition · v{e(__version__)}</p>"
        f"<p>{e(ONION)}</p>"
        "<p>no javascript · no cookies · no analytics</p></footer>"
        "</body></html>"
    )


def home() -> str:
    body = """
<h1>See what your files give away.</h1>
<p class="lede">GPS coordinates, device serials, author names, black boxes that
hide nothing, deleted text. Scan a photo, PDF or Office file, read the report,
download a copy with the evidence removed.</p>
<form method="post" action="/scan" enctype="multipart/form-data">
  <fieldset><legend>file</legend>
    <input type="file" name="file" required>
  </fieldset>
  <fieldset><legend>options</legend>
    <label><input type="checkbox" name="fast" value="true"> fast scan
      <span class="meta">— metadata only; skip OCR, faces, codes, dots</span></label>
  </fieldset>
  <button type="submit">Inspect file</button>
  <p class="meta">No JavaScript, no cookies. Works in w3m and lynx.
  50 MB limit.</p>
</form>
<p class="meta">What it checks and how it handles your file: <a href="/about">/about</a></p>
"""
    return page("see what your files give away", body)


def _meter(score: int) -> str:
    filled = max(0, min(20, round(score / 5)))
    return "[" + "#" * filled + "-" * (20 - filled) + f"] {score}/100"


def _score(counts: dict) -> int:
    return min(100, 12 * counts["critical"] + 6 * counts["high"]
               + 3 * counts["medium"] + 1 * counts["low"])


_SEV_LABEL = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM",
              "low": "LOW", "info": "INFO"}


def report(r, filename: str, token: str, hints: list[str]) -> str:
    counts = r.counts()
    score = _score(counts)
    kind = getattr(r, "kind", None)

    facts_rows = []
    for bucket in sorted(r.facts, key=lambda b: list(FACT_LABELS).index(b)
                         if b in FACT_LABELS else 99):
        vals = "".join(f"<li>{e(v)}</li>" for v in r.facts[bucket])
        facts_rows.append(f"<tr><th>{e(FACT_LABELS.get(bucket, bucket.upper()))}</th>"
                          f"<td><ul>{vals}</ul></td></tr>")

    finding_rows = []
    for f in r.sorted_findings():
        detail = f'<div class="meta">{e(f.detail)}</div>' if f.detail else ""
        finding_rows.append(
            f'<tr><td class="sev {e(f.severity)}">[{_SEV_LABEL.get(f.severity, f.severity.upper())}]</td>'
            f"<td><strong>{e(f.title)}</strong>{detail}</td>"
            f'<td class="meta">{e(f.source)}</td></tr>')

    def box(name: str, label: str, hint: str, note: str = "") -> str:
        checked = " checked" if hint in hints else ""
        extra = f' <span class="meta">— {note}</span>' if note else ""
        return (f'<label><input type="checkbox" name="{name}" value="true"{checked}>'
                f" {label}{extra}</label>")

    opts = (
        box("redact_text", "redact readable text", "redact_text", "burn in solid boxes over OCR hits")
        + box("redact_codes", "redact codes and boarding passes", "redact_codes")
        + box("blur_faces", "blur faces", "blur_faces")
        + box("redact_plates", "redact license plates", "redact_plates")
        + box("desync", "desync", "desync", "resample and crop to break photo fingerprints")
        + box("keep_dots", "keep printer tracking dots", "keep_dots")
    )
    pdf = ""
    if r.filetype == "application/pdf" or (r.path or "").lower().endswith(".pdf"):
        pdf = ('<label>PDF mode <select name="pdf_mode">'
               '<option value="raster">raster — flatten every page (safest)</option>'
               '<option value="text">text — keep selectable text</option>'
               "</select></label>")

    size = f"{r.size:,} bytes" if r.size else ""
    sha = e(r.sha256[:12] + "…") if r.sha256 else ""
    counts_line = " · ".join(f"{counts[s]} {s}" for s in SEVERITIES if counts[s])

    body = f"""
<p class="meta"><a href="/">← scan another file</a></p>
<h1>report: {e(filename)}</h1>
<p class="meta">{e(r.filetype or "unknown")} · {size} · sha256 {sha}</p>

<h2>findability</h2>
<p class="meter">{_meter(score)}</p>
<p class="meta">{counts_line}</p>

<h2>what it reveals</h2>
<table>{''.join(facts_rows) or '<tr><td class="meta">nothing extracted</td></tr>'}</table>

<h2>findings ({len(r.findings)})</h2>
<table>
<tr><th>severity</th><th>finding</th><th>source</th></tr>
{''.join(finding_rows)}
</table>

<h2>clean it</h2>
<form method="post" action="/clean">
  <input type="hidden" name="token" value="{e(token)}">
  <fieldset><legend>what to remove <span class="meta">(metadata is always stripped)</span></legend>
    {opts}
  </fieldset>
  {pdf}
  <button type="submit">Clean and re-scan</button>
</form>
<p class="note">Your upload is held in a private temp directory so the cleaned
copy can be produced from the same file. It is deleted after the download, or
after 5 minutes, whichever comes first.</p>
"""
    return page(f"report: {filename}", body)


def cleaned(src_name: str, out_name: str, before: int, after: int,
            remaining: list, notes: list, token: str) -> str:
    remaining_html = ""
    if remaining:
        items = "".join(f"<li>{e(f.title)} <span class='meta'>{e(f.source)}</span></li>"
                        for f in remaining[:12])
        remaining_html = (
            f'<h2>still visible ({len(remaining)})</h2>'
            f"<p class='meta'>These survived the clean; go back and pick more options.</p>"
            f"<ul>{items}</ul>")
    notes_html = "".join(f"<li>{e(n)}</li>" for n in notes)
    if notes_html:
        notes_html = f"<h2>what changed</h2><ul>{notes_html}</ul>"

    body = f"""
<h1>cleaned</h1>
<p class="meta">{e(src_name)} → {e(out_name)}</p>
<table>
<tr><th>before</th><td>{before} findings</td></tr>
<tr><th>after</th><td>{after} findings</td></tr>
</table>
{notes_html}
{remaining_html}
<p style="margin-top:24px"><a class="btn" href="/download/{e(token)}">Download cleaned copy</a></p>
<p class="note">The link works once. The file is deleted as soon as it is served.</p>
<p class="meta"><a href="/">scan another file</a></p>
"""
    return page("cleaned", body)


def about() -> str:
    body = """
<h1>about this mirror</h1>
<p class="lede">The no-JavaScript edition of unredact.tools, served only as a
Tor onion service.</p>

<h2>what it looks at</h2>
<ul>
<li>EXIF/XMP/IPTC metadata: GPS, device and lens serials, owner, software trail</li>
<li>embedded thumbnails and motion-photo video</li>
<li>hidden PDF content: old revisions, attachments, annotations, deleted text</li>
<li>Office internals: authors, comments, tracked changes, hidden sheets</li>
<li>failed redactions: text still readable under black boxes</li>
<li>optical: OCR text, QR/barcodes, faces, license plates, printer dots</li>
</ul>

<h2>how your file is handled</h2>
<ul>
<li>the scan runs here; nothing is sent to any third party</li>
<li>uploads go to a private temp directory and are deleted when you download
the cleaned copy, or after 5 minutes</li>
<li>no filenames are logged, no cookies, no analytics, no scripts</li>
</ul>

<h2>findability</h2>
<p class="meta">A rough exposure score: 12 points per critical finding, 6 per
high, 3 per medium, 1 per low, capped at 100. It is a conversation starter,
not a risk model.</p>

<h2>limits</h2>
<ul>
<li>50 MB per file; OCR and dot decoding need a fast scan turned off</li>
<li>detection is heuristic — a clean report is not a guarantee</li>
<li>for anything you would not upload anywhere, run the CLI offline</li>
</ul>

<h2>elsewhere</h2>
<p class="meta">clearnet: unredact.tools<br>
source: github.com/NPCmillionaire/unredact.tools</p>
<pre>pip install "unredact-tools[web]"
unredact.tools web</pre>
"""
    return page("about", body)


def error(status: int, message: str) -> str:
    body = (f'<h1>{status}</h1><p>{e(message)}</p>'
            '<p class="meta"><a href="/">← back to the scanner</a></p>')
    return page(str(status), body)
