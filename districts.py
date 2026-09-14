"""Per-district results, seat allocation and counting status, from Valmyndigheten's official files.

The results zip holds every voting district's votes and the seat-allocation inputs for the whole
country, so one download per update is enough. It is reduced to small JSON files for the browser,
together with Valmyndigheten's schedule messages and whether the final count has started publishing.

Standalone use (e.g. from cron on PHP hosting):  python3 districts.py data/districts.json
That also writes seats.json and status.json next to districts.json.
"""
import collections
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import mandates

ZIP_URL = "https://resultat.val.se/resultatfiler/val2026/p/rd/Val_2026_preliminar_00_RD.zip"
FINAL_ZIP_URL = "https://resultat.val.se/resultatfiler/val2026/s/rd/Val_2026_slutlig_00_RD.zip"
MESSAGES_URL = "https://resultat.val.se/data/meddelanden/meddelanden_val2026.json"
USER_AGENT = "valvaka-dashboard/1.0"
PARTIES = ["S", "SD", "M", "C", "KD", "L", "MP", "V"]


def request(url, headers=None, method="GET", timeout=60):
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers, method=method), timeout=timeout)


def read_json(archive, kind):
    return json.loads(archive.read(next(n for n in archive.namelist() if kind in n and n.endswith(".json"))))


def fetch(etag=None):
    """Returns (etag, districts, seats, progress), or (etag, None, None, None) when the zip is unchanged."""
    try:
        with request(ZIP_URL, {"If-None-Match": etag} if etag else None) as resp:
            body = resp.read()
            new_etag = resp.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return etag, None, None, None
        raise
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        votes = read_json(archive, "rostfordelning")
        seats = mandates.summary(read_json(archive, "mandatfordelning"))
        counting = progress(votes, read_json(archive, "summering"))
    return new_etag, compact(votes), seats, counting


def compact(data):
    districts = {}
    colors = {}
    for d in data["valdistrikt"]:
        # Collection districts (uppsamlingsdistrikt) have no area on the map
        votes = (d.get("rostfordelning") or {}).get("rosterPaverkaMandat")
        if not votes or d.get("valdistriktstyp") != "valdistrikt":
            continue
        shares = dict.fromkeys(PARTIES, 0)
        for p in votes["partiRoster"]:
            code = p["partiforkortning"]
            if code in shares:
                shares[code] = p["andelRoster"] or 0
                colors.setdefault(code, p.get("fargkod"))
        other = (votes.get("rosterOvrigaPartier") or {}).get("andelRoster") or 0
        # [reported at, valid votes, *shares in PARTIES order, other parties' share]
        districts[d["valdistriktskod"]] = [d.get("rapporteringsTid") or "", votes["antalRoster"],
                                          *(shares[c] for c in PARTIES), other]
    return {
        "updated": data.get("senasteUppdateringstid"),
        "counted": data.get("antalValdistriktRaknade"),
        "total": data.get("antalValdistriktSomSkaRaknas"),
        "parties": PARTIES,
        "colors": colors,
        "districts": districts,
    }


def progress(votes, summary):
    """Counting progress per district type, and where polling-station results are still missing."""
    counts = {"valdistrikt": [0, 0], "uppsamlingsdistrikt": [0, 0]}
    pending = collections.Counter()
    for d in votes["valdistrikt"]:
        kind = d.get("valdistriktstyp")
        counted = bool(d.get("rostfordelning"))
        if kind in counts:
            counts[kind][0] += counted
            counts[kind][1] += 1
        if kind == "valdistrikt" and not counted:
            pending[d.get("kommunkod")] += 1
    names = {k["kommunkod"]: k["namn"] for k in summary.get("kommuner", [])}
    return {
        "updated": votes.get("senasteUppdateringstid"),
        "regular": {"counted": counts["valdistrikt"][0], "total": counts["valdistrikt"][1]},
        "collection": {"counted": counts["uppsamlingsdistrikt"][0], "total": counts["uppsamlingsdistrikt"][1]},
        "pending": [{"kommun": names.get(code, code), "districts": n} for code, n in pending.most_common()],
    }


def riksdag_messages():
    """Valmyndigheten's info messages for the Riksdag election, which carry the counting schedule."""
    with request(MESSAGES_URL, timeout=30) as resp:
        items = json.load(resp)
    if isinstance(items, dict):
        items = items.get("meddelanden", [])
    return [m["text"].strip() for m in items if any(n.get("path") == "RD" for n in m.get("nivaer", []))]


def final_count_published():
    try:
        with request(FINAL_ZIP_URL, method="HEAD", timeout=30):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def status(counting):
    return {**counting, "messages": riksdag_messages(), "final_published": final_count_published()}


def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(path)


def main(out_path):
    out = Path(out_path)
    seats_out = out.with_name("seats.json")
    status_out = out.with_name("status.json")
    etag_file = out.with_suffix(".etag")
    # Without every output on disk, download even if the zip is unchanged (e.g. right after an upgrade)
    complete = all(p.exists() for p in (out, seats_out, status_out))
    etag = etag_file.read_text().strip() if etag_file.exists() and complete else None
    etag, districts, seats, counting = fetch(etag)
    out.parent.mkdir(parents=True, exist_ok=True)
    if districts is not None:
        write_json(out, districts)
        write_json(seats_out, seats)
        if etag:
            etag_file.write_text(etag)
    else:
        # Zip unchanged: keep the counts, but still pick up new messages or the start of the final count
        previous = json.loads(status_out.read_text())
        counting = {key: previous[key] for key in ("updated", "regular", "collection", "pending")}
    write_json(status_out, status(counting))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "districts.json")
