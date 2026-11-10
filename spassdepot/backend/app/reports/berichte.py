"""Morgenbericht, Positions-Check und Wochenbilanz."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlmodel import Session, select

from app.data.news import ManuellerNewsProvider, NewsProvider
from app.data.store import KursSpeicher
from app.journal import tabellen as t
from app.journal.berechnung import einsatz, ergebnis_eur, ist_offen, regelverstoesse
from app.journal.dienst import depot_stand, heute_berlin, positionen
from app.rules.regeln import eur, max_positionsgroesse, pct, risk_off_aktiv, verlustbremse


def _risiko(g: dict, depotwert: float) -> dict:
    ro = risk_off_aktiv(bool(g["risk_off"]), float(g["index_vortag_pct"]), g)
    vb = verlustbremse(depotwert, g)
    return {"risk_off": not ro.ok, "risk_off_text": ro.begruendung,
            "verlustbremse": not vb.ok, "verlustbremse_text": vb.begruendung,
            "max_knockout": max_positionsgroesse("ko_long", depotwert, not ro.ok, g).wert,
            "max_aktie": max_positionsgroesse("aktie", depotwert, not ro.ok, g).wert}


def positions_check(s: Session, store: KursSpeicher, g: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    d = depot_stand(s, store, g, now)
    return {"art": "positionen", "zeit": now.isoformat(), "depot": d,
            "risiko": _risiko(g, d["depotwert"]), "positionen": positionen(s, store, g, now)}


def morgenbericht(s: Session, store: KursSpeicher, g: dict, now: datetime | None = None,
                  news: NewsProvider | None = None) -> dict:
    now = now or datetime.now(UTC)
    heute = heute_berlin(now)
    news = news or ManuellerNewsProvider()
    check = positions_check(s, store, g, now)
    plan = []
    for p in s.exec(select(t.PlanEintrag).where(t.PlanEintrag.status.in_(["offen", "signal"]))):  # type: ignore[attr-defined]
        info = store.nachricht(p.symbol, now) if p.symbol else None
        zahlen = news.naechste_quartalszahlen(s, p.symbol, heute, heute + timedelta(days=14)) if p.symbol else None
        hinweise = []
        grenze = check["risiko"]["max_aktie" if p.typ == "aktie" else "max_knockout"]
        if p.einsatz > grenze + 0.005:
            hinweise.append(f"Geplanter Einsatz {eur(p.einsatz)} liegt über dem aktuellen Limit von {eur(grenze)}.")
        if zahlen:
            hinweise.append(f"Quartalszahlen am {zahlen.strftime('%d.%m.')} – Knock-out nicht über die Zahlen halten.")
        if info is None and p.symbol:
            hinweise.append("Kein aktueller Kurs verfügbar.")
        plan.append({**p.model_dump(), "kurs_info": info, "hinweise": hinweise})
    termine = news.termine(s, heute, heute + timedelta(days=7))
    zeilen = [f"Depotwert {eur(check['depot']['depotwert'])} ({pct(check['depot']['veraenderung_pct'])} seit Start), "
              f"freie Reserve {eur(check['depot']['bargeld'])}."]
    if check["risiko"]["risk_off"]:
        zeilen.append(check["risiko"]["risk_off_text"])
    if check["risiko"]["verlustbremse"]:
        zeilen.append(check["risiko"]["verlustbremse_text"])
    for p in check["positionen"]:
        for sig in p["signale"]:
            zeilen.append(f"{p['wertpapier']}: {sig['begruendung']}")
    zeilen.append(f"{len(plan)} offene Plan-Position(en), {len(check['positionen'])} offene Position(en), "
                  f"{len(termine)} Termin(e) in den nächsten 7 Tagen.")
    return {**check, "art": "morgen", "plan": plan, "termine": termine, "zusammenfassung": zeilen}


def wochenbilanz(s: Session, store: KursSpeicher, g: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    heute = heute_berlin(now)
    montag = heute - timedelta(days=heute.weekday())
    sonntag = montag + timedelta(days=6)
    trades = list(s.exec(select(t.Trade)))
    gekauft = [tr for tr in trades if montag <= tr.datum_kauf <= sonntag]
    verkauft = [tr for tr in trades if tr.datum_verkauf and montag <= tr.datum_verkauf <= sonntag]
    erg = [ergebnis_eur(tr) or 0.0 for tr in verkauft]
    picks = [p for p in s.exec(select(t.Pick)) if montag - timedelta(days=21) <= p.datum <= sonntag]
    d = depot_stand(s, store, g, now)
    zeile = lambda tr: {"id": tr.id, "wertpapier": tr.wertpapier, "typ": tr.typ, "einsatz": einsatz(tr),
                        "ergebnis_eur": ergebnis_eur(tr), "lehre": tr.lehre}
    return {
        "art": "woche", "zeit": now.isoformat(), "woche": f"{montag.isocalendar().year}-KW{montag.isocalendar().week:02d}",
        "von": montag, "bis": sonntag, "depot": d,
        "gekauft": [zeile(tr) for tr in gekauft], "verkauft": [zeile(tr) for tr in verkauft],
        "ergebnis_woche": sum(erg),
        "trefferquote_woche": sum(1 for e in erg if e > 0) / len(erg) if erg else None,
        "offene_positionen": sum(1 for tr in trades if ist_offen(tr)),
        "regelverstoesse": [v for v in regelverstoesse(trades, g, heute) if montag <= v["datum"] <= sonntag],
        "picks": [p.model_dump() for p in picks],
        "lehren": [tr.lehre for tr in verkauft if tr.lehre],
    }


def pick_ergebnis(pick_datum: date, kurs: float, richtung: str, verlauf: pd.DataFrame, tage: int) -> float | None:
    """Kursveränderung in % in Pick-Richtung nach ``tage`` Handelstagen (Schlusskurs).
    None, solange der Zeitraum noch nicht abgelaufen ist."""
    spaeter = verlauf[verlauf["datum"] > pick_datum]
    if len(spaeter) < tage:
        return None
    schluss = float(spaeter.iloc[tage - 1]["close"])
    veraenderung = (schluss / kurs - 1) * 100
    return veraenderung if richtung == "long" else -veraenderung


async def bewerte_picks(s: Session, kette) -> int:
    """Trägt für Picks die Ergebnisse nach 5 und 10 Handelstagen nach."""
    n = 0
    for p in s.exec(select(t.Pick).where((t.Pick.ergebnis_5t == None) | (t.Pick.ergebnis_10t == None))):  # noqa: E711
        try:
            df, _ = await kette.daily_history(p.symbol, 60)
        except Exception:
            continue
        for feld, tage in (("ergebnis_5t", 5), ("ergebnis_10t", 10)):
            if getattr(p, feld) is None:
                wert = pick_ergebnis(p.datum, p.kurs, p.richtung, df, tage)
                if wert is not None:
                    setattr(p, feld, round(wert, 2))
                    n += 1
        s.add(p)
    s.commit()
    return n


def speichere(s: Session, art: str, inhalt: dict) -> t.Bericht:
    b = t.Bericht(art=art, zeit=datetime.now(UTC), inhalt=json.dumps(inhalt, default=str))
    s.add(b)
    s.commit()
    s.refresh(b)
    return b


def letzter(s: Session, art: str) -> dict | None:
    b = s.exec(select(t.Bericht).where(t.Bericht.art == art).order_by(t.Bericht.zeit.desc())).first()  # type: ignore[attr-defined]
    if b is None:
        return None
    return {**json.loads(b.inhalt), "gespeichert_am": (b.zeit if b.zeit.tzinfo else b.zeit.replace(tzinfo=UTC)).isoformat(), "bericht_id": b.id}
