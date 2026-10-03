# Sportfogadás Value-Tipp Telegram Bot

Automatikusan elemzi a foci meccseket (Poisson gólmodell + forma-korrekció),
összeveti a bukméker oddsokkal, és csak akkor küld neked Telegram üzenetet,
ha valódi matematikai előnyt (value-t) talál.

---

## 1. Mielőtt elindítod: szerezd meg a Telegram Chat ID-det

A bot token már be van állítva, de a bot-nak tudnia kell, **kinek** küldje a
napi automatikus tippeket (a `/today` parancs enélkül is működik, de a napi
automata küldéshez ez kötelező).

1. Nyisd meg Telegramon ezt a botot: **@userinfobot**
2. Küldj neki egy üzenetet (pl. `/start`)
3. Visszaküld egy számot "Id:" felirattal, pl. `Id: 123456789`
4. Ezt a számot másold be a `.env` fájlban a `TELEGRAM_CHAT_ID=` sor után

Majd keresd meg a saját botodat Telegramon (azt a nevet, amit a @BotFather-nél
adtál neki), nyomj `/start`-ot neki is — enélkül nem tud neked írni, amíg te
nem szólítottad meg először.

---

## 2. Üzembe helyezés Railway-en (nincs szükség parancssorra)

### A) Kód feltöltése GitHub-ra
1. Menj a **github.com**-ra, jelentkezz be (vagy regisztrálj, 2 perc)
2. Jobb fent **"+"** → **"New repository"** → adj neki nevet (pl. `sportbot`) → **Create repository**
3. A repo oldalán kattints: **"uploading an existing file"**
4. Húzd be az ÖSSZES fájlt ebből a mappából (kivéve a `.env`-et! - lásd lent miért)
5. **Commit changes**

> ⚠️ **FONTOS:** A `.env` fájlt **NE** töltsd fel GitHub-ra, mert abban van a
> Telegram token és az API kulcs, nyilvános repo esetén bárki ellophatja őket.
> A `.gitignore` fájl emiatt eleve kizárja, de kézi feltöltésnél ügyelj rá.
> Railway-en a következő lépésben, a Variables fülön adod meg ugyanezeket.

### B) Railway beállítás
1. Menj a **railway.app**-ra, jelentkezz be GitHub fiókkal
2. **"New Project"** → **"Deploy from GitHub repo"** → válaszd ki a `sportbot` repót
3. Railway automatikusan felismeri, hogy Python projekt (a `requirements.txt` alapján)
4. Kattints a projektedre → **"Variables"** fül → **"New Variable"**, és add hozzá egyesével:

   | Variable neve | Érték |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | a @BotFather-től kapott token |
   | `TELEGRAM_CHAT_ID` | a @userinfobot-tól kapott számod |
   | `API_FOOTBALL_KEY` | a dashboard.api-football.com kulcsod |
   | `LEAGUE_IDS` | `39,140,78,135,61,271` (vagy a sajátod, lásd lent) |
   | `SEASON` | `2025` |
   | `MIN_EDGE_PCT` | `5` |
   | `KELLY_FRACTION` | `0.25` |
   | `LOOKAHEAD_HOURS` | `48` |
   | `DAILY_RUN_HOUR` | `8` |
   | `DAILY_RUN_MINUTE` | `0` |

5. Railway a `Procfile` alapján automatikusan elindítja a botot (`worker: python main.py`)
6. A **"Deployments"** fülön látod élőben a logokat — ha ott azt írja
   `Bot elindult, polling...`, kész is vagy!

---

## 3. Használat

- Írj a botnak Telegramon: **`/start`** — üdvözlő üzenet, parancslista
- **`/today`** — azonnal lefuttatja az elemzést a következő meccsekre és elküldi
  (ne várj rá: az ingyenes API-Football csomag napi 100 kérésre korlátoz,
  minden `/today` futtatás több kérést is elhasznál a sok meccs/csapat miatt)
