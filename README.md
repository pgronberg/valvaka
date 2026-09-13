# Valvaka 2026

[![Licens: MIT](https://img.shields.io/badge/licens-MIT-blue.svg)](LICENSE)
[![Data: Valmyndigheten](https://img.shields.io/badge/data-Valmyndigheten-005293.svg)](https://resultat.val.se/val2026/RD?r=P)
[![Status: inofficiell](https://img.shields.io/badge/status-inofficiell-orange.svg)](#förtroende-och-transparens)
[![Ingen spårning](https://img.shields.io/badge/sp%C3%A5rning-ingen-brightgreen.svg)](#förtroende-och-transparens)
[![Beroenden: 0](https://img.shields.io/badge/beroenden-0-brightgreen.svg)](#kom-igång)

**Live: [valvaka.celestiocloud.site](https://valvaka.celestiocloud.site)**

En enkel live-dashboard för valnatten: hur stora **Tidöpartierna** (M, SD, KD, L) och **oppositionen** (S, V, MP, C) är just nu, varje partis andel, och hur siffrorna förändras under kvällen. Siffrorna hämtas direkt från Valmyndighetens resultatsida och uppdateras varje minut.

*A small live dashboard for Sweden's 2026 general election night, showing bloc and party vote shares straight from the Election Authority's published results. Unofficial, open source, no tracking.*

## Vad visas

- **Blocken:** Oppositionens och Tidöpartiernas sammanlagda andel av rösterna, förändring sedan 2022 och vem som leder.
- **Partierna:** Varje partis andel som stapel, förändring sedan 2022 och 4 %-spärren.
- **Utvecklingen:** En linjegraf med en punkt per uppdatering från Valmyndigheten, för blocken eller alla partier. Hovra eller använd piltangenterna för att se värden och förändringen sedan föregående uppdatering. Allt finns även som tabell.
- **Räkningsläget:** Hur många av valdistrikten som är räknade och när Valmyndigheten senast uppdaterade.
- **Kartan:** Alla 6 312 valdistrikt, färgade efter största parti eller största block när de är räknade. Hovra eller tryck på ett distrikt för dess resultat, zooma in i städerna och se de senast rapporterade distrikten.

## Förtroende och transparens

- **Inofficiell.** Projektet är inte kopplat till eller granskat av Valmyndigheten. Det officiella resultatet finns på [val.se](https://www.val.se) och fastställs av Valmyndigheten.
- **Oförändrad källdata.** Resultaten hämtas från samma JSON-filer som [resultat.val.se](https://resultat.val.se/val2026/RD?r=P) själv använder och skickas vidare utan ändringar. Serverns enda tillägg är en historik med en ögonblicksbild per uppdatering.
- **Öppna beräkningar.** Partiernas andelar är Valmyndighetens egna siffror (`andelRoster`). Blockens andel är summan av blockets partiers röster delat med antalet röster som påverkar mandatfördelningen (`rosterPaverkaMandat.antalRoster`). Koden finns i [`index.html`](index.html) och [`server.py`](server.py).
- **Preliminärt.** Valnattens siffror är den preliminära rösträkningen. Den slutliga räkningen kan ge andra siffror.
- **Ingen spårning.** Inga cookies, ingen analys och inga tredjepartsresurser. Webbläsaren pratar bara med servern som levererar sidan. `localStorage` används bara för att komma ihåg grafvalet, och på statiska värdar även för historiken.
- **Kartdata.** Distriktsgränserna kommer från Valmyndighetens [öppna data](https://www.val.se/valresultat-och-statistik/statistik-och-data/radata-val-2026) (länsstyrelsernas valdistrikt i SWEREF 99 TM), förenklade med [mapshaper](https://github.com/mbloch/mapshaper) till `valdistrikt.topo.json`. Resultaten per distrikt kommer från Valmyndighetens officiella resultatfil `Val_2026_preliminar_00_RD.zip`. De 314 uppsamlingsdistrikten saknar geografi och syns inte på kartan.
- **Inga beroenden.** Servern använder bara Pythons standardbibliotek och sidan är ren HTML, CSS och JavaScript, så det finns ingen leveranskedja att lita på.

## Kom igång

Kräver Python 3.10 eller senare.

```bash
python3 server.py
```

Öppna sedan <http://localhost:8765>.

| Miljövariabel | Standard | Beskrivning |
|---|---|---|
| `HOST` | `127.0.0.1` | Adress servern lyssnar på. Använd `0.0.0.0` i en container. |
| `PORT` | `8765` | Port. |
| `HISTORY_FILE` | `history.json` | Var kvällens historik sparas, så att den överlever en omstart. |

## Driftsättning

Valmyndighetens filer skickar inga CORS-huvuden, så en webbläsare på en annan domän kan inte hämta dem direkt. Därför behöver värden skicka vidare `api/results` (och helst `api/history`) till val.se. Välj det som passar din hosting:

| Hosting | Filer | Historik |
|---|---|---|
| Container eller VPS med Python | `server.py`, `districts.py`, `index.html`, `valdistrikt.topo.json` | På servern, gemensam för alla besökare |
| Docker | `Dockerfile` | På servern. Montera en volym på `/data` för att behålla den vid omstart. |
| PHP (Apache eller nginx) | `index.html`, `api.php`, `.htaccess`, `districts.py`, `valdistrikt.topo.json` | På servern, men registreras bara när någon har sidan öppen. Utan URL-omskrivning, till exempel på nginx, anropar sidan `api.php` direkt. |
| Netlify | `index.html`, `_redirects` | Bara i besökarens webbläsare |
| Vercel | `index.html`, `vercel.json` | Bara i besökarens webbläsare |

```bash
docker build -t valvaka .
docker run -p 8080:8080 -v valvaka-data:/data valvaka
```

På PHP-hosting sköter cron det som `server.py` annars gör i bakgrunden: historiken och resultaten per distrikt till kartan. `districts.py` kräver Python 3.10 eller senare på servern.

```bash
* * * * * cd ~/public && php api.php >/dev/null 2>&1
* * * * * cd ~/public && python3 districts.py data/districts.json >/dev/null 2>&1
```

## API

| Endpoint | Svar |
|---|---|
| `GET /api/results` | Valmyndighetens `RD_P.json` oförändrad, cachad i 30 sekunder |
| `GET /api/history` | `[{ t, districts, left, right, parties: { S: 24.0, … } }, …]`, en post per uppdatering |
| `GET /api/districts` | `{ updated, parties, colors, districts: { "08600201": [rapporterat, giltiga röster, …andelar i partiordning, övriga] } }`, bara räknade distrikt |

Källdatan följer mönstret `https://resultat.val.se/data/resultat/val2026/{val}_{område}_{P|S}.json`, till exempel `RD_P.json` (riksdagen, hela landet, preliminärt) eller `KF_10_1082_P.json` (kommunvalet i Karlshamn). Alla områdeskoder finns i `https://resultat.val.se/data/valgeografi/valgeografi_val2026.json`. Formatet är Valmyndighetens interna och odokumenterade format och kan ändras utan förvarning.

Servern hämtar som mest en gång var 30:e sekund oavsett antal besökare, för att inte belasta Valmyndighetens tjänst.

## Licens

Koden är licensierad under [MIT](LICENSE). Licensen gäller koden i det här repot. Valresultat och distriktsgränser kommer från Valmyndigheten, som ska anges som källa. Gränserna tas fram av länsstyrelserna.
