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
RED = c(255, 85, 85)
DARK_RED = c(170, 0, 0)
DARK_GREEN = c(0, 170, 0)
DARK_AQUA = c(0, 170, 170)
BLUE = c(85, 85, 255)
DARK_BLUE = c(0, 0, 170)
LIGHT_PURPLE = c(255, 85, 255)
DARK_PURPLE = c(170, 0, 170)
BLACK = c(0, 0, 0)

# ── star colors ───────────────────────────────────────────────────────────────

PRESTIGE = {
    0: GRAY,  # <100 → same gray as low fkdr
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
_RAINBOW = [AQUA, GREEN, YELLOW, GOLD]  # ones→thousands (inner digits)
_BRACKET_L = c(255, 85, 85)  # red
_STAR_COL = c(255, 85, 255)  # pink
_BRACKET_R = c(170, 0, 170)  # purple


def fmt_stars(n: int) -> str:
    s = str(n)
    if n < 1000:
        col = PRESTIGE.get((n // 100) * 100, GRAY)
        return f"{col}[{s}★]{R}"
    # 1000+: [digits★] with rainbow coloring
    # digits colored gold/yellow/green/aqua from thousands→ones (left to right)
    colored_digits = ""
    for i, ch in enumerate(s):  # left to right
        place = len(s) - 1 - i  # thousands=3, hundreds=2, …
        colored_digits += _RAINBOW[min(place, 3)] + ch
    return f"{_BRACKET_L}[{R}{colored_digits}{R}{_STAR_COL}★{R}{_BRACKET_R}]{R}"


# ── rank ──────────────────────────────────────────────────────────────────────

PLUS_COLOR_MAP = {
    "BLACK": BLACK,
    "DARK_BLUE": DARK_BLUE,
    "DARK_GREEN": DARK_GREEN,
    "DARK_AQUA": DARK_AQUA,
    "DARK_RED": DARK_RED,
    "DARK_PURPLE": DARK_PURPLE,
    "GOLD": GOLD,
    "GRAY": GRAY,
    "DARK_GRAY": c(85, 85, 85),
    "BLUE": BLUE,
    "GREEN": GREEN,
    "AQUA": AQUA,
    "RED": RED,
    "LIGHT_PURPLE": LIGHT_PURPLE,
    "YELLOW": YELLOW,
    "WHITE": WHITE,
}

MC_COLOR_MAP = {
    "0": BLACK,
    "1": DARK_BLUE,
    "2": DARK_GREEN,
    "3": DARK_AQUA,
    "4": DARK_RED,
    "5": DARK_PURPLE,
    "6": GOLD,
    "7": GRAY,
    "8": c(85, 85, 85),
    "9": BLUE,
    "a": GREEN,
    "b": AQUA,
    "c": RED,
    "d": LIGHT_PURPLE,
    "e": YELLOW,
    "f": WHITE,
    "l": BOLD,
    "r": R,
}


def mc_to_ansi(s: str) -> str:
    out, i = "", 0
    while i < len(s):
        if s[i] == "§" and i + 1 < len(s):
            out += MC_COLOR_MAP.get(s[i + 1].lower(), "")
            i += 2
        else:
            out += s[i]
            i += 1
    return out + R


_NO_RANK = {None, "NONE", "NORMAL", ""}


def fmt_rank(
    rank: str | None,
    new_pkg: str | None,
    monthly: str | None,
    plus_color: str | None,
    prefix: str | None,
) -> tuple[str, str]:
    if prefix and prefix not in _NO_RANK:
        bracket = mc_to_ansi(prefix)
        m = re.search(r"(\033\[[^m]+m)", bracket)
        return bracket, (m.group(1) if m else WHITE)

    pc = PLUS_COLOR_MAP.get(plus_color or "", RED)

    if rank == "YOUTUBER":
        return f"{RED}[{WHITE}YOUTUBE{RED}]{R}", RED
    if rank == "STAFF":
        return f"{DARK_RED}[STAFF]{R}", DARK_RED

    if monthly == "SUPERSTAR":
        return f"{GOLD}[MVP{pc}++{GOLD}]{R}", GOLD

    rank_map = {
        "MVP_PLUS": (f"{AQUA}[MVP{pc}+{AQUA}]{R}", AQUA),
        "MVP": (f"{AQUA}[MVP]{R}", AQUA),
        "VIP_PLUS": (f"{GREEN}[VIP{GOLD}+{GREEN}]{R}", GREEN),
        "VIP": (f"{GREEN}[VIP]{R}", GREEN),
    }
    if new_pkg in rank_map:
        return rank_map[new_pkg]

    return ("", GRAY)


# ── stat colors ───────────────────────────────────────────────────────────────


def fmt_fkdr(v: float) -> str:
    col = GRAY if v < 1 else WHITE if v < 3 else GOLD if v < 5 else DARK_RED
    return f"{col}{v:.2f}{R}"


def fmt_ws(v) -> str:
    if v is None:
        return f"{GRAY}-{R}"
    try:
        n = int(v)
    except (ValueError, TypeError):
        return f"{GRAY}-{R}"
    col = GRAY if n < 5 else WHITE if n < 10 else GOLD if n < 20 else DARK_RED
    return f"{col}{n}{R}"


# ── api ───────────────────────────────────────────────────────────────────────


def fetch(name: str) -> tuple[str, dict | None]:
    try:
        r = SESSION.get(PLAYERDB.format(name), timeout=5)
        r.raise_for_status()
        d = r.json()
        if not d.get("success"):
            return name, None
        pdb = d["data"]["player"]
        uuid = pdb["id"]
        canon = pdb["username"]
    except Exception:
        return name, None

    try:
        r = SESSION.get(HYPIXEL, params={"key": API_KEY, "uuid": uuid}, timeout=5)
        r.raise_for_status()
        d = r.json()
        if not d.get("success") or not d.get("player"):
            return canon, None
        pl = d["player"]
        bw = pl.get("stats", {}).get("Bedwars", {})

        fk = bw.get("final_kills_bedwars", 0)
        fd = bw.get("final_deaths_bedwars", 0)

        bracket, name_color = fmt_rank(
            pl.get("rank"),
            pl.get("newPackageRank"),
            pl.get("monthlyPackageRank"),
            pl.get("rankPlusColor"),
            pl.get("prefix"),
        )

        return canon, {
            "stars": pl.get("achievements", {}).get("bedwars_level", 0),
            "bracket": bracket,
            "name_color": name_color,
            "fkdr": fk / fd if fd else float(fk),
            "winstreak": bw.get("winstreak"),
        }
    except Exception:
        return canon, None


def fetch_all(names: list[str]) -> dict[str, dict | None]:
    results = {}
    with ThreadPoolExecutor(max_workers=max(len(names), 1)) as pool:
        futures = {pool.submit(fetch, n): n for n in names}
        for fut in as_completed(futures):
            canon, data = fut.result()
            results[canon] = data
    return results


# ── display ───────────────────────────────────────────────────────────────────

FW = 6  # fkdr column width
WW = 4  # ws column width


def _vis(s: str) -> int:
    return len(re.sub(r"\033\[[^m]*m", "", s))


def fmt_player_cell(data: dict | None, name: str) -> str:
    if data is None:
        return f"{GRAY}{name}{R}"
    star_s = fmt_stars(data["stars"])
    bracket = data["bracket"]
    name_s = f"{data['name_color']}{name}{R}"
    if bracket:
        return f"{star_s} {bracket} {name_s}"
    return f"{star_s} {name_s}"


def print_table(names: list[str], results: dict[str, dict | None]) -> None:
    player_cells = {n: fmt_player_cell(results.get(n), n) for n in names}
    pw = max(_vis(cell) for cell in player_cells.values())
    total_w = pw + 2 + FW + 2 + WW
    bar = f"{GRAY}{'─' * total_w}{R}"
    header = f"{GRAY}{'player':<{pw}}  {'fkdr':>{FW}}  {'ws':>{WW}}{R}"

    print()
    print(bar)
    print(header)
    print(bar)
    for name in names:
        data = results.get(name)
        cell = player_cells[name]
        pad = pw - _vis(cell)

        if data is None:
            fkdr_s = f"{GRAY}{'—':>{FW}}{R}"
            ws_s = f"{GRAY}{'-':>{WW}}{R}"
        else:
            f_raw = f"{data['fkdr']:.2f}"
            w_raw = str(data["winstreak"]) if data["winstreak"] is not None else "-"
            fkdr_s = " " * max(0, FW - len(f_raw)) + fmt_fkdr(data["fkdr"])
            ws_s = " " * max(0, WW - len(w_raw)) + fmt_ws(data["winstreak"])

        print(f"{cell}{' ' * pad}  {fkdr_s}  {ws_s}")
    print(bar)
    print()


# ── log patterns ──────────────────────────────────────────────────────────────

RE_WHO = re.compile(r"ONLINE: (.+)")
RE_LOOKUP = re.compile(
    r"Can't find a player by the name of '!([A-Za-z0-9_]+)'", re.IGNORECASE
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _sorted_names(results: dict) -> list[str]:
    return sorted(
        results,
        key=lambda n: results[n]["fkdr"] if results[n] else float("inf"),
        reverse=True,
    )


def _show(results: dict) -> None:
    print_table(_sorted_names(results), results)


# ── entry points ──────────────────────────────────────────────────────────────


def run_debug(names: list[str]) -> None:
    _show(fetch_all(names))


def run_watcher() -> None:
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
                _show(fetch_all(names))
                continue

            m = RE_LOOKUP.search(line)
            if m:
                canon, data = fetch(m.group(1))
                _show({canon: data})


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        if args and args[0] == "--debug":
            if len(args) < 2:
                sys.exit("Usage: python . --debug <name1> [name2 …]")
            run_debug(args[1:])
        else:
            run_watcher()
    except KeyboardInterrupt:
        pass
