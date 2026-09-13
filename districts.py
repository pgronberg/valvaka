"""Per-district results for the map, from Valmyndigheten's official results zip.

The zip holds every voting district's votes for the whole country, so one download per update is
enough. It is reduced to a small JSON file the browser can colour 6,312 districts from.

Standalone use (e.g. from cron on PHP hosting):  python3 districts.py data/districts.json
"""
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ZIP_URL = "https://resultat.val.se/resultatfiler/val2026/p/rd/Val_2026_preliminar_00_RD.zip"
USER_AGENT = "valvaka-dashboard/1.0"
PARTIES = ["S", "SD", "M", "C", "KD", "L", "MP", "V"]


def fetch(etag=None):
    """Returns (etag, compact results), or (etag, None) when the zip is unchanged since `etag`."""
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    try:
        with urllib.request.urlopen(urllib.request.Request(ZIP_URL, headers=headers), timeout=60) as resp:
            body = resp.read()
            new_etag = resp.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return etag, None
        raise
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        name = next(n for n in z.namelist() if "rostfordelning" in n and n.endswith(".json"))
        data = json.loads(z.read(name))
    return new_etag, compact(data)


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


def main(out_path):
    out = Path(out_path)
    etag_file = out.with_suffix(".etag")
    etag = etag_file.read_text().strip() if etag_file.exists() and out.exists() else None
    etag, result = fetch(etag)
    if result is None:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, separators=(",", ":")))
    tmp.replace(out)
    if etag:
        etag_file.write_text(etag)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "districts.json")
