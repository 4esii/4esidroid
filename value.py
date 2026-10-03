"""
Value-bet kiszámítás: a modell valószínűségét összeveti a bukméker (vig nélküli)
implikált valószínűségével, és csak akkor jelez, ha van valódi matematikai előny.
"""


def devig_odds(odds_dict):
    """
    odds_dict: {'home_win': 2.10, 'draw': 3.40, 'away_win': 3.20}
    Visszaadja a vig (bukméker árrés) nélküli, "igazi" implikált valószínűségeket.
    """
    implied = {k: 1.0 / v for k, v in odds_dict.items() if v and v > 0}
    overround = sum(implied.values())
    if overround == 0:
        return {}
    return {k: v / overround for k, v in implied.items()}


def find_value(model_probs, true_implied_probs, odds_dict, min_edge_pct):
    """
    Visszaadja a value tippeket listaként:
    [{'market': 'home_win', 'model_prob': 0.52, 'implied_prob': 0.45,
      'edge_pct': 7.0, 'odds': 2.10}, ...]
    """
    results = []
    for market, model_p in model_probs.items():
        if market not in true_implied_probs:
            continue
        edge = (model_p - true_implied_probs[market]) * 100
        if edge >= min_edge_pct:
            results.append({
                "market": market,
                "model_prob": model_p,
                "implied_prob": true_implied_probs[market],
                "edge_pct": edge,
                "odds": odds_dict.get(market),
            })
    return results


def kelly_stake_fraction(model_prob, decimal_odds, kelly_fraction=0.25):
    """
    Fractional Kelly tét-javaslat, a bankroll százalékában kifejezve.
    A teljes (full) Kelly gyakran túl agresszív, ezért alapértelmezetten
    csak a negyedét javasoljuk (biztonsági fék a variancia ellen).
    """
    if not decimal_odds or decimal_odds <= 1:
        return 0.0
    b = decimal_odds - 1
    q = 1 - model_prob
    full_kelly = (b * model_prob - q) / b
    stake = max(full_kelly, 0) * kelly_fraction
    return round(stake * 100, 2)  # bankroll %-ban
