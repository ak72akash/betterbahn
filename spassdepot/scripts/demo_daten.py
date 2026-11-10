"""Legt Beispieldaten über die API an (zum Ausprobieren und für die Bildschirmfotos).

Aufruf: python scripts/demo_daten.py [http://localhost:8000]
Nur für eine leere Test-Datenbank gedacht – die Einträge sind erfunden und tragen keine WKN."""
import sys
from datetime import date, timedelta

import httpx
import numpy as np

basis = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000") + "/api"
c = httpx.Client(base_url=basis, timeout=30)
heute = date.today()
vor = lambda n: str(np.busday_offset(heute, -n, roll="backward"))
nach = lambda n: str(heute + timedelta(days=n))


def post(pfad, daten):
    r = c.post(pfad, json=daten)
    r.raise_for_status()
    return r.json()


def ko(name, sym, stueck, kauf, schwelle, tage_her, **kw):
    return {"datum_kauf": vor(tage_her), "wertpapier": name, "typ": "ko_long", "symbol": sym, "stueck": stueck,
            "kaufkurs": kauf, "ko_schwelle": schwelle, "bezugsverhaeltnis": 0.1, "gebuehren": 0.99, **kw}


# geschlossene Trades (mit Prognose für die Kalibrierung)
for daten, verkauf_vor, kurs, lehre in [
    (ko("Turbo Long Siemens Energy", "ENR.DE", 110, 0.90, 86.0, 24, prognose_p_gewinn=0.44, these="Ausbruch nach Auftragseingang"), 20, 1.52, "Teilgewinn früher sichern"),
    (ko("Turbo Long AMD", "AMD", 60, 1.55, 215.0, 21, prognose_p_gewinn=0.41, these="Rücksetzer an die 50-Tage-Linie"), 17, 0.74, "Stop bei −50 % eingehalten"),
    (ko("Turbo Long Rheinmetall", "RHM.DE", 8, 12.0, 1590.0, 18, prognose_p_gewinn=0.35, these="Zahlen-Vorlauf"), 14, 17.5, None),
    ({**ko("Turbo Short Tesla", "TSLA", 45, 2.10, 455.0, 15, prognose_p_gewinn=0.18, these="Schwäche nach Auslieferungen"), "typ": "ko_short"}, 12, 0.0, "Hebel war zu hoch – KO am zweiten Tag"),
    ({"datum_kauf": vor(13), "wertpapier": "Siemens", "typ": "aktie", "symbol": "SIE.DE", "stueck": 1, "kaufkurs": 224.0,
      "prognose_p_gewinn": 0.52, "ziel": 236.0, "stop": 218.0, "these": "Relative Stärke im DAX", "gebuehren": 0.99}, 6, 235.4, "Ziel fast erreicht, sauber verkauft"),
    (ko("Turbo Long Micron", "MU", 50, 1.90, 216.0, 9, prognose_p_gewinn=0.38, these="Speicherpreise ziehen an"), 5, 2.65, None),
    (ko("Turbo Long Palantir", "PLTR", 70, 1.40, 162.0, 8, prognose_p_gewinn=0.27, these="Momentum"), 4, 1.05, "Einstieg ohne klares Signal"),
]:
    t = post("/trades", daten)
    post(f"/trades/{t['id']}/schliessen", {"datum_verkauf": vor(verkauf_vor), "verkaufskurs": kurs, "gebuehren": 0.99, "lehre": lehre})

# offene Positionen
post("/trades", ko("Turbo Long Infineon", "IFX.DE", 230, 0.42, 34.20, 3, prognose_p_gewinn=0.43, ziel=41.5, stop=36.8,
                   these="Erholung der Halbleiter, Ausbruch über 38"))
post("/trades", ko("Turbo Long Nvidia", "NVDA", 55, 1.62, 169.0, 6, prognose_p_gewinn=0.40, ziel=202.0, stop=180.0,
                   these="Zahlen der Zulieferer stark"))
post("/trades", {"datum_kauf": vor(2), "wertpapier": "SAP", "typ": "aktie", "symbol": "SAP.DE", "stueck": 1, "kaufkurs": 235.2,
                 "prognose_p_gewinn": 0.5, "ziel": 249.0, "stop": 228.0, "these": "Cloud-Wachstum, Rücksetzer gekauft", "gebuehren": 0.99})

# Plan
kw = heute.isocalendar()
woche = f"{kw.year}-KW{kw.week:02d}"
post("/plan", {"woche": woche, "position": "Turbo Long Applied Materials", "symbol": "AMAT", "typ": "ko_long", "einsatz": 100,
               "kaufzeitpunkt": "Mittwoch nach US-Eröffnung", "kaufbedingung": "Kurs hält über 228 $",
               "filter": "Knock-out / Turbo, Long, Open End, Hebel 6–8, KO-Schwelle ca. 199, Bezugsverhältnis 0,1, Spread < 1 %",
               "ziel": "+60 % auf den Schein", "ausstieg": "−50 % oder 10 Handelstage", "status": "signal"})
post("/plan", {"woche": woche, "position": "Rheinmetall (Aktie)", "symbol": "RHM.DE", "typ": "aktie", "einsatz": 250,
               "kaufzeitpunkt": "Donnerstag Vormittag", "kaufbedingung": "Schlusskurs über 1.720 €",
               "ziel": "1.800 €", "ausstieg": "Stop 1.660 €", "status": "offen"})

# Termine
post("/events", {"datum": nach(2), "symbol": "IFX.DE", "art": "Quartalszahlen", "notiz": "vor Börsenstart"})
post("/events", {"datum": nach(8), "symbol": "NVDA", "art": "Quartalszahlen", "notiz": "nach US-Börsenschluss"})
post("/events", {"datum": nach(5), "symbol": None, "art": "Zinsentscheid", "notiz": "EZB, 14:15 Uhr"})

# Picks
for sym, name, kurs, ziel, stop, kat in [("AMAT", "Applied Materials", 232.0, 250.0, 222.0, "Ausrüster-Zahlen der Woche"),
                                         ("ENR.DE", "Siemens Energy", 96.0, 104.0, 91.5, "Großauftrag Netztechnik")]:
    post("/picks", {"datum": str(heute), "aktie": name, "symbol": sym, "richtung": "long", "kurs": kurs, "quelle": "demo",
                    "ziel": ziel, "stop": stop, "katalysator": kat, "trotzdem_speichern": True})
print("Beispieldaten angelegt.")
