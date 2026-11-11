"""Yahoo Finance als Rückfallebene ohne Schlüssel (Abfrage alle 15–30 Sekunden).

Genutzt wird derselbe öffentliche Chart-Endpunkt, den auch die Bibliothek
``yfinance`` anspricht – direkt über httpx, damit er in Tests gemockt werden kann.
Inoffizielle Schnittstelle, nur für den privaten Gebrauch; Kurse je nach Börse
verzögert (die Antwort nennt die Verzögerung)."""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from app.data.base import AnbieterFehler, Kurs, PriceProvider, anbieter, verlauf_df
from app.data.maerkte import markt
from app.data.ratelimit import RateLimiter


def yahoo_symbol(symbol: str) -> str:
    return "EURUSD=X" if markt(symbol) == "FX" else symbol


@anbieter("yfinance")
class YFinanceProvider(PriceProvider):
    URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    poll_intervall = 20.0

    def standard_limiter(self) -> RateLimiter:
        return RateLimiter(min_abstand=0.3, pro_minute=100)

    async def _chart(self, symbol: str, bereich: str) -> dict:
        d = await self._get(self.URL.format(sym=yahoo_symbol(symbol)),
                            params={"interval": "1d", "range": bereich})
        try:
            erg = d["chart"]["result"]
            if not erg:
                raise KeyError("result")
            return erg[0]
        except (KeyError, TypeError) as e:
            fehler = (d.get("chart") or {}).get("error") if isinstance(d, dict) else None
            raise AnbieterFehler(f"yfinance: kein Ergebnis für {symbol} ({fehler})") from e

    async def latest_price(self, symbol: str) -> Kurs:
        meta = (await self._chart(symbol, "1d")).get("meta", {})
        preis = meta.get("regularMarketPrice")
        if not preis:
            raise AnbieterFehler(f"yfinance: kein Kurs für {symbol}")
        ts = datetime.fromtimestamp(meta["regularMarketTime"], UTC) if meta.get("regularMarketTime") \
            else datetime.now(UTC)
        verz = int(meta.get("exchangeDataDelayedBy") or 0) * 60          # Angabe in Minuten
        return Kurs(symbol, float(preis), ts, self.name, verz)

    async def daily_history(self, symbol: str, tage: int) -> pd.DataFrame:
        bereich = "3mo" if tage <= 60 else "6mo" if tage <= 120 else "1y" if tage <= 250 else "2y"
        r = await self._chart(symbol, bereich)
        zeiten = r.get("timestamp") or []
        q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
        if not zeiten or not q.get("close"):
            raise AnbieterFehler(f"yfinance: kein Verlauf für {symbol}")
        sp = lambda n, i: (q.get(n) or [None] * len(zeiten))[i]
        return verlauf_df([{"datum": datetime.fromtimestamp(t, UTC).date(), "open": sp("open", i),
                            "high": sp("high", i), "low": sp("low", i), "close": sp("close", i),
                            "volume": sp("volume", i)} for i, t in enumerate(zeiten)]).tail(tage).reset_index(drop=True)
