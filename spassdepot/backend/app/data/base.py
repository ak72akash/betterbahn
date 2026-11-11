"""Gemeinsames Interface aller Kursquellen und die Anbieter-Registrierung.

Einen weiteren Anbieter ergänzen: eine Datei in ``app/data/providers/`` anlegen,
von `PriceProvider` ableiten und die Klasse mit ``@anbieter("name")`` markieren.
Danach kann der Name in ``PROVIDER_ORDER`` verwendet werden."""
from __future__ import annotations

import importlib
import pkgutil
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd

from app.data.ratelimit import RateLimiter


def jetzt() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Kurs:
    symbol: str
    kurs: float
    zeitstempel: datetime            # Zeit des Kurses laut Quelle (UTC)
    quelle: str
    verzoegerung_sek: int = 0
    schlusskurs: bool = False        # True: nur Tagesschluss, nie als aktueller Kurs zeigen
    empfangen: datetime = field(default_factory=jetzt)

    def __iter__(self):              # (kurs, zeitstempel, quelle, verzoegerung_sek)
        return iter((self.kurs, self.zeitstempel, self.quelle, self.verzoegerung_sek))


class AnbieterFehler(Exception):
    """Abfrage beim Anbieter fehlgeschlagen (Ausfall, unbekanntes Symbol, Tarifgrenze)."""


class NichtUnterstuetzt(AnbieterFehler):
    """Der Anbieter liefert dieses Symbol im vorhandenen Tarif nicht."""


@dataclass
class AnbieterStatus:
    verbunden: bool = False          # Stream steht bzw. letzte Abfrage erfolgreich
    letzter_erfolg: datetime | None = None
    letzter_fehler: str | None = None
    fehler_in_folge: int = 0
    pausiert_bis: float = 0.0        # monotone Uhr


class PriceProvider(ABC):
    name: str = ""
    schluessel_env: str | None = None    # Name der Umgebungsvariablen mit dem API-Schlüssel
    kann_kurs: bool = True               # liefert aktuelle Kurse per Abfrage
    kann_stream: bool = False
    kann_historie: bool = True
    nur_schlusskurs: bool = False        # z. B. Alpha Vantage Free: nie als Live-Kurs nutzen
    poll_intervall: float = 20.0

    def __init__(self, api_key: str = "", client: httpx.AsyncClient | None = None,
                 ws_connect: Callable[..., Any] | None = None, limiter: RateLimiter | None = None):
        self.api_key = api_key
        self._client = client
        self._ws_connect = ws_connect
        self.limiter = limiter or self.standard_limiter()
        self.status = AnbieterStatus()

    def standard_limiter(self) -> RateLimiter:
        return RateLimiter()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "Mozilla/5.0 (spassdepot)"})
        return self._client

    def ws_connect(self, url: str):
        if self._ws_connect is not None:
            return self._ws_connect(url)
        import websockets
        return websockets.connect(url, open_timeout=10, ping_interval=20)

    async def _get(self, url: str, **kw) -> Any:
        await self.limiter.acquire()
        try:
            r = await self.client.get(url, **kw)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise AnbieterFehler(f"{self.name}: {type(e).__name__}: {e}") from e

    def unterstuetzt(self, symbol: str) -> bool:
        return True

    @abstractmethod
    async def latest_price(self, symbol: str) -> Kurs: ...

    async def daily_history(self, symbol: str, tage: int) -> pd.DataFrame:
        raise NichtUnterstuetzt(f"{self.name} liefert keine Tagesverläufe")

    async def stream(self, symbols: list[str]) -> AsyncIterator[Kurs]:
        raise NichtUnterstuetzt(f"{self.name} bietet keinen Kurs-Stream")
        yield  # pragma: no cover

    async def schliessen(self) -> None:
        if self._client is not None:
            await self._client.aclose()


ANBIETER: dict[str, type[PriceProvider]] = {}


def anbieter(name: str):
    def deko(cls: type[PriceProvider]) -> type[PriceProvider]:
        cls.name = name
        ANBIETER[name] = cls
        return cls
    return deko


def lade_anbieter() -> dict[str, type[PriceProvider]]:
    """Importiert alle Module in app.data.providers – jede Datei registriert sich selbst."""
    import app.data.providers as paket
    for m in pkgutil.iter_modules(paket.__path__):
        importlib.import_module(f"{paket.__name__}.{m.name}")
    return ANBIETER


def verlauf_df(zeilen: list[dict]) -> pd.DataFrame:
    """Einheitliches Format für Tagesverläufe: Spalten datum, open, high, low, close, volume."""
    df = pd.DataFrame(zeilen, columns=["datum", "open", "high", "low", "close", "volume"])
    df = df.dropna(subset=["close"]).sort_values("datum").reset_index(drop=True)
    return df
