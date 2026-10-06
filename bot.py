#!/usr/bin/env python3
"""
Napi jelzőrendszer: félidős / félidei gólpiacok value-keresője.

Működés:
  1. Lekéri a mai meccseket (API-Football), csak a megadott ligákból.
  2. A liga lejátszott meccseiből Poisson-modellt épít (1. és 2. félidő külön).
  3. Összeveti a modell valószínűségét a fogadóirodák oddsaival (value = p * odds - 1).
  4. A legjobb jelöltekről Telegram-üzenetet küld, és naplózza őket (signals_log.csv).
  5. Következő futáskor lezárja a korábbi jelzéseket, és statisztikát ad.

Futtatás:
  python bot.py            normál futás
  python bot.py --test     csak teszt üzenet + API státusz
  python bot.py --dry      nem küld Telegramot, kiírja a képernyőre
"""
import csv
import html
import math
import os
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

# ----------------------------------------------------------------------------
# BEÁLLÍTÁSOK (környezeti változókkal felülírhatók, lásd a GitHub workflow-t)
# ----------------------------------------------------------------------------
API = "https://v3.football.api-sports.io"
TZ = "Europe/Budapest"
LOG_FILE = "signals_log.csv"

API_KEY = os.environ.get("API_FOOTBALL_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

# Liga ID-k (API-Football). Ellenőrizd / bővítsd: https://dashboard.api-football.com
# 39 PL, 40 Championship, 140 La Liga, 135 Serie A, 78 Bundesliga, 79 Bundesliga 2,
# 61 Ligue 1, 88 Eredivisie, 94 Primeira, 144 Belga, 203 Török, 179 Skót,
# 119 Dán, 103 Norvég, 113 Svéd, 271 NB I
DEFAULT_LEAGUES = "39,40,140,135,78,79,61,88,94,144,203,179,119,103,113,271"
LEAGUES = {int(x) for x in os.environ.get("LEAGUES", DEFAULT_LEAGUES).split(",") if x.strip()}

MIN_VALUE = float(os.environ.get("MIN_VALUE", "0.06"))   # min. érték (6%)
MAX_VALUE = float(os.environ.get("MAX_VALUE", "0.35"))   # efölött gyanús (adathiba)
MIN_ODDS = float(os.environ.get("MIN_ODDS", "1.30"))
MAX_ODDS = float(os.environ.get("MAX_ODDS", "3.50"))
MIN_GAMES = int(os.environ.get("MIN_GAMES", "4"))        # min. meccs/csapat (hazai ill. idegen)
SHRINK_K = float(os.environ.get("SHRINK_K", "5"))        # kis minta -> liga átlag felé húzás
MAX_SIGNALS = int(os.environ.get("MAX_SIGNALS", "8"))
ENABLED = [m.strip() for m in os.environ.get(
    "MARKETS", "h1_draw,h1_o05,h1_o15,h2_o15").split(",") if m.strip()]


# ----------------------------------------------------------------------------
# MODELL
# ----------------------------------------------------------------------------
def poisson_pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def p_draw(lh, la, kmax=15):
    return sum(poisson_pmf(k, lh) * poisson_pmf(k, la) for k in range(kmax + 1))


def p_over(lh, la, line):
    lam = lh + la
    return 1 - sum(poisson_pmf(k, lam) for k in range(int(math.floor(line)) + 1))


# bet: milyen típusú fogadási piacot keresünk az odds-ok között
# value: az odds-értéknév kisbetűvel
MARKETS = {
    "h1_draw": dict(
        label="1. félidő döntetlen", bet="h1_winner", value="draw",
        prob=lambda e: p_draw(*e["h1"]),
        win=lambda r: r["h1"][0] == r["h1"][1]),
    "h1_o05": dict(
        label="1. félidő 0,5 gól felett", bet="h1_ou", value="over 0.5",
        prob=lambda e: p_over(*e["h1"], 0.5),
        win=lambda r: sum(r["h1"]) > 0.5),
    "h1_o15": dict(
        label="1. félidő 1,5 gól felett", bet="h1_ou", value="over 1.5",
        prob=lambda e: p_over(*e["h1"], 1.5),
        win=lambda r: sum(r["h1"]) > 1.5),
    "h2_o15": dict(
        label="2. félidő 1,5 gól felett", bet="h2_ou", value="over 1.5",
        prob=lambda e: p_over(*e["h2"], 1.5),
        win=lambda r: sum(r["h2"]) > 1.5),
    "h2_o05": dict(
        label="2. félidő 0,5 gól felett", bet="h2_ou", value="over 0.5",
        prob=lambda e: p_over(*e["h2"], 0.5),
        win=lambda r: sum(r["h2"]) > 0.5),
}


def shrunk(total, n, prior):
    return (total + SHRINK_K * prior) / (n + SHRINK_K)


def build_stats(fixtures):
    """Lejátszott meccsekből liga-átlagok és csapat-statisztikák (hazai/idegen bontásban)."""
    rows = []
    for f in fixtures:
        if f["fixture"]["status"]["short"] != "FT":
            continue
        ht, ft = f["score"]["halftime"], f["score"]["fulltime"]
        if ht["home"] is None or ft["home"] is None:
            continue
        rows.append((f["teams"]["home"]["id"], f["teams"]["away"]["id"],
                     ht["home"], ht["away"],
                     ft["home"] - ht["home"], ft["away"] - ht["away"]))
    if len(rows) < 20:
        return None
    n = len(rows)
    league = {
        1: (sum(r[2] for r in rows) / n, sum(r[3] for r in rows) / n),
        2: (sum(r[4] for r in rows) / n, sum(r[5] for r in rows) / n),
    }
    home, away = {}, {}
    for hid, aid, h1h, h1a, h2h, h2a in rows:
        # [n, h1_for, h1_against, h2_for, h2_against]
        s = home.setdefault(hid, [0, 0, 0, 0, 0])
        s[0] += 1; s[1] += h1h; s[2] += h1a; s[3] += h2h; s[4] += h2a
        s = away.setdefault(aid, [0, 0, 0, 0, 0])
        s[0] += 1; s[1] += h1a; s[2] += h1h; s[3] += h2a; s[4] += h2h
    return dict(league=league, home=home, away=away)


def expected_goals(stats, hid, aid):
    hs, as_ = stats["home"].get(hid), stats["away"].get(aid)
    if not hs or not as_ or hs[0] < MIN_GAMES or as_[0] < MIN_GAMES:
        return None
    out = {}
    for period, (fi, ai) in ((1, (1, 2)), (2, (3, 4))):
        lh, la = stats["league"][period]
        if lh <= 0 or la <= 0:
            return None
        att_h = shrunk(hs[fi], hs[0], lh)       # hazai csapat lőtt gólja otthon
        def_a = shrunk(as_[ai], as_[0], lh)     # vendég kapott gólja idegenben
        att_a = shrunk(as_[fi], as_[0], la)     # vendég lőtt gólja idegenben
        def_h = shrunk(hs[ai], hs[0], la)       # hazai kapott gólja otthon
        out["h%d" % period] = (att_h * def_a / lh, att_a * def_h / la)
    return out


# ----------------------------------------------------------------------------
# API-FOOTBALL
# ----------------------------------------------------------------------------
class Api:
    remaining = None

    @classmethod
    def get(cls, path, **params):
        r = requests.get(API + path, headers={"x-apisports-key": API_KEY},
                         params=params, timeout=40)
        r.raise_for_status()
        rem = r.headers.get("x-ratelimit-requests-remaining")
        if rem is not None:
            cls.remaining = rem
        data = r.json()
        if data.get("errors"):
            raise RuntimeError("API-Football hiba: %s" % data["errors"])
        return data


def classify_bet(name):
    n = name.lower()
    first = "first" in n or "1st" in n
    second = "second" in n or "2nd" in n
    if "half winner" in n and first and not second:
        return "h1_winner"
    if "over/under" in n:
        bad = ("home", "away", "team", "both", "corner", "card", "handicap",
               "asian", "exact", "odd", "result", "btts")
        if any(b in n for b in bad):
            return None
        if first and not second:
            return "h1_ou"
        if second and not first:
            return "h2_ou"
    return None


def parse_odds(items):
    """{fixture_id: {(bet_kind, value): [(odd, bookmaker), ...]}}"""
    out = {}
    for it in items:
        fid = it["fixture"]["id"]
        for bm in it.get("bookmakers", []):
            for bet in bm.get("bets", []):
                kind = classify_bet(bet.get("name", ""))
                if not kind:
                    continue
                for v in bet.get("values", []):
                    try:
                        odd = float(v["odd"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    key = (kind, str(v.get("value", "")).strip().lower())
                    out.setdefault(fid, {}).setdefault(key, []).append((odd, bm.get("name", "?")))
    return out


def fetch_odds(date_str, league_id, season):
    items, page = [], 1
    while page <= 6:
        d = Api.get("/odds", date=date_str, league=league_id, season=season,
                    timezone=TZ, page=page)
        items += d.get("response", [])
        paging = d.get("paging") or {}
        if page >= int(paging.get("total", 1) or 1):
            break
        page += 1
    return parse_odds(items)


def median(xs):
    xs = sorted(xs)
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


# ----------------------------------------------------------------------------
# NAPLÓ + LEZÁRÁS
# ----------------------------------------------------------------------------
LOG_FIELDS = ["date", "fixture_id", "league", "match", "market", "model_p",
              "odds", "best_odds", "bookmaker", "value", "status"]


def read_log():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_log(rows):
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        w.writeheader()
        w.writerows(rows)


def settle(rows, today_str):
    pending = [r for r in rows if r["status"] == "pending" and r["date"] < today_str]
    ids = sorted({r["fixture_id"] for r in pending})
    results = {}
    for i in range(0, len(ids), 20):
        d = Api.get("/fixtures", ids="-".join(ids[i:i + 20]), timezone=TZ)
        for f in d.get("response", []):
            results[str(f["fixture"]["id"])] = f
    for r in pending:
        f = results.get(r["fixture_id"])
        if not f:
            continue
        st = f["fixture"]["status"]["short"]
        if st in ("PST", "CANC", "ABD", "AWD", "WO"):
            r["status"] = "void"
        elif st == "FT":
            ht, ft = f["score"]["halftime"], f["score"]["fulltime"]
            if ht["home"] is None or ft["home"] is None:
                continue
            res = {"h1": (ht["home"], ht["away"]),
                   "h2": (ft["home"] - ht["home"], ft["away"] - ht["away"])}
            r["status"] = "won" if MARKETS[r["market"]]["win"](res) else "lost"
    return rows


def summary(rows):
    done = [r for r in rows if r["status"] in ("won", "lost")]
    if not done:
        return ""
    wins = sum(1 for r in done if r["status"] == "won")
    profit = sum(float(r["odds"]) - 1 if r["status"] == "won" else -1 for r in done)
    return "📊 Eddigi jelzések: %d lezárva, %d nyert (%.0f%%), ROI %+.1f%% (1 egységes tétekkel)" % (
        len(done), wins, 100 * wins / len(done), 100 * profit / len(done))


# ----------------------------------------------------------------------------
# TELEGRAM
# ----------------------------------------------------------------------------
def hu(x, d=2):
    return ("%.*f" % (d, x)).replace(".", ",")


def send_telegram(text, dry=False):
    if dry:
        print(text)
        return
    blocks, chunk, chunks = text.split("\n\n"), "", []
    for b in blocks:
        if len(chunk) + len(b) + 2 > 3800 and chunk:
            chunks.append(chunk)
            chunk = ""
        chunk += ("\n\n" if chunk else "") + b
    chunks.append(chunk)
    for c in chunks:
        r = requests.post(
            "https://api.telegram.org/bot%s/sendMessage" % TG_TOKEN,
            json={"chat_id": TG_CHAT, "text": c, "parse_mode": "HTML",
                  "disable_web_page_preview": True}, timeout=30)
        if not r.ok:
            raise RuntimeError("Telegram hiba %s: %s" % (r.status_code, r.text))


# ----------------------------------------------------------------------------
# FŐ LOGIKA
# ----------------------------------------------------------------------------
def find_signals(day_fixtures, season_cache, odds_cache):
    signals = []
    by_league = {}
    for f in day_fixtures:
        if f["league"]["id"] in LEAGUES and f["fixture"]["status"]["short"] == "NS":
            by_league.setdefault(f["league"]["id"], []).append(f)

    for lid, fixes in by_league.items():
        season = fixes[0]["league"]["season"]
        stats = season_cache(lid, season)
        if not stats:
            continue
        odds = odds_cache(lid, season)
        for f in fixes:
            fid = f["fixture"]["id"]
            exp = expected_goals(stats, f["teams"]["home"]["id"], f["teams"]["away"]["id"])
            fo = odds.get(fid)
            if not exp or not fo:
                continue
            for key in ENABLED:
                m = MARKETS.get(key)
                lines = fo.get((m["bet"], m["value"])) if m else None
                if not lines:
                    continue
                p = m["prob"](exp)
                ref = median([o for o, _ in lines])
                best, book = max(lines)
                value = p * ref - 1
                if not (MIN_ODDS <= ref <= MAX_ODDS and MIN_VALUE <= value <= MAX_VALUE):
                    continue
                signals.append(dict(
                    fixture_id=fid, league=f["league"]["name"],
                    time=f["fixture"]["date"][11:16],
                    home=f["teams"]["home"]["name"], away=f["teams"]["away"]["name"],
                    market=key, label=m["label"], p=p, ref=ref, best=best, book=book,
                    value=value))
    signals.sort(key=lambda s: s["value"], reverse=True)
    return signals[:MAX_SIGNALS]


def format_message(signals, today_str, stats_line):
    if not signals:
        msg = "📡 <b>%s</b>\nMa nincs a szűrőknek megfelelő jelzés." % today_str
    else:
        parts = ["📡 <b>Napi jelzések – %s</b> (%d db)" % (today_str, len(signals))]
        for s in signals:
            parts.append(
                "⚽ <b>%s – %s</b>\n%s · %s\n"
                "▫️ <b>%s</b>\n"
                "Modell: %s%% (fair odds %s) · Piaci odds: %s (legjobb %s @ %s)\n"
                "Érték: <b>%s%%</b>" % (
                    html.escape(s["home"]), html.escape(s["away"]),
                    html.escape(s["league"]), s["time"], s["label"],
                    hu(100 * s["p"], 0), hu(1 / s["p"]), hu(s["ref"]), hu(s["best"]),
                    html.escape(s["book"]), "%+.0f" % (100 * s["value"])))
        parts.append("ℹ️ Jelzés, nem tipp: nézd át a keretet, hiányzókat és a formát, mielőtt játszol.")
        msg = "\n\n".join(parts)
    if stats_line:
        msg += "\n\n" + stats_line
    return msg


def main():
    dry = "--dry" in sys.argv
    missing = [n for n, v in (("API_FOOTBALL_KEY", API_KEY), ("TELEGRAM_BOT_TOKEN", TG_TOKEN),
                              ("TELEGRAM_CHAT_ID", TG_CHAT)) if not v]
    if missing and not dry:
        print("Hiányzó beállítás: " + ", ".join(missing))
        sys.exit(1)

    if "--test" in sys.argv:
        st = Api.get("/status")["response"]
        used = st.get("requests", {})
        send_telegram("✅ A bot működik, a Telegram-kapcsolat rendben.\n"
                      "API-Football: %s kérés felhasználva ma (limit: %s)." % (
                          used.get("current"), used.get("limit_day")), dry)
        return

    try:
        today = datetime.now(ZoneInfo(TZ)).date().isoformat()

        # 1) korábbi jelzések lezárása
        rows = read_log()
        if any(r["status"] == "pending" and r["date"] < today for r in rows):
            rows = settle(rows, today)

        # 2) mai meccsek + modell + odds
        day = Api.get("/fixtures", date=today, timezone=TZ)["response"]
        cache_s, cache_o = {}, {}

        def season_cache(lid, season):
            if lid not in cache_s:
                d = Api.get("/fixtures", league=lid, season=season, status="FT")["response"]
                cache_s[lid] = build_stats(d)
            return cache_s[lid]

        def odds_cache(lid, season):
            if lid not in cache_o:
                cache_o[lid] = fetch_odds(today, lid, season)
            return cache_o[lid]

        signals = find_signals(day, season_cache, odds_cache)

        # 3) naplózás (duplikáció nélkül)
        have = {(r["fixture_id"], r["market"]) for r in rows}
        for s in signals:
            if (str(s["fixture_id"]), s["market"]) in have:
                continue
            rows.append(dict(
                date=today, fixture_id=s["fixture_id"], league=s["league"],
                match="%s - %s" % (s["home"], s["away"]), market=s["market"],
                model_p="%.3f" % s["p"], odds="%.2f" % s["ref"],
                best_odds="%.2f" % s["best"], bookmaker=s["book"],
                value="%.3f" % s["value"], status="pending"))
        write_log(rows)

        # 4) üzenet
        send_telegram(format_message(signals, today, summary(rows)), dry)
        print("Kész. Jelzések: %d · API kérések hátra: %s" % (len(signals), Api.remaining))
    except Exception as e:  # a hibát Telegramra is elküldjük, hogy lásd
        traceback.print_exc()
        try:
            send_telegram("⚠️ A bot hibába futott:\n<code>%s</code>" % html.escape(str(e))[:900], dry)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
