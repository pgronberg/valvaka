"""Dashboard + proxy for Valmyndigheten's live Riksdag results (val.se sends no CORS headers).

Background pollers keep the latest national results, record a snapshot every time val.se
publishes an update (so /api/history holds the whole evening no matter when a visitor arrives),
and keep per-district results for the map.
"""
import json
import os
import threading
import time
import urllib.request
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import districts

ROOT = Path(__file__).parent
HOST = os.environ.get("HOST", "127.0.0.1")  # set HOST=0.0.0.0 inside a container
PORT = int(os.environ.get("PORT", "8765"))
HISTORY_FILE = Path(os.environ.get("HISTORY_FILE", ROOT / "history.json"))
UPSTREAM = "https://resultat.val.se/data/resultat/val2026/RD_P.json"
POLL_SECONDS = 30  # the CDN caches for ~60s, so polling harder gains nothing
DISTRICTS_SECONDS = 60
LEFT = ("S", "V", "MP", "C")
RIGHT = ("M", "SD", "KD", "L")
MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli",
          "augusti", "september", "oktober", "november", "december"]

_lock = threading.Lock()
_ready = threading.Event()
_latest = None  # raw bytes of the most recent good fetch
_districts = None  # compact per-district JSON bytes for the map
_history = []


def parse_update_time(text):
    """'13 september 2026 20:49:36' -> '2026-09-13T20:49:36'"""
    day, month, year, clock = text.split()
    hour, minute, second = map(int, clock.split(":"))
    return datetime(int(year), MONTHS.index(month.lower()) + 1, int(day), hour, minute, second).isoformat()


def snapshot(data):
    r = data["rosterPaverkaMandat"]
    parties = {p["partiforkortning"]: p for p in r["partiroster"]}
    total = r["antalRoster"] or 0

    def bloc(codes):
        votes = sum(parties[c]["antalRoster"] or 0 for c in codes if c in parties)
        return round(votes / total * 100, 2) if total else 0

    return {
        "t": parse_update_time(data["senasteUppdateringstid"]),
        "districts": data["antalValdistriktRaknade"],
        "left": bloc(LEFT),
        "right": bloc(RIGHT),
        "parties": {code: p["andelRoster"] for code, p in parties.items()},
    }


def save_history():
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_history))
    tmp.replace(HISTORY_FILE)


def poll_forever():
    global _latest
    while True:
        try:
            req = urllib.request.Request(UPSTREAM, headers={"User-Agent": "valvaka-dashboard/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
            snap = snapshot(json.loads(body))
            with _lock:
                _latest = body
                if not _history or _history[-1]["t"] != snap["t"]:
                    _history.append(snap)
                    save_history()
            _ready.set()
        except Exception as e:  # keep polling through network blips and half-published data
            print(f"poll failed: {e}", flush=True)
        time.sleep(POLL_SECONDS)


def poll_districts_forever():
    global _districts
    etag = None
    while True:
        try:
            etag, result = districts.fetch(etag)
            if result is not None:
                body = json.dumps(result, separators=(",", ":")).encode()
                with _lock:
                    _districts = body
        except Exception as e:
            print(f"district poll failed: {e}", flush=True)
        time.sleep(DISTRICTS_SECONDS)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/results":
            _ready.wait(timeout=20)
            with _lock:
                body = _latest
            if body is None:
                return self.reply(502, b'{"error":"upstream unavailable"}')
            return self.reply(200, body)
        if path == "/api/history":
            with _lock:
                body = json.dumps(_history).encode()
            return self.reply(200, body)
        if path == "/api/districts":
            with _lock:
                body = _districts
            if body is None:
                return self.reply(503, b'{"error":"district results not loaded yet"}')
            return self.reply(200, body)
        return super().do_GET()

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    if HISTORY_FILE.exists():
        _history = json.loads(HISTORY_FILE.read_text())
    threading.Thread(target=poll_forever, daemon=True).start()
    threading.Thread(target=poll_districts_forever, daemon=True).start()
    handler = partial(Handler, directory=str(ROOT))
    print(f"Valvaka dashboard: http://{HOST}:{PORT} (history: {HISTORY_FILE})", flush=True)
    ThreadingHTTPServer((HOST, PORT), handler).serve_forever()