- **`/leagues`** — megmutatja, mely bajnokságokat figyeli éppen
- Minden nap **08:00-kor (szerver/UTC idő!)** automatikusan lefut és küld, ha
  talál value tippet

---

## 4. Beállítások finomhangolása

Mindezt a Railway Variables fülön tudod módosítani (nem kell új kódot írni):

- **`LEAGUE_IDS`** — mely bajnokságokat figyelje. Néhány hasznos ID:
  - `39` Premier League, `140` La Liga, `78` Bundesliga, `135` Serie A,
    `61` Ligue 1, `271` NB I, `2` Bajnokok Ligája, `88` Eredivisie
  - Teljes lista: a dashboard.api-football.com dokumentációjában, "Leagues" endpoint
- **`MIN_EDGE_PCT`** — minél magasabb, annál kevesebb, de "biztosabb" tippet küld.
  5 = elég gyakori tippek, 10+ = ritkább, de erősebb value
- **`KELLY_FRACTION`** — mennyire agresszív tétjavaslatot adjon. 0.25 = óvatos
  (ajánlott), 0.5 = közepes, 1.0 = teljes Kelly (kockázatosabb, nagy varianciájú)
- **`DAILY_RUN_HOUR`** / **`DAILY_RUN_MINUTE`** — Railway szervere **UTC**
  időzónát használ! Ha magyar idő szerint reggel 8-kor szeretnéd (nyáron
  CEST = UTC+2, télen CET = UTC+1), ennek megfelelően állítsd be
  (pl. nyáron `DAILY_RUN_HOUR=6` ad magyar 08:00-at)

---

## 5. Fontos korlátok és figyelmeztetés

- **Az ingyenes API-Football csomag napi 100 kérésre korlátoz.** Egy meccs
  elemzése kb. 4-5 API hívást használ (fixture, 2× csapatstatisztika, 2× forma,
  odds), tehát kb. napi 15-20 meccset tud átnézni ingyen. Ha több bajnokságot
  figyelsz, hamar elfogyhat a keret — ekkor a bot csendben kihagyja a
  további meccseket (hibaüzenetet ír a logba, de nem akad el).
- **Ez egy statisztikai modell, nem garancia.** A value betting hosszú távon,
  sok fogadás esetén várhatóan pozitív várható értékű, de rövid távon simán
  lehet veszteséges szakasz (variancia). Soha ne tégy fel annyit, amit nem
  engedhetsz meg magadnak elveszíteni.
- A modell jelenleg csak **1X2 (hazai/döntetlen/vendég)** piacra számol
  value-t; az Over/Under és BTTS valószínűséget már kiszámolja a `model.py`,
  csak még nincs hozzá odds-összehasonlítás bekötve (ez egy jó következő
  fejlesztési lépés, szólj ha ezt szeretnéd bővíteni).

---

## 6. Fájlstruktúra

```
config.py        - minden beállítás (.env-ből olvas)
data_api.py       - API-Football hívások
model.py          - Poisson gólmodell + forma-korrekció
value.py          - devig, edge-számítás, Kelly tét-javaslat
analysis.py        - összeköti az adatot, modellt, value-t
telegram_bot.py    - Telegram parancsok + napi ütemezés
main.py           - belépési pont
requirements.txt  - Python csomagok
Procfile          - Railway indítási parancs
.env              - a te saját kulcsaid (NE oszd meg, NE töltsd fel GitHub-ra)
```

---

## 7. Mi jöhet ezután (ahogy korábban említetted)

Ez a bot később bővíthető:
- **Több sport** (tenisz, kosárlabda) hozzáadása
- **Trading alert funkció** becsatlakoztatása ugyanebbe a botba (pl. a
  TradingView webhookjait fogadva, a korábban megírt Volume Profile
  indikátorral összekötve)
- **AI-alapú kommentár** a tippekhez (pl. miért erős az adott value, rövid
  indoklás generálása)

Szólj, ha ezek közül bármelyiket szeretnéd legközelebb megépíteni!
