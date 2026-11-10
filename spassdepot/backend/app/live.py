"""Hintergrunddienst für Kurs-Streams.

Hält die Verbindungen zu den Anbietern, abonniert alle Symbole aus Watchlist, Plan
und offenen Positionen, schreibt Updates in den Kursspeicher (Arbeitsspeicher) und
gebündelt in ``price_cache``, verteilt sie an verbundene Browser und prüft bei jedem
Update offener Positionen die Ausstiegsregeln."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.data.base import Kurs, PriceProvider
from app.data.kette import AnbieterKette
from app.data.maerkte import markt, markt_offen
from app.data.store import KursSpeicher

log = logging.getLogger("spassdepot.live")


def wartezeit(versuch: int, basis: float = 1.0, maximum: float = 60.0) -> float:
    """Wachsende Wartezeit vor dem Wiederaufbau: 1, 2, 4, … höchstens 60 Sekunden."""
    return float(min(maximum, basis * 2 ** max(0, versuch)))


class Verteiler:
    """Verteilt Nachrichten an alle verbundenen Clients (WebSocket und SSE)."""

    def __init__(self) -> None:
        self._abos: set[asyncio.Queue] = set()

    def abonniere(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._abos.add(q)
        return q

    def kuendige(self, q: asyncio.Queue) -> None:
        self._abos.discard(q)

    def sende(self, nachricht: dict) -> None:
        for q in list(self._abos):
            try:
                q.put_nowait(nachricht)
            except asyncio.QueueFull:          # langsamer Client: ältestes Update verwerfen
                q.get_nowait()
                q.put_nowait(nachricht)


class LiveDienst:
    def __init__(self, kette: AnbieterKette, store: KursSpeicher, verteiler: Verteiler,
                 symbole: Callable[[], list[str]],
                 bei_update: Callable[[str], list[dict]] | None = None,
                 cache_schreiben: Callable[[list[Kurs]], None] | None = None,
                 positions_symbole: Callable[[], list[str]] | None = None,
                 nachricht: Callable[[str], dict | None] | None = None,
                 takt: float = 1.0, poll_takt: float = 5.0, cache_takt: float = 15.0,
                 vergleich_takt: float = 300.0, ruhe_intervall: float = 300.0):
        self.kette, self.store, self.verteiler = kette, store, verteiler
        self._symbole, self._bei_update = symbole, bei_update
        self._cache_schreiben, self._positions_symbole = cache_schreiben, positions_symbole
        self._nachricht = nachricht or (lambda s: store.nachricht(s))
        self.takt, self.poll_takt, self.cache_takt = takt, poll_takt, cache_takt
        self.vergleich_takt, self.ruhe_intervall = vergleich_takt, ruhe_intervall
        self._geaendert: set[str] = set()
        self._fuer_cache: dict[tuple[str, str], Kurs] = {}
        self._aufgaben: list[asyncio.Task] = []
        self.laeuft = False

    # ---- Lebenszyklus ----
    async def start(self) -> None:
        self.laeuft = True
        schleifen = [self._verteil_schleife(), self._poll_schleife(), self._cache_schleife(),
                     self._vergleich_schleife()]
        schleifen += [self._stream_schleife(p) for p in self.kette.anbieter
                      if p.kann_stream and not p.nur_schlusskurs]
        self._aufgaben = [asyncio.create_task(c) for c in schleifen]

    async def stop(self) -> None:
        self.laeuft = False
        for a in self._aufgaben:
            a.cancel()
        await asyncio.gather(*self._aufgaben, return_exceptions=True)
        self._aufgaben = []
        self.cache_leeren()

    # ---- Verarbeitung ----
    def verarbeite(self, k: Kurs) -> None:
        self.store.aktualisiere(k)
        self._geaendert.add(k.symbol)
        self._fuer_cache[(k.symbol, k.quelle)] = k

    def verteile(self) -> None:
        """Schickt geänderte Kurse an die Clients und prüft Warnungen (max. 1×/Takt je Symbol)."""
        symbole, self._geaendert = self._geaendert, set()
        for s in symbole:
            n = self._nachricht(s)
            if n:
                self.verteiler.sende({"typ": "kurs", "daten": n})
            if self._bei_update:
                try:
                    for alarm in self._bei_update(s):
                        self.verteiler.sende({"typ": "alert", "daten": alarm})
                except Exception:
                    log.exception("Warnungsprüfung für %s fehlgeschlagen", s)

    def cache_leeren(self) -> None:
        kurse, self._fuer_cache = list(self._fuer_cache.values()), {}
        if kurse and self._cache_schreiben:
            try:
                self._cache_schreiben(kurse)
            except Exception:
                log.exception("price_cache konnte nicht geschrieben werden")

    # ---- Schleifen ----
    async def _verteil_schleife(self) -> None:
        while True:
            await asyncio.sleep(self.takt)
            self.verteile()

    async def _cache_schleife(self) -> None:
        while True:
            await asyncio.sleep(self.cache_takt)
            self.cache_leeren()

    def faellig(self, symbol: str, now: datetime | None = None) -> bool:
        """Braucht das Symbol eine Abfrage? (Kein frischer Kurs aus Stream oder letzter Abfrage.)"""
        now = now or datetime.now(UTC)
        b = self.store.bester(symbol)
        if b is None or b.schlusskurs:
            return True
        intervall = min((p.poll_intervall for p in self.kette.live_anbieter()), default=20.0)
        if not markt_offen(markt(symbol), now):
            intervall = self.ruhe_intervall
        return (now - b.empfangen).total_seconds() >= intervall

    async def poll_runde(self) -> int:
        n = 0
        for s in self._symbole():
            if not self.faellig(s):
                continue
            try:
                self.verarbeite(await self.kette.latest_price(s))
                n += 1
            except Exception as e:
                log.debug("Keine Abfrage möglich für %s: %s", s, e)
        return n

    async def _poll_schleife(self) -> None:
        while True:
            try:
                await self.poll_runde()
            except Exception:
                log.exception("Fehler in der Abfrage-Runde")
            await asyncio.sleep(self.poll_takt)

    async def vergleich_runde(self) -> None:
        """Zweite Quelle für offene Positionen abfragen, um Abweichungen > 3 % zu erkennen."""
        for s in (self._positions_symbole() if self._positions_symbole else []):
            b = self.store.bester(s)
            if b is None:
                continue
            try:
                k2 = await self.kette.latest_price(s, ausser={b.quelle})
                # Primärquelle bleibt der "beste" Kurs: Vergleichskurs zeitlich knapp davor einordnen
                self.verarbeite(replace(k2, empfangen=b.empfangen - timedelta(milliseconds=1)))
            except Exception:
                pass

    async def _vergleich_schleife(self) -> None:
        while True:
            await asyncio.sleep(self.vergleich_takt)
            await self.vergleich_runde()

    def _stream_symbole(self, p: PriceProvider) -> list[str]:
        return [s for s in self._symbole() if self.kette.stream_anbieter(s) is p]

    async def _konsumiere(self, p: PriceProvider, symbole: list[str]) -> None:
        async for k in p.stream(symbole):
            p.status.verbunden = True
            p.status.fehler_in_folge = 0
            p.status.letzter_erfolg = datetime.now(UTC)
            self.verarbeite(k)

    async def _stream_schleife(self, p: PriceProvider, pruef_takt: float = 15.0) -> None:
        versuch = 0
        while True:
            symbole = self._stream_symbole(p)
            if not symbole:
                await asyncio.sleep(pruef_takt)
                continue
            aufgabe = asyncio.create_task(self._konsumiere(p, symbole))
            neu_abonnieren = False
            try:
                while not aufgabe.done():
                    await asyncio.wait([aufgabe], timeout=pruef_takt)
                    if not aufgabe.done() and set(self._stream_symbole(p)) != set(symbole):
                        neu_abonnieren = True
                        break
            finally:
                if not aufgabe.done():
                    aufgabe.cancel()
                await asyncio.gather(aufgabe, return_exceptions=True)
            p.status.verbunden = False
            if neu_abonnieren:
                continue
            fehler = aufgabe.exception() if not aufgabe.cancelled() else None
            p.status.letzter_fehler = f"Stream: {fehler}" if fehler else "Stream beendet"
            if p.status.letzter_erfolg and (datetime.now(UTC) - p.status.letzter_erfolg).total_seconds() < 30:
                versuch = 0                       # lief eben noch: schnell wieder verbinden
            warte = wartezeit(versuch)
            versuch += 1
            log.warning("Stream %s getrennt (%s), neuer Versuch in %.0f s", p.name, fehler, warte)
            await asyncio.sleep(warte)
