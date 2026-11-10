"""Journal-Berechnungen als reine Funktionen: Einsatz, Ergebnis, Positionswert,
Depotwert, Auswertung, Regelverstöße."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from app.data.maerkte import waehrung
from app.rules.grenzen import STANDARD
from app.rules.regeln import (
    Regelergebnis,
    ampel,
    ausstieg_aktie,
    ausstieg_knockout,
    eur,
    handelstage,
    ist_hebelprodukt,
    pct,
)


def einsatz(tr) -> float:
    return tr.stueck * tr.kaufkurs


def ergebnis_eur(tr) -> float | None:
    if tr.verkaufskurs is None:
        return None
    return (tr.verkaufskurs - tr.kaufkurs) * tr.stueck - (tr.gebuehren or 0.0)


def ergebnis_pct(tr) -> float | None:
    e = ergebnis_eur(tr)
    return None if e is None else e / einsatz(tr) * 100


def ist_offen(tr) -> bool:
    return tr.datum_verkauf is None


def trade_ausgabe(tr) -> dict:
    return {**tr.model_dump(), "einsatz": einsatz(tr), "ergebnis_eur": ergebnis_eur(tr),
            "ergebnis_pct": ergebnis_pct(tr), "offen": ist_offen(tr)}


def schein_wert(typ: str, kurs: float, ko_schwelle: float, bezugsverhaeltnis: float,
                eurusd: float | None = None, in_usd: bool = False) -> float:
    """Geschätzter Wert eines Knock-out-Scheins in €: innerer Wert × Bezugsverhältnis,
    bei US-Basiswerten durch EUR/USD geteilt. Ohne Aufgeld und Spread – eine Schätzung."""
    innerer = (kurs - ko_schwelle) if typ == "ko_long" else (ko_schwelle - kurs)
    wert = max(0.0, innerer) * bezugsverhaeltnis
    if in_usd:
        if not eurusd or eurusd <= 0:
            raise ValueError("Für US-Basiswerte wird der EUR/USD-Kurs benötigt.")
        wert /= eurusd
    return wert


def bewerte_position(tr, kurs: float | None, eurusd: float | None, heute: date,
                     g: dict = STANDARD) -> dict:
    """Aktueller Stand einer offenen Position inkl. Ausstiegssignalen.

    ``kurs``: Kurs des Basiswerts in dessen Währung. Liefert auch ohne Kurs die
    Stammdaten (dann ohne Wert und Signale außer Zeit-Stop)."""
    usd = waehrung(tr.symbol) == "USD"
    ein = einsatz(tr)
    gehalten = handelstage(tr.datum_kauf, heute)
    out: dict = {"trade_id": tr.id, "wertpapier": tr.wertpapier, "symbol": tr.symbol, "typ": tr.typ,
                 "stueck": tr.stueck, "kaufkurs": tr.kaufkurs, "einsatz": ein,
                 "ko_schwelle": tr.ko_schwelle, "bezugsverhaeltnis": tr.bezugsverhaeltnis,
                 "ziel": tr.ziel, "stop": tr.stop, "handelstage": gehalten, "kurs": kurs,
                 "wert": None, "wert_je_stueck": None, "perf_pct": None, "ko_abstand_pct": None,
                 "geschaetzt": True, "hinweis": None, "signale": [], "ampel": "grau"}
    signale: list[Regelergebnis] = []
    if kurs is None or (usd and not eurusd):
        out["hinweis"] = "Kein aktueller Kurs" if kurs is None else "EUR/USD-Kurs fehlt"
        if tr.typ != "aktie" and gehalten >= int(g["ko_zeitstop_tage"]):
            signale = [s for s in ausstieg_knockout(0, gehalten, 100, g) if s.regel == "ko_zeitstop"]
    elif tr.typ == "aktie":
        je = kurs / eurusd if usd else kurs
        out.update(wert_je_stueck=je, wert=je * tr.stueck, perf_pct=(je / tr.kaufkurs - 1) * 100,
                   geschaetzt=usd,
                   hinweis="Aus US-Kurs und EUR/USD umgerechnet" if usd else None)
        signale = ausstieg_aktie(kurs, tr.ziel, tr.stop)
    else:
        je = schein_wert(tr.typ, kurs, tr.ko_schwelle, tr.bezugsverhaeltnis, eurusd, usd)
        abstand = (kurs - tr.ko_schwelle) / kurs * 100 if tr.typ == "ko_long" else (tr.ko_schwelle - kurs) / kurs * 100
        perf = (je / tr.kaufkurs - 1) * 100
        out.update(wert_je_stueck=je, wert=je * tr.stueck, perf_pct=perf, ko_abstand_pct=abstand,
                   hinweis="Schätzung: (Kurs − KO-Schwelle) × Bezugsverhältnis"
                           + (" ÷ EUR/USD" if usd else "") + ", ohne Aufgeld und Spread")
        signale = ausstieg_knockout(perf, gehalten, abstand, g)
    out["signale"] = [s.dict() for s in signale]
    out["ampel"] = ampel(signale) if (kurs is not None or signale) else "grau"
    return out


def depot(trades: Iterable, positionswerte: dict[int, float | None], g: dict = STANDARD) -> dict:
    """Depotstand. Offene Positionen ohne Kurs zählen mit ihrem Einsatz."""
    trades = list(trades)
    start = float(g["startkapital"])
    realisiert = sum(ergebnis_eur(t) or 0.0 for t in trades if not ist_offen(t))
    offene = [t for t in trades if ist_offen(t)]
    gebunden = sum(einsatz(t) for t in offene)
    gebuehren_offen = sum(t.gebuehren or 0.0 for t in offene)
    bargeld = start + realisiert - gebunden - gebuehren_offen
    wert_offen = 0.0
    for t in offene:
        w = positionswerte.get(t.id)
        wert_offen += einsatz(t) if w is None else w
    depotwert = bargeld + wert_offen
    hebel = sum(einsatz(t) for t in offene if ist_hebelprodukt(t.typ))
    return {"startkapital": start, "depotwert": depotwert, "veraenderung_eur": depotwert - start,
            "veraenderung_pct": (depotwert / start - 1) * 100 if start else 0.0,
            "bargeld": bargeld, "reserve_anteil": bargeld / depotwert if depotwert > 0 else 0.0,
            "reserve_minimum": float(g["min_reserve_anteil"]) * depotwert,
            "gebunden": gebunden, "hebel_einsatz": hebel, "wert_offen": wert_offen,
            "realisiert": realisiert, "offene_positionen": len(offene)}


def kalibrierung(trades: Iterable) -> list[dict]:
    """Prognose-Gruppen gegen tatsächliche Trefferquote (nur geschlossene Trades mit Prognose)."""
    gruppen = [("< 20 %", 0.0, 0.2), ("20–40 %", 0.2, 0.4), ("> 40 %", 0.4, 1.01)]
    out = []
    for name, von, bis in gruppen:
        g = [t for t in trades if not ist_offen(t) and t.prognose_p_gewinn is not None
             and von <= t.prognose_p_gewinn < bis]
        treffer = sum(1 for t in g if (ergebnis_eur(t) or 0) > 0)
        out.append({"gruppe": name, "anzahl": len(g),
                    "prognose_mittel": sum(t.prognose_p_gewinn for t in g) / len(g) if g else None,
                    "trefferquote": treffer / len(g) if g else None})
    return out


def regelverstoesse(trades: Iterable, g: dict = STANDARD, heute: date | None = None) -> list[dict]:
    heute = heute or date.today()
    out = []
    def melde(t, regel, text):
        out.append({"trade_id": t.id, "wertpapier": t.wertpapier, "datum": t.datum_kauf, "regel": regel, "text": text})
    for t in trades:
        ein = einsatz(t)
        grenze = float(g["max_ko_einsatz"] if ist_hebelprodukt(t.typ) else g["max_aktie_einsatz"])
        if ein > grenze + 0.005:
            melde(t, "positionsgroesse", f"Einsatz {eur(ein)} über dem Limit von {eur(grenze)}.")
        if not (t.these or "").strip():
            melde(t, "these", "Kauf ohne festgehaltene These.")
        if t.typ != "aktie":
            tage = handelstage(t.datum_kauf, t.datum_verkauf or heute)
            if tage > int(g["ko_zeitstop_tage"]):
                melde(t, "ko_zeitstop", f"Knock-out {tage} Handelstage gehalten (Zeit-Stop nach {int(g['ko_zeitstop_tage'])}).")
            p = ergebnis_pct(t)
            if p is not None and p < float(g["ko_verlust_stop_pct"]) - 5:
                melde(t, "ko_verlust", f"Verkauft bei {pct(p, 0)} – Ausstieg bei {pct(float(g['ko_verlust_stop_pct']), 0)} nicht eingehalten (oder KO).")
    return out


def auswertung(trades: Iterable, g: dict = STANDARD, heute: date | None = None) -> dict:
    trades = list(trades)
    zu = sorted((t for t in trades if not ist_offen(t)), key=lambda t: (t.datum_verkauf, t.id or 0))
    erg = [ergebnis_eur(t) or 0.0 for t in zu]
    gewinne, verluste = sum(e for e in erg if e > 0), -sum(e for e in erg if e < 0)
    start = float(g["startkapital"])
    verlauf, stand = [], start
    if zu:
        verlauf.append({"datum": min(t.datum_kauf for t in trades), "depotwert": start})
    for t, e in zip(zu, erg, strict=True):
        stand += e
        if verlauf and verlauf[-1]["datum"] == t.datum_verkauf:
            verlauf[-1]["depotwert"] = stand
        else:
            verlauf.append({"datum": t.datum_verkauf, "depotwert": stand})
    return {
        "anzahl_geschlossen": len(zu), "anzahl_offen": len(trades) - len(zu),
        "gewinner": sum(1 for e in erg if e > 0), "verlierer": sum(1 for e in erg if e <= 0),
        "trefferquote": sum(1 for e in erg if e > 0) / len(zu) if zu else None,
        "gewinnfaktor": gewinne / verluste if verluste > 0 else None,
        "summe_gewinne": gewinne, "summe_verluste": verluste, "ergebnis_gesamt": sum(erg),
        "durchschnitt_gewinn": gewinne / max(1, sum(1 for e in erg if e > 0)) if gewinne else None,
        "durchschnitt_verlust": -verluste / max(1, sum(1 for e in erg if e < 0)) if verluste else None,
        "depotverlauf": verlauf, "kalibrierung": kalibrierung(trades),
        "regelverstoesse": regelverstoesse(trades, g, heute),
    }


def teile_fuer_teilverkauf(tr, stueck: float) -> tuple[dict, float]:
    """Teilverkauf: Daten für den abgespaltenen (zu schließenden) Teil und Reststückzahl.
    Bereits gebuchte Gebühren werden anteilig verteilt."""
    if stueck >= tr.stueck:
        raise ValueError("Teilverkauf muss kleiner als der Bestand sein.")
    anteil = stueck / tr.stueck
    teil = tr.model_dump(exclude={"id"})
    teil["stueck"] = stueck
    teil["gebuehren"] = (tr.gebuehren or 0.0) * anteil
    return teil, tr.stueck - stueck
