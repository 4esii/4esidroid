"""
Egyszerűsített Dixon-Coles jellegű Poisson gólmodell + forma-heurisztika.

A modell lényege:
1. Minden csapathoz kiszámolunk egy "támadó erő" és "védekező erő" mutatót
   a liga-átlaghoz viszonyítva (hazai/vendég bontásban).
2. Ezekből várható gólszámot (lambda) számolunk mindkét csapatra.
3. A lambdákat Poisson-eloszlásba téve megkapjuk a lehetséges végeredmények
   (0-0, 1-0, 2-1, stb.) valószínűségi mátrixát.
4. Ebből összegezzük a piaci kimeneteket (1X2, Over/Under 2.5, BTTS).
5. A nyers lambdát egy kis súlyú forma-korrekcióval finomítjuk (utolsó 5 meccs).
"""
import math


def poisson_pmf(k, lam):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


def score_matrix(lambda_home, lambda_away, max_goals=6):
    """Valószínűségi mátrix minden (hazai gól, vendég gól) kombinációra."""
    matrix = []
    for h in range(max_goals + 1):
        row = []
        for a in range(max_goals + 1):
            row.append(poisson_pmf(h, lambda_home) * poisson_pmf(a, lambda_away))
        matrix.append(row)
    return matrix


def outcome_probabilities(matrix):
    """A score-mátrixból kiszámolt piaci valószínűségek."""
    home_win = draw = away_win = 0.0
    over25 = btts_yes = 0.0
    for h, row in enumerate(matrix):
        for a, p in enumerate(row):
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
            if h + a > 2.5:
                over25 += p
            if h >= 1 and a >= 1:
                btts_yes += p
    return {
        "home_win": home_win, "draw": draw, "away_win": away_win,
        "over25": over25, "under25": 1 - over25,
        "btts_yes": btts_yes, "btts_no": 1 - btts_yes,
    }


def form_points(fixtures, team_id):
    """
    Utolsó N meccs forma-pontszáma 0..1 közé normalizálva
    (győzelem=3, döntetlen=1, vereség=0 pont, a maximum pontszámhoz viszonyítva).
    Ha nincs adat, 0.5-öt (semleges) ad vissza.
    """
    if not fixtures:
        return 0.5
    total = 0
    counted = 0
    for fx in fixtures:
        home_id = fx["teams"]["home"]["id"]
        home_goals = fx["goals"]["home"]
        away_goals = fx["goals"]["away"]
        if home_goals is None or away_goals is None:
            continue
        counted += 1
        is_home = home_id == team_id
        team_goals = home_goals if is_home else away_goals
        opp_goals = away_goals if is_home else home_goals
        if team_goals > opp_goals:
            total += 3
        elif team_goals == opp_goals:
            total += 1
    if counted == 0:
        return 0.5
    return total / (3 * counted)


def expected_goals(home_stats, away_stats, league_avg_home_goals, league_avg_away_goals,
                    home_form=0.5, away_form=0.5):
    """
    Várható gólszám (lambda) mindkét csapatra.

    home_stats / away_stats kulcsai:
        goals_for_home_avg, goals_for_away_avg,
        goals_against_home_avg, goals_against_away_avg
    """
    home_scored_avg = home_stats["goals_for_home_avg"]
    home_conceded_avg = home_stats["goals_against_home_avg"]
    away_scored_avg = away_stats["goals_for_away_avg"]
    away_conceded_avg = away_stats["goals_against_away_avg"]

    home_attack = home_scored_avg / league_avg_home_goals
    away_defense = away_conceded_avg / league_avg_home_goals
    away_attack = away_scored_avg / league_avg_away_goals
    home_defense = home_conceded_avg / league_avg_away_goals

    lambda_home = home_attack * away_defense * league_avg_home_goals
    lambda_away = away_attack * home_defense * league_avg_away_goals

    # Forma-korrekció: 0.5 a semleges érték, 0..1 skálán kb. +/-15%-kal tudja
    # módosítani a várható gólszámot. Szándékosan kis súlyú, hogy ne írja
    # felül a statisztikai alapot.
    home_form_adj = 0.85 + 0.30 * home_form
    away_form_adj = 0.85 + 0.30 * away_form
    lambda_home *= home_form_adj
    lambda_away *= away_form_adj

    return max(lambda_home, 0.05), max(lambda_away, 0.05)
