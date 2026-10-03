"""
A teljes napi elemzési folyamat: végigmegy a figyelt bajnokságok közelgő meccsein,
lefuttatja a modellt, összeveti a bukméker oddsokkal, és összegyűjti a value tippeket.
"""
import logging

import config
import data_api
import model
import value

logger = logging.getLogger(__name__)

# Liga-átlag gólszámok - egyszerűsítésként fix értékek, később bővíthető úgy,
# hogy ligánként/szezononként ténylegesen kiszámolt átlagot használjon.
LEAGUE_AVG_HOME_GOALS = 1.5
LEAGUE_AVG_AWAY_GOALS = 1.2


def extract_team_goal_stats(stats_json):
    try:
        goals_for = stats_json["goals"]["for"]["average"]
        goals_against = stats_json["goals"]["against"]["average"]
        return {
            "goals_for_home_avg": float(goals_for["home"]),
            "goals_for_away_avg": float(goals_for["away"]),
            "goals_against_home_avg": float(goals_against["home"]),
            "goals_against_away_avg": float(goals_against["away"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def parse_1x2_odds(odds_response):
    """API-Football odds válaszból kiszedi az első elérhető 1X2 (Match Winner) piacot."""
    try:
        for bookmaker in odds_response[0]["bookmakers"]:
            for bet in bookmaker["bets"]:
                if bet["name"] == "Match Winner":
                    vals = {v["value"]: float(v["odd"]) for v in bet["values"]}
                    return {
                        "home_win": vals.get("Home"),
                        "draw": vals.get("Draw"),
                        "away_win": vals.get("Away"),
                    }
    except (IndexError, KeyError, ValueError, TypeError):
        return None
    return None


def format_tip_message(fixture, tips, lambda_home, lambda_away):
    home = fixture["teams"]["home"]["name"]
    away = fixture["teams"]["away"]["name"]
    league = fixture["league"]["name"]
    kickoff = fixture["fixture"]["date"]

    lines = [
        f"⚽ *{home} vs {away}*",
        f"_{league} | {kickoff}_",
        f"Várható gólok: {home} {lambda_home:.2f} - {lambda_away:.2f} {away}",
        "",
    ]
    for t in tips:
        stake = value.kelly_stake_fraction(t["model_prob"], t["odds"], config.KELLY_FRACTION)
        lines.append(
            f"🎯 *{t['market']}* | Odds: {t['odds']:.2f} | "
            f"Modell: {t['model_prob']*100:.1f}% vs Piac: {t['implied_prob']*100:.1f}% | "
            f"Edge: +{t['edge_pct']:.1f}% | Javasolt tét: {stake}% bankroll"
        )
    return "\n".join(lines)


def run_analysis():
    """Végigfut a figyelt ligák közelgő meccsein, visszaadja a value-tipp üzeneteket (lista)."""
    results = []

    for league_id in config.LEAGUE_IDS:
        try:
            fixtures = data_api.get_upcoming_fixtures(league_id, config.SEASON, config.LOOKAHEAD_HOURS)
        except Exception as e:
            logger.error(f"Hiba a {league_id} liga meccseinek lekérésekor: {e}")
            continue

        for fx in fixtures:
            try:
                home_id = fx["teams"]["home"]["id"]
                away_id = fx["teams"]["away"]["id"]
                fixture_id = fx["fixture"]["id"]

                home_stats_raw = data_api.get_team_statistics(home_id, league_id, config.SEASON)
                away_stats_raw = data_api.get_team_statistics(away_id, league_id, config.SEASON)
                home_stats = extract_team_goal_stats(home_stats_raw)
                away_stats = extract_team_goal_stats(away_stats_raw)
                if not home_stats or not away_stats:
                    continue

                home_form_fx = data_api.get_team_recent_form(home_id, league_id, config.SEASON)
                away_form_fx = data_api.get_team_recent_form(away_id, league_id, config.SEASON)
                home_form = model.form_points(home_form_fx, home_id)
                away_form = model.form_points(away_form_fx, away_id)

                lambda_home, lambda_away = model.expected_goals(
                    home_stats, away_stats,
                    LEAGUE_AVG_HOME_GOALS, LEAGUE_AVG_AWAY_GOALS,
                    home_form, away_form,
                )
                matrix = model.score_matrix(lambda_home, lambda_away)
                model_probs_full = model.outcome_probabilities(matrix)
                model_probs = {
                    "home_win": model_probs_full["home_win"],
                    "draw": model_probs_full["draw"],
                    "away_win": model_probs_full["away_win"],
                }

                odds_resp = data_api.get_odds_for_fixture(fixture_id)
                odds_1x2 = parse_1x2_odds(odds_resp)
                if not odds_1x2 or None in odds_1x2.values():
                    continue

                true_implied = value.devig_odds(odds_1x2)
                tips = value.find_value(model_probs, true_implied, odds_1x2, config.MIN_EDGE_PCT)

                if tips:
                    msg = format_tip_message(fx, tips, lambda_home, lambda_away)
                    results.append(msg)

            except Exception as e:
                fx_id = fx.get("fixture", {}).get("id")
                logger.error(f"Hiba a meccs elemzésekor (fixture {fx_id}): {e}")
                continue

    return results
