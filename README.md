# Nyckeltal ur årsredovisningar – med tillgångar

En fil med nyckeltal för svenska aktiebolag ur de årsredovisningar som lämnats in digitalt till
Bolagsverket. En rad per bolag, det senaste räkenskapsåret. Byggs om varje söndag av GitHub
Actions och läggs under Releases som `nyckeltal.zip` (tabbseparerad text, UTF-8, rubrikrad först).

Utöver resultat och balans finns det som visar vad bolaget äger och hur pengarna rör sig:

| Kolumn | Innehåll |
|---|---|
| orgnr, fran, till, undertecknad, sate, valuta | bolaget och räkenskapsåret (tom valuta = kronor) |
| nettoomsattning, nettoomsattning_fg | omsättning i år och förra året |
| rorelseresultat, resultat_efter_fin, arets_resultat | resultat |
| tillgangar, eget_kapital, soliditet | balans, soliditet i procent |
| kassa_bank, kortfristiga_skulder, langfristiga_skulder | likviditet och skulder |
| kreditinstitut_lang, kreditinstitut_kort | skulder till banker och andra kreditinstitut |
| materiella | materiella anläggningstillgångar totalt |
| byggnader_mark | byggnader och mark (fastighet) |
| maskiner | maskiner och andra tekniska anläggningar |
| inventarier | inventarier, verktyg och installationer (här ligger ofta fordon) |
| varulager, kundfordringar | rörelsekapital |
| anstallda, anstallda_fg, personalkostnader | personal |

Belopp i hela kronor. Ett tomt fält betyder att värdet inte är märkt i årsredovisningen. Har
årsredovisningen också en koncernredovisning tas bolagets egna värden. Personnamn tas inte med.

## Källa

Bolagsverket, digitalt inlämnade årsredovisningar:
https://vardefulla-datamangder.bolagsverket.se/arsredovisningar-bulkfiler

Uppgifterna är öppna data enligt EU:s förordning om värdefulla datamängder (2023/138).

## Bygga själv

Bara Python 3.9 eller senare, inga paket.

```bash
python3 test_bygg.py
python3 bygg.py --ut ut                     # från början (tar flera timmar)
python3 bygg.py --forra forra --ut ut       # bygger vidare på förra bygget
```
