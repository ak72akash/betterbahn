"""Datenbank-Anbindung, erste Befüllung und kleine Speicher-Helfer."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from io import StringIO
from pathlib import Path

import pandas as pd
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.data.base import Kurs
from app.journal import tabellen as t
from app.rules.grenzen import STANDARD

WATCHLIST_START = [
    ("IFX.DE", "Infineon", "Halbleiter"), ("ENR.DE", "Siemens Energy", "Energie"),
    ("SIE.DE", "Siemens", "Industrie"), ("RHM.DE", "Rheinmetall", "Rüstung"),
    ("SAP.DE", "SAP", "Software"), ("NVDA", "Nvidia", "Halbleiter"), ("AMD", "AMD", "Halbleiter"),
    ("TSLA", "Tesla", "Auto"), ("PLTR", "Palantir", "Software"), ("MU", "Micron", "Halbleiter"),
    ("AMAT", "Applied Materials", "Halbleiter"),
]


def erstelle_engine(url: str):
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    kw: dict = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if ":memory:" in url or url == "sqlite://":
        kw["poolclass"] = StaticPool
    return create_engine(url, **kw)


def initialisiere(engine) -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        if s.exec(select(t.WatchlistEintrag)).first() is None and s.get(t.Setting, "_befuellt") is None:
            for sym, name, branche in WATCHLIST_START:
                s.add(t.WatchlistEintrag(symbol=sym, name=name, branche=branche))
        if s.get(t.Setting, "_befuellt") is None:
            s.add(t.Setting(schluessel="_befuellt", wert="true"))
        s.commit()


# ---------- Einstellungen ----------
def lade_grenzen(s: Session) -> dict:
    g = dict(STANDARD)
    for e in s.exec(select(t.Setting)):
        if e.schluessel in STANDARD:
            g[e.schluessel] = json.loads(e.wert)
    return g


def speichere_grenzen(s: Session, werte: dict) -> dict:
    for k, v in werte.items():
        if k not in STANDARD:
            raise ValueError(f"Unbekannte Einstellung: {k}")
        vorgabe = STANDARD[k]
        if isinstance(vorgabe, bool):
            if not isinstance(v, bool):
                raise ValueError(f"{k} muss wahr oder falsch sein")
        elif isinstance(vorgabe, (int, float)):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{k} muss eine Zahl sein")
            v = int(v) if isinstance(vorgabe, int) else float(v)
        elif not isinstance(v, str) or not v.strip():
            raise ValueError(f"{k} muss ein Text sein")
        s.merge(t.Setting(schluessel=k, wert=json.dumps(v)))
    s.commit()
    return lade_grenzen(s)


# ---------- Kurs-Cache ----------
def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def schreibe_kurse(engine, kurse: list[Kurs]) -> None:
    if not kurse:
        return
    with Session(engine) as s:
        for k in kurse:
            s.merge(t.PriceCache(symbol=k.symbol, quelle=k.quelle, kurs=k.kurs, zeit=k.zeitstempel,
                                 empfangen=k.empfangen, verzoegerung_sek=k.verzoegerung_sek,
                                 schlusskurs=k.schlusskurs))
        s.commit()


def lese_kurse(engine) -> list[Kurs]:
    with Session(engine) as s:
        return [Kurs(c.symbol, c.kurs, _utc(c.zeit), c.quelle, c.verzoegerung_sek, c.schlusskurs, _utc(c.empfangen))
                for c in s.exec(select(t.PriceCache))]


# ---------- Verlaufs-Cache ----------
def verlauf_lesen(engine, symbol: str, tage: int, now: datetime | None = None):
    """Cache-Treffer, wenn heute schon abgerufen und genug Tage vorhanden."""
    now = now or datetime.now(UTC)
    with Session(engine) as s:
        v = s.get(t.Kursverlauf, symbol)
        if v is None or _utc(v.abgerufen).date() != now.date():
            return None
        df = pd.read_json(StringIO(v.daten), orient="records")
        df["datum"] = pd.to_datetime(df["datum"]).dt.date
        if len(df) < min(tage, 61):
            return None
        return df.tail(tage).reset_index(drop=True), f"{v.quelle} (Cache)"


def verlauf_schreiben(engine, symbol: str, quelle: str, df: pd.DataFrame) -> None:
    daten = df.assign(datum=df["datum"].astype(str)).to_json(orient="records")
    with Session(engine) as s:
        s.merge(t.Kursverlauf(symbol=symbol, quelle=quelle, abgerufen=datetime.now(UTC), daten=daten))
        s.commit()


# ---------- Tageszähler ----------
def zaehler_laden(engine, anbieter: str):
    def laden(tag: date) -> int:
        with Session(engine) as s:
            z = s.get(t.ApiNutzung, (anbieter, tag))
            return z.anzahl if z else 0
    return laden


def zaehler_speichern(engine, anbieter: str):
    def speichern(tag: date, anzahl: int) -> None:
        with Session(engine) as s:
            s.merge(t.ApiNutzung(anbieter=anbieter, tag=tag, anzahl=anzahl))
            s.commit()
    return speichern
