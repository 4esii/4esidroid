"""
Minden beállítás innen jön. Ne írj közvetlenül a kódba semmilyen kulcsot vagy
tokent - mindig a .env fájlban add meg őket.
"""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # a saját Telegram user/chat ID-d

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
# Közvetlen API-SPORTS hitelesítés (dashboard.api-football.com-on regisztrálva),
# NEM a RapidAPI piactéren keresztül - ezért más base URL és más header kell.
API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"

# Figyelt bajnokságok (API-Football liga ID-k).
# 39 = Premier League, 140 = La Liga, 78 = Bundesliga, 135 = Serie A,
# 61 = Ligue 1, 271 = NB I (magyar bajnokság)
LEAGUE_IDS = [int(x) for x in os.getenv("LEAGUE_IDS", "39,140,78,135,61,271").split(",") if x.strip()]

SEASON = int(os.getenv("SEASON", "2025"))

# Value betting küszöb: a bot csak akkor jelez tippet, ha a modell-valószínűség
# legalább ennyi százalékponttal magasabb, mint a bukméker (vig nélküli) implikált esélye.
MIN_EDGE_PCT = float(os.getenv("MIN_EDGE_PCT", "5"))

# Fractional Kelly: a teljes Kelly-tét hányad részét javasolja a bot (biztonsági fék
# a túlzott tétek ellen). 0.25 = negyed-Kelly, ami a leggyakrabban ajánlott érték.
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", "0.25"))

# Hány órával előre nézzen meccseket a napi elemzésnél
LOOKAHEAD_HOURS = int(os.getenv("LOOKAHEAD_HOURS", "48"))

# Napi automatikus futtatás ideje (24 órás formátum, SZERVER idő szerint - Railway-n UTC!)
DAILY_RUN_HOUR = int(os.getenv("DAILY_RUN_HOUR", "8"))
DAILY_RUN_MINUTE = int(os.getenv("DAILY_RUN_MINUTE", "0"))
