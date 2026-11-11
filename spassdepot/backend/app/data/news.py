"""Nachrichten, Stimmung und Termine hinter einem Interface. Zunächst nur manuelle
Eingabe (Tabelle `events`); ein externer Anbieter kann später dieselbe Schnittstelle
implementieren."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from sqlmodel import Session, select


class NewsProvider(ABC):
    @abstractmethod
    def termine(self, session: Session, von: date, bis: date, symbol: str | None = None) -> list[dict]: ...

    def naechste_quartalszahlen(self, session: Session, symbol: str, ab: date, bis: date) -> date | None:
        for t in self.termine(session, ab, bis, symbol):
            if "zahlen" in t["art"].lower() or "earnings" in t["art"].lower():
                return t["datum"]
        return None


class ManuellerNewsProvider(NewsProvider):
    def termine(self, session: Session, von: date, bis: date, symbol: str | None = None) -> list[dict]:
        from app.journal.tabellen import Event
        q = select(Event).where(Event.datum >= von, Event.datum <= bis).order_by(Event.datum)  # type: ignore[arg-type]
        if symbol:
            q = q.where(Event.symbol == symbol)
        return [{"id": e.id, "datum": e.datum, "symbol": e.symbol, "art": e.art, "notiz": e.notiz,
                 "quelle": "manuell"} for e in session.exec(q)]
