"""Symbol-Konventionen, Handelszeiten und Kennzeichnung von Kursen.

Symbole: US-Aktien ohne Endung (NVDA), Xetra mit ``.DE`` (IFX.DE), Wechselkurs
``EURUSD``, Indizes mit ``^`` (^GDAXI). Handelszeiten in deutscher Zeit, Mo–Fr,
ohne Feiertagskalender (Annahme, siehe README)."""
from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from app.data.base import Kurs

BERLIN = ZoneInfo("Europe/Berlin")
ZEITEN = {
    "XETRA": (time(9, 0), time(17, 30)),
    "GETTEX": (time(8, 0), time(22, 0)),
    "US": (time(15, 30), time(22, 0)),
    "FX": (time(0, 0), time(23, 59, 59)),
}
ZEITEN["INDEX"] = ZEITEN["XETRA"]
MARKT_NAME = {"XETRA": "Xetra", "GETTEX": "gettex", "US": "USA", "FX": "Devisen", "INDEX": "Index"}


def markt(symbol: str) -> str:
    s = symbol.upper()
    if s == "EURUSD":
        return "FX"
    if s.startswith("^"):
        return "INDEX"
    if s.endswith(".DE"):
        return "XETRA"
    return "US"


def waehrung(symbol: str) -> str:
    return "USD" if markt(symbol) == "US" else "EUR"


def markt_offen(m: str, now: datetime | None = None) -> bool:
    lokal = (now or datetime.now(UTC)).astimezone(BERLIN)
    if lokal.weekday() >= 5:
        return False
    von, bis = ZEITEN[m]
    return von <= lokal.time() <= bis


def kurs_etikett(k: Kurs) -> str:
    if k.schlusskurs:
        return "Schlusskurs"
    if k.verzoegerung_sek <= 0:
        return "Echtzeit"
    return f"verzögert ({max(1, round(k.verzoegerung_sek / 60))} Min)"


def ist_veraltet(k: Kurs, now: datetime | None = None, nach_sek: float = 60) -> bool:
    """Veraltet = während der Handelszeit seit mehr als ``nach_sek`` kein Update empfangen."""
    now = now or datetime.now(UTC)
    if k.schlusskurs or not markt_offen(markt(k.symbol), now):
        return False
    return (now - k.empfangen).total_seconds() > nach_sek


def kurs_status(k: Kurs, now: datetime | None = None, nach_sek: float = 60) -> dict:
    now = now or datetime.now(UTC)
    m = markt(k.symbol)
    offen = markt_offen(m, now)
    return {
        "etikett": kurs_etikett(k),
        "veraltet": ist_veraltet(k, now, nach_sek),
        "markt": MARKT_NAME[m],
        "markt_offen": offen,
        "gettex_offen": markt_offen("GETTEX", now),
        "hinweis": None if offen else "Markt geschlossen",
    }
