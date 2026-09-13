"""Per-district results for the map and the seat allocation, from Valmyndigheten's official results zip.

The zip holds every voting district's votes and the seat-allocation inputs for the whole country,
so one download per update is enough. It is reduced to two small JSON files for the browser.

Standalone use (e.g. from cron on PHP hosting):  python3 districts.py data/districts.json
That also writes seats.json next to districts.json.
"""
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import mandates

ZIP_URL = "https://resultat.val.se/resultatfiler/val2026/p/rd/Val_2026_preliminar_00_RD.zip"
USER_AGENT = "valvaka-dashboard/1.0"
PARTIES = ["S", "SD", "M", "C", "KD", "L", "MP", "V"]


def read_json(archive, kind):
    return json.loads(archive.read(next(n for n in archive.namelist() if kind in n and n.endswith(".json"))))


def fetch(etag=None):
    """Returns (etag, districts, seats), or (etag, None, None) when the zip is unchanged since `etag`."""
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    try:
        with urllib.request.urlopen(urllib.request.Request(ZIP_URL, headers=headers), timeout=60) as resp:
            body = resp.read()
            new_etag = resp.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return etag, None, None
        raise
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        districts = compact(read_json(archive, "rostfordelning"))
        seats = mandates.summary(read_json(archive, "mandatfordelning"))
    return new_etag, districts, seats


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


def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    tmp.replace(path)


def main(out_path):
    out = Path(out_path)
    seats_out = out.with_name("seats.json")
    etag_file = out.with_suffix(".etag")
    # Without both outputs on disk, download even if the zip is unchanged (e.g. right after an upgrade)
    etag = etag_file.read_text().strip() if etag_file.exists() and out.exists() and seats_out.exists() else None
    etag, districts, seats = fetch(etag)
    if districts is None:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, districts)
    write_json(seats_out, seats)
    if etag:
        etag_file.write_text(etag)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "districts.json")
