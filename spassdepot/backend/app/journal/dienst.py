"""Datenbankgestützte Journal-Funktionen: Positions-Check, Depotstand, Live-Warnungen."""
from __future__ import annotations

from datetime import UTC, date, datetime, time

from sqlmodel import Session, select

from app.data.maerkte import BERLIN
from app.data.store import KursSpeicher
from app.journal import tabellen as t
from app.journal.berechnung import bewerte_position, depot, ist_offen


def eurusd(store: KursSpeicher) -> float | None:
    k = store.bester("EURUSD")
    return k.kurs if k else None


def offene_trades(s: Session, symbol: str | None = None) -> list[t.Trade]:
    q = select(t.Trade).where(t.Trade.datum_verkauf == None)  # noqa: E711
    if symbol:
        q = q.where(t.Trade.symbol == symbol)
    return list(s.exec(q.order_by(t.Trade.datum_kauf)))  # type: ignore[arg-type]


def heute_berlin(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(BERLIN).date()


def positionen(s: Session, store: KursSpeicher, g: dict, now: datetime | None = None,
               symbol: str | None = None) -> list[dict]:
    fx = eurusd(store)
    out = []
    for tr in offene_trades(s, symbol):
        k = store.bester(tr.symbol)
        kurs = k.kurs if k and not k.schlusskurs else None
        p = bewerte_position(tr, kurs, fx, heute_berlin(now), g)
        p["kurs_info"] = store.nachricht(tr.symbol, now, float(g["kurs_abweichung_pct"]), float(g["veraltet_nach_sek"]))
        p["eurusd"] = fx
        out.append(p)
    return out


def depot_stand(s: Session, store: KursSpeicher, g: dict, now: datetime | None = None) -> dict:
    trades = list(s.exec(select(t.Trade)))
    werte = {p["trade_id"]: p["wert"] for p in positionen(s, store, g, now)}
    return depot(trades, werte, g)


def branchen_belegung(s: Session, symbol: str) -> int:
    """Offene Positionen in derselben Branche wie ``symbol`` (laut Watchlist)."""
    branche = {w.symbol: w.branche for w in s.exec(select(t.WatchlistEintrag))}
    ziel = branche.get(symbol)
    if not ziel:
        return sum(1 for tr in offene_trades(s) if tr.symbol == symbol)
    return sum(1 for tr in offene_trades(s) if branche.get(tr.symbol) == ziel)


def filtere_neue_signale(signale: list[dict], trade_id: int, tag: date,
                         ausgeloest: set[tuple[int, str, date]]) -> list[dict]:
    """Entprellung (reine Funktion): jede Regel je Position höchstens einmal pro Tag."""
    neu = []
    for sig in signale:
        schluessel = (trade_id, sig["regel"], tag)
        if schluessel not in ausgeloest:
            ausgeloest.add(schluessel)
            neu.append(sig)
    return neu


class WarnDienst:
    """Prüft bei Kurs-Updates die Ausstiegsregeln offener Positionen und legt Warnungen an."""

    def __init__(self) -> None:
        self._ausgeloest: set[tuple[int, str, date]] = set()
        self._geladen: date | None = None

    def _lade(self, s: Session, tag: date) -> None:
        if self._geladen == tag:
            return
        beginn = datetime.combine(tag, time(0, 0), BERLIN).astimezone(UTC)
        self._ausgeloest = {(a.trade_id, a.regel, tag) for a in
                            s.exec(select(t.Alert).where(t.Alert.zeit >= beginn)) if a.trade_id is not None}
        self._geladen = tag

    def pruefe(self, s: Session, store: KursSpeicher, g: dict, symbol: str | None = None,
               now: datetime | None = None) -> list[t.Alert]:
        now = now or datetime.now(UTC)
        tag = heute_berlin(now)
        self._lade(s, tag)
        neu: list[t.Alert] = []
        for p in positionen(s, store, g, now, symbol):
            for sig in filtere_neue_signale(p["signale"], p["trade_id"], tag, self._ausgeloest):
                a = t.Alert(zeit=now, position=p["wertpapier"], trade_id=p["trade_id"],
                            regel=sig["regel"], text=sig["begruendung"])
                s.add(a)
                neu.append(a)
        if neu:
            s.commit()
            for a in neu:
                s.refresh(a)
        return neu


def alert_dict(a: t.Alert) -> dict:
    return {"id": a.id, "zeit": (a.zeit if a.zeit.tzinfo else a.zeit.replace(tzinfo=UTC)).isoformat(), "position": a.position,
            "trade_id": a.trade_id, "regel": a.regel, "text": a.text, "gelesen": a.gelesen}


def abo_symbole(s: Session) -> list[str]:
    """Alle Symbole aus Watchlist, Plan und offenen Positionen plus EUR/USD."""
    syms = {w.symbol for w in s.exec(select(t.WatchlistEintrag))}
    syms |= {p.symbol for p in s.exec(select(t.PlanEintrag)) if p.symbol and p.status in ("offen", "signal")}
    syms |= {tr.symbol for tr in s.exec(select(t.Trade)) if ist_offen(tr)}
    syms.add("EURUSD")
    return sorted(syms)
