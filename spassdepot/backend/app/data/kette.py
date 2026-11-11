"""Anbieter-Kette: Reihenfolge = Priorität, automatischer Wechsel bei Ausfall."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

import pandas as pd

from app.config import Konfig
from app.data.base import AnbieterFehler, Kurs, NichtUnterstuetzt, PriceProvider, lade_anbieter
from app.data.ratelimit import LimitErreicht

log = logging.getLogger("spassdepot.kette")


class KeinKurs(AnbieterFehler):
    """Kein Anbieter der Kette konnte liefern."""


def pause_nach_fehlern(fehler_in_folge: int) -> float:
    """Ab dem dritten Fehler in Folge pausiert ein Anbieter (30 s, 60 s, … max. 10 Min)."""
    if fehler_in_folge < 3:
        return 0.0
    return float(min(600, 30 * 2 ** (fehler_in_folge - 3)))


class AnbieterKette:
    def __init__(self, anbieter: list[PriceProvider], clock: Callable[[], float] = time.monotonic,
                 verlauf_lesen: Callable[[str, int], tuple[pd.DataFrame, str] | None] | None = None,
                 verlauf_schreiben: Callable[[str, str, pd.DataFrame], None] | None = None):
        self.anbieter = anbieter
        self._clock = clock
        self._gesperrt: dict[tuple[str, str], float] = {}      # (Anbieter, Symbol) -> bis
        self._verlauf_lesen, self._verlauf_schreiben = verlauf_lesen, verlauf_schreiben

    def _nutzbar(self, p: PriceProvider, symbol: str) -> bool:
        now = self._clock()
        return (p.unterstuetzt(symbol) and p.status.pausiert_bis <= now
                and self._gesperrt.get((p.name, symbol), 0) <= now)

    def _erfolg(self, p: PriceProvider) -> None:
        p.status.verbunden, p.status.fehler_in_folge = True, 0
        p.status.letzter_erfolg, p.status.letzter_fehler = datetime.now(UTC), None

    def _fehler(self, p: PriceProvider, symbol: str, e: Exception) -> None:
        if isinstance(e, LimitErreicht):
            p.status.letzter_fehler = str(e)
            return                                   # Limit ist kein Ausfall
        if isinstance(e, NichtUnterstuetzt):
            self._gesperrt[(p.name, symbol)] = self._clock() + 3600   # nicht jede Runde neu probieren
            p.status.letzter_fehler = str(e)
            return
        p.status.fehler_in_folge += 1
        p.status.letzter_fehler = str(e)[:200]
        p.status.verbunden = False
        p.status.pausiert_bis = self._clock() + pause_nach_fehlern(p.status.fehler_in_folge)
        log.warning("Anbieter %s ausgefallen für %s: %s", p.name, symbol, e)

    def live_anbieter(self) -> list[PriceProvider]:
        return [p for p in self.anbieter if p.kann_kurs and not p.nur_schlusskurs]

    def stream_anbieter(self, symbol: str) -> PriceProvider | None:
        """Erster Anbieter in der Reihenfolge, der das Symbol streamen kann."""
        for p in self.anbieter:
            if p.kann_stream and not p.nur_schlusskurs and self._nutzbar(p, symbol):
                return p
        return None

    async def latest_price(self, symbol: str, ausser: frozenset[str] | set[str] = frozenset()) -> Kurs:
        fehler = []
        for p in self.live_anbieter():
            if p.name in ausser or not self._nutzbar(p, symbol):
                continue
            try:
                k = await p.latest_price(symbol)
                self._erfolg(p)
                return k
            except (AnbieterFehler, LimitErreicht) as e:
                self._fehler(p, symbol, e)
                fehler.append(f"{p.name}: {e}")
        raise KeinKurs(f"Kein Anbieter liefert einen aktuellen Kurs für {symbol}. " + " | ".join(fehler))

    async def daily_history(self, symbol: str, tage: int = 120) -> tuple[pd.DataFrame, str]:
        """Tagesverlauf: zuerst Cache, dann Live-Anbieter, Alpha Vantage zuletzt.
        Gibt (DataFrame, Quelle) zurück."""
        if self._verlauf_lesen:
            treffer = self._verlauf_lesen(symbol, tage)
            if treffer is not None:
                return treffer
        fehler = []
        reihenfolge = sorted((p for p in self.anbieter if p.kann_historie), key=lambda p: p.nur_schlusskurs)
        for p in reihenfolge:
            if not self._nutzbar(p, symbol):
                continue
            try:
                df = await p.daily_history(symbol, tage)
                if len(df) < 2:
                    raise AnbieterFehler(f"{p.name}: zu wenig Daten")
                self._erfolg(p)
                if self._verlauf_schreiben:
                    self._verlauf_schreiben(symbol, p.name, df)
                return df, p.name
            except (AnbieterFehler, LimitErreicht) as e:
                self._fehler(p, symbol, e)
                fehler.append(f"{p.name}: {e}")
        raise KeinKurs(f"Kein Anbieter liefert einen Tagesverlauf für {symbol}. " + " | ".join(fehler))

    def status(self) -> list[dict]:
        now = self._clock()
        return [{
            "name": p.name,
            "verbunden": p.status.verbunden,
            "stream": p.kann_stream,
            "nur_schlusskurs": p.nur_schlusskurs,
            "pausiert": p.status.pausiert_bis > now,
            "letzter_erfolg": p.status.letzter_erfolg.isoformat() if p.status.letzter_erfolg else None,
            "letzter_fehler": p.status.letzter_fehler,
            "abfragen_heute": p.limiter.heute_anzahl,
            "limit_tag": p.limiter.pro_tag,
            "verbleibend_heute": p.limiter.verbleibend_heute,
        } for p in self.anbieter]

    async def schliessen(self) -> None:
        for p in self.anbieter:
            await p.schliessen()


def baue_kette(cfg: Konfig, limiter_fabrik: Callable[[PriceProvider], None] | None = None, **kw) -> tuple[AnbieterKette, list[dict]]:
    """Erzeugt die Kette aus PROVIDER_ORDER. Anbieter ohne Schlüssel werden übersprungen
    und in der zweiten Rückgabe als "nicht konfiguriert" aufgeführt."""
    klassen = lade_anbieter()
    aktiv: list[PriceProvider] = []
    fehlend: list[dict] = []
    for name in cfg.provider_order:
        cls = klassen.get(name)
        if cls is None:
            fehlend.append({"name": name, "grund": "unbekannter Anbieter"})
            continue
        key = cfg.schluessel(cls.schluessel_env) if cls.schluessel_env else ""
        if cls.schluessel_env and not key:
            fehlend.append({"name": name, "grund": f"{cls.schluessel_env} fehlt in .env"})
            continue
        p = cls(api_key=key)
        if limiter_fabrik:
            limiter_fabrik(p)
        aktiv.append(p)
    return AnbieterKette(aktiv, **kw), fehlend
