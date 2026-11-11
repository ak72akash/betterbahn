"""Demo-Anbieter: simulierte Kurse (Zufallsbewegung) zum Ausprobieren ohne Schlüssel
und ohne Internet. Nur aktiv, wenn ``demo`` in PROVIDER_ORDER steht; die Quelle heißt
überall sichtbar "demo" – das sind keine Marktdaten."""
from __future__ import annotations

import asyncio
import zlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from app.data.base import Kurs, PriceProvider, anbieter, verlauf_df

BASIS = {"IFX.DE": 38.5, "ENR.DE": 96.0, "SIE.DE": 232.0, "RHM.DE": 1710.0, "SAP.DE": 238.0,
         "NVDA": 188.0, "AMD": 236.0, "TSLA": 430.0, "PLTR": 178.0, "MU": 238.0, "AMAT": 232.0,
         "EURUSD": 1.16, "^GDAXI": 24100.0}
VOLA = {"EURUSD": 0.07, "^GDAXI": 0.16, "SAP.DE": 0.28, "SIE.DE": 0.27}


@anbieter("demo")
class DemoProvider(PriceProvider):
    kann_stream = True
    poll_intervall = 5.0
    takt: float = 1.0

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._rng = np.random.default_rng(7)
        self._kurse: dict[str, float] = {}

    def _schritt(self, symbol: str) -> float:
        alt = self._kurse.get(symbol) or BASIS.get(symbol, 100.0)
        sigma = VOLA.get(symbol, 0.5)
        neu = alt * float(np.exp(self._rng.standard_t(4) * sigma / np.sqrt(252 * 6.5 * 3600) * 6))
        self._kurse[symbol] = neu
        return neu

    async def latest_price(self, symbol: str) -> Kurs:
        return Kurs(symbol, round(self._schritt(symbol), 4), datetime.now(UTC), self.name, 0)

    async def daily_history(self, symbol: str, tage: int) -> pd.DataFrame:
        rng = np.random.default_rng(zlib.crc32(symbol.encode()))
        sigma = VOLA.get(symbol, 0.5)
        r = rng.standard_t(4, tage) / np.sqrt(2) * sigma / np.sqrt(252)
        ende = BASIS.get(symbol, 100.0)
        kurse = ende * np.exp(np.cumsum(r) - np.sum(r))
        tag0 = datetime.now(UTC).date()
        tage_liste = [d.date() for d in pd.bdate_range(end=tag0 - timedelta(days=1), periods=tage)]
        return verlauf_df([{"datum": d, "open": k, "high": k, "low": k, "close": k, "volume": 0.0}
                           for d, k in zip(tage_liste, kurse, strict=True)])

    async def stream(self, symbols: list[str]) -> AsyncIterator[Kurs]:
        while True:
            for s in symbols:
                if self._rng.random() < 0.6:
                    yield await self.latest_price(s)
            await asyncio.sleep(self.takt)
