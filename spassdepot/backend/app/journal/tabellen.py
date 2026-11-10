"""Datenbanktabellen (SQLModel) und die Ein-/Ausgabe-Schemas der API.

Einsatz und Ergebnis (in € und %) werden berechnet, nicht gespeichert."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import model_validator
from sqlmodel import Field, SQLModel

TradeTyp = Literal["aktie", "ko_long", "ko_short"]
Richtung = Literal["long", "short"]
PlanStatus = Literal["offen", "signal", "gekauft", "verworfen"]


# ---------- trades ----------
class TradeBasis(SQLModel):
    datum_kauf: date
    wertpapier: str = Field(min_length=1)
    wkn: str | None = None                       # nur vom Nutzer eingetragen, nie erzeugt
    typ: str = Field(default="ko_long")
    basiswert: str | None = None
    symbol: str = Field(min_length=1, index=True)
    stueck: float = Field(gt=0)
    kaufkurs: float = Field(gt=0)                # Kurs des gekauften Papiers in €
    ko_schwelle: float | None = Field(default=None, gt=0)
    bezugsverhaeltnis: float | None = Field(default=None, gt=0)
    prognose_p_gewinn: float | None = Field(default=None, ge=0, le=1)
    ziel: float | None = Field(default=None, gt=0)   # Kurs des Basiswerts
    stop: float | None = Field(default=None, gt=0)   # Kurs des Basiswerts
    these: str | None = None
    datum_verkauf: date | None = None
    verkaufskurs: float | None = Field(default=None, ge=0)
    gebuehren: float = Field(default=0.0, ge=0)
    lehre: str | None = None


class Trade(TradeBasis, table=True):
    __tablename__ = "trades"
    id: int | None = Field(default=None, primary_key=True)


class TradeNeu(TradeBasis):
    typ: TradeTyp = "ko_long"

    @model_validator(mode="after")
    def pflichtfelder(self):
        if self.typ != "aktie":
            if self.ko_schwelle is None:
                raise ValueError("Bei Knock-outs ist die KO-Schwelle ein Pflichtfeld.")
            if self.bezugsverhaeltnis is None:
                raise ValueError("Bei Knock-outs ist das Bezugsverhältnis ein Pflichtfeld.")
        if (self.datum_verkauf is None) != (self.verkaufskurs is None):
            raise ValueError("Verkaufsdatum und Verkaufskurs gehören zusammen.")
        if self.datum_verkauf and self.datum_verkauf < self.datum_kauf:
            raise ValueError("Das Verkaufsdatum liegt vor dem Kaufdatum.")
        return self


class TradeAendern(SQLModel):
    datum_kauf: date | None = None
    wertpapier: str | None = None
    wkn: str | None = None
    typ: TradeTyp | None = None
    basiswert: str | None = None
    symbol: str | None = None
    stueck: float | None = Field(default=None, gt=0)
    kaufkurs: float | None = Field(default=None, gt=0)
    ko_schwelle: float | None = Field(default=None, gt=0)
    bezugsverhaeltnis: float | None = Field(default=None, gt=0)
    prognose_p_gewinn: float | None = Field(default=None, ge=0, le=1)
    ziel: float | None = None
    stop: float | None = None
    these: str | None = None
    datum_verkauf: date | None = None
    verkaufskurs: float | None = Field(default=None, ge=0)
    gebuehren: float | None = Field(default=None, ge=0)
    lehre: str | None = None


class TradeSchliessen(SQLModel):
    datum_verkauf: date
    verkaufskurs: float = Field(ge=0)
    stueck: float | None = Field(default=None, gt=0)     # leer = alles; kleiner = Teilverkauf
    gebuehren: float = Field(default=0.0, ge=0)
    lehre: str | None = None


class TradeAusgabe(TradeBasis):
    id: int
    einsatz: float
    ergebnis_eur: float | None
    ergebnis_pct: float | None
    offen: bool


# ---------- picks ----------
class PickBasis(SQLModel):
    datum: date
    aktie: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    richtung: str = "long"
    kurs: float = Field(gt=0)
    quelle: str | None = None
    ziel: float = Field(gt=0)
    stop: float = Field(gt=0)
    p_ziel_vor_stop: float | None = Field(default=None, ge=0, le=1)
    katalysator: str | None = None
    ergebnis_5t: float | None = None             # % in Pick-Richtung
    ergebnis_10t: float | None = None


class Pick(PickBasis, table=True):
    __tablename__ = "picks"
    id: int | None = Field(default=None, primary_key=True)


class PickNeu(SQLModel):
    datum: date
    aktie: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    richtung: Richtung = "long"
    kurs: float = Field(gt=0)
    quelle: str | None = None
    ziel: float = Field(gt=0)
    stop: float = Field(gt=0)
    katalysator: str | None = None
    tage: int = Field(default=10, ge=1, le=30)
    sigma: float | None = Field(default=None, gt=0, le=3)    # leer = aus Kursverlauf
    trotzdem_speichern: bool = False


class PickAendern(SQLModel):
    aktie: str | None = None
    katalysator: str | None = None
    ergebnis_5t: float | None = None
    ergebnis_10t: float | None = None


# ---------- plan ----------
class PlanBasis(SQLModel):
    woche: str = Field(min_length=1)             # z. B. 2026-KW46
    position: str = Field(min_length=1)
    symbol: str | None = None                    # für Live-Kurse (Ergänzung zur Vorgabe)
    typ: str = "ko_long"
    einsatz: float = Field(default=100.0, gt=0)
    kaufzeitpunkt: str | None = None
    kaufbedingung: str | None = None
    filter: str | None = None                    # Suchwerte für den Broker als Text
    ziel: str | None = None
    ausstieg: str | None = None
    status: str = "offen"


class PlanEintrag(PlanBasis, table=True):
    __tablename__ = "plan"
    id: int | None = Field(default=None, primary_key=True)


class PlanNeu(PlanBasis):
    typ: TradeTyp = "ko_long"
    status: PlanStatus = "offen"


class PlanAendern(SQLModel):
    woche: str | None = None
    position: str | None = None
    symbol: str | None = None
    typ: TradeTyp | None = None
    einsatz: float | None = Field(default=None, gt=0)
    kaufzeitpunkt: str | None = None
    kaufbedingung: str | None = None
    filter: str | None = None
    ziel: str | None = None
    ausstieg: str | None = None
    status: PlanStatus | None = None


# ---------- watchlist / events ----------
class WatchlistBasis(SQLModel):
    symbol: str = Field(min_length=1, unique=True)
    name: str = Field(min_length=1)
    branche: str | None = None


class WatchlistEintrag(WatchlistBasis, table=True):
    __tablename__ = "watchlist"
    id: int | None = Field(default=None, primary_key=True)


class WatchlistAendern(SQLModel):
    name: str | None = None
    branche: str | None = None


class EventBasis(SQLModel):
    datum: date
    symbol: str | None = None
    art: str = Field(min_length=1)               # z. B. Quartalszahlen, Notiz, Zinsentscheid
    notiz: str | None = None


class Event(EventBasis, table=True):
    __tablename__ = "events"
    id: int | None = Field(default=None, primary_key=True)


class EventAendern(SQLModel):
    datum: date | None = None
    symbol: str | None = None
    art: str | None = None
    notiz: str | None = None


# ---------- settings / cache / alerts / berichte ----------
class Setting(SQLModel, table=True):
    __tablename__ = "settings"
    schluessel: str = Field(primary_key=True)
    wert: str                                    # JSON


class PriceCache(SQLModel, table=True):
    __tablename__ = "price_cache"
    symbol: str = Field(primary_key=True)
    quelle: str = Field(primary_key=True)
    kurs: float
    zeit: datetime
    empfangen: datetime
    verzoegerung_sek: int = 0
    schlusskurs: bool = False


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"
    id: int | None = Field(default=None, primary_key=True)
    zeit: datetime
    position: str
    trade_id: int | None = Field(default=None, index=True)
    regel: str
    text: str
    gelesen: bool = False


class Bericht(SQLModel, table=True):
    __tablename__ = "berichte"
    id: int | None = Field(default=None, primary_key=True)
    art: str = Field(index=True)                 # morgen | positionen | woche
    zeit: datetime
    inhalt: str                                  # JSON


class Kursverlauf(SQLModel, table=True):
    """Cache der Tagesverläufe (schont die Tageslimits, v. a. Alpha Vantage)."""
    __tablename__ = "kursverlauf"
    symbol: str = Field(primary_key=True)
    quelle: str
    abgerufen: datetime
    daten: str                                   # JSON (Liste von Tageszeilen)


class ApiNutzung(SQLModel, table=True):
    """Tageszähler je Anbieter – übersteht Neustarts."""
    __tablename__ = "api_nutzung"
    anbieter: str = Field(primary_key=True)
    tag: date = Field(primary_key=True)
    anzahl: int = 0
