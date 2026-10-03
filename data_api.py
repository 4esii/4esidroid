"""
Vékony wrapper az API-Football (RapidAPI) végpontok köré.
Dokumentáció: https://www.api-football.com/documentation-v3
"""
import requests
from datetime import datetime, timedelta

import config

BASE_URL = config.API_FOOTBALL_BASE_URL

# Közvetlen API-SPORTS hitelesítés (dashboard.api-football.com-on kapott kulcs).
HEADERS = {
    "x-apisports-key": config.API_FOOTBALL_KEY,
}


def _get(endpoint, params=None):
    resp = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def get_upcoming_fixtures(league_id, season, hours_ahead):
    """A következő `hours_ahead` órában kezdődő, még el nem kezdődött meccsek."""
    now = datetime.utcnow()
    end = now + timedelta(hours=hours_ahead)
    data = _get("fixtures", {
        "league": league_id,
        "season": season,
        "from": now.strftime("%Y-%m-%d"),
        "to": end.strftime("%Y-%m-%d"),
        "status": "NS",  # Not Started
    })
    return data.get("response", [])


def get_team_statistics(team_id, league_id, season):
    """Csapat szezon-statisztikája (gólok hazai/vendég bontásban stb.)."""
    data = _get("teams/statistics", {
        "team": team_id,
        "league": league_id,
        "season": season,
    })
    return data.get("response", {})


def get_team_recent_form(team_id, league_id, season, last=5):
    """Az utolsó N lejátszott meccs a formaszámításhoz."""
    data = _get("fixtures", {
        "team": team_id,
        "league": league_id,
        "season": season,
        "last": last,
    })
    return data.get("response", [])


def get_odds_for_fixture(fixture_id):
    """Elérhető bukméker oddsok egy adott meccsre."""
    data = _get("odds", {"fixture": fixture_id})
    return data.get("response", [])
