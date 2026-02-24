import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ── config ────────────────────────────────────────────────────────────────────

LOG_PATH = Path.home() / ".lunarclient/profiles/lunar/1.8/logs/latest.log"

API_KEY = os.getenv("HYPIXEL_API_KEY")
if not API_KEY:
    sys.exit("HYPIXEL_API_KEY not set — add it to .env")

PLAYERDB = "https://playerdb.co/api/player/minecraft/{}"
HYPIXEL = "https://api.hypixel.net/player"
SESSION = requests.Session()

# ── ansi ──────────────────────────────────────────────────────────────────────

R = "\033[0m"
BOLD = "\033[1m"


def c(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"


GRAY = c(100, 100, 100)
WHITE = c(210, 210, 210)
GOLD = c(255, 170, 0)
YELLOW = c(255, 255, 0)
GREEN = c(85, 255, 85)
AQUA = c(85, 255, 255)
RED = c(170, 0, 0)

# ── star colors ───────────────────────────────────────────────────────────────

PRESTIGE = {
    0: c(170, 170, 170),
    100: c(255, 255, 255),
    200: GOLD,
    300: AQUA,
    400: c(0, 170, 0),
    500: c(0, 170, 170),
    600: c(170, 0, 0),
    700: c(255, 85, 255),
    800: c(85, 85, 255),
    900: c(170, 0, 170),
}

# rainbow per digit: ones=aqua, tens=green, hundreds=yellow, thousands+=gold
_RAINBOW = [AQUA, GREEN, YELLOW, GOLD]


def fmt_stars(n: int) -> str:
    s = str(n)
    if n < 1000:
        return PRESTIGE.get((n // 100) * 100, PRESTIGE[0]) + s + R
    out = ""
    for i, ch in enumerate(reversed(s)):
        out = _RAINBOW[min(i, 3)] + ch + out
    return out + R


# ── stat colors ───────────────────────────────────────────────────────────────


def fmt_fkdr(v: float) -> str:
    col = GRAY if v < 1 else WHITE if v < 3 else GOLD if v < 5 else RED
    return f"{col}{v:.2f}{R}"


def fmt_ws(v) -> str:
    try:
        n = int(v)
    except (ValueError, TypeError):
        return f"{GRAY}—{R}"
    col = GRAY if n < 5 else WHITE if n < 10 else GOLD if n < 20 else RED
    return f"{col}{n}{R}"


# ── api ───────────────────────────────────────────────────────────────────────


def fetch(name: str) -> tuple[str, dict | None]:
    try:
        r = SESSION.get(PLAYERDB.format(name), timeout=5)
        r.raise_for_status()
        d = r.json()
        if not d.get("success"):
            return name, None
        uuid = d["data"]["player"]["id"]
    except Exception:
        return name, None

    try:
        r = SESSION.get(HYPIXEL, params={"key": API_KEY, "uuid": uuid}, timeout=5)
        r.raise_for_status()
        d = r.json()
        if not d.get("success") or not d.get("player"):
            return name, None
        pl = d["player"]
        bw = pl.get("stats", {}).get("Bedwars", {})
        fk = bw.get("final_kills_bedwars", 0)
        fd = bw.get("final_deaths_bedwars", 0)
        return name, {
            "stars": pl.get("achievements", {}).get("bedwars_level", 0),
            "fkdr": fk / fd if fd else float(fk),
            "winstreak": bw.get("winstreak", "?"),
        }
    except Exception:
        return name, None


def fetch_all(names: list[str]) -> dict[str, dict | None]:
    results = {}
    with ThreadPoolExecutor(max_workers=max(len(names), 1)) as pool:
        futures = {pool.submit(fetch, n): n for n in names}
        for f in as_completed(futures):
            name, data = f.result()
            results[name] = data
    return results


# ── display ───────────────────────────────────────────────────────────────────

NW = 17  # name
SW = 5  # stars (raw digit width)
FW = 6  # fkdr
WW = 4  # winstreak

BAR = f"{GRAY}{'─' * 39}{R}"
HEADER = (
    f"{GRAY}"
    f"{'player':<{NW}}  "
    f"{'stars':>{SW}}  "
    f"{'fkdr':>{FW}}  "
    f"{'ws':>{WW}}"
    f"{R}"
)


def row(name: str, data: dict | None) -> str:
    nc = f"{WHITE}{name:<{NW}}{R}"

    if data is None:
        return f"{nc}  {GRAY}{'—':>{SW}}  {'—':>{FW}}  {'—':>{WW}}{R}"

    # Manual padding — ANSI escapes break f-string width counting
    s_raw = str(data["stars"])
    f_raw = f"{data['fkdr']:.2f}"
    w_raw = str(data["winstreak"])

    s_str = " " * max(0, SW - len(s_raw)) + fmt_stars(data["stars"])
    f_str = " " * max(0, FW - len(f_raw)) + fmt_fkdr(data["fkdr"])
    w_str = " " * max(0, WW - len(w_raw)) + fmt_ws(data["winstreak"])

    return f"{nc}  {s_str}  {f_str}  {w_str}"


def print_table(names: list[str], results: dict[str, dict | None]) -> None:
    print()
    print(BAR)
    print(HEADER)
    print(BAR)
    for name in names:
        print(row(name, results.get(name)))
    print(BAR)
    print()


# ── log patterns ──────────────────────────────────────────────────────────────

RE_WHO = re.compile(r"ONLINE: (.+)")
RE_LOOKUP = re.compile(
    r"Can't find a player by the name of '!([A-Za-z0-9_]+)'", re.IGNORECASE
)

# ── watcher ───────────────────────────────────────────────────────────────────


def run() -> None:
    if not LOG_PATH.exists():
        sys.exit(f"Log not found: {LOG_PATH}")

    with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue

            m = RE_WHO.search(line)
            if m:
                names = [n.strip() for n in m.group(1).split(",") if n.strip()]
                results = fetch_all(names)
                names.sort(
                    key=lambda n: results[n]["fkdr"] if results[n] else float("inf"),
                    reverse=True,
                )
                print_table(names, results)
                continue

            m = RE_LOOKUP.search(line)
            if m:
                name = m.group(1)
                _, data = fetch(name)
                print_table([name], {name: data})


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
