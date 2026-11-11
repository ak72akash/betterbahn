"""Alpha Vantage: nur Tagesverläufe und Volatilität.

Free-Key: höchstens 25 Abfragen pro Tag und 1 pro Sekunde; GLOBAL_QUOTE liefert nur
den Schlusskurs des Vortags. Deshalb ``nur_schlusskurs`` – die Kette nutzt diesen
Anbieter nie für aktuelle Kurse. Deutsche Aktien: Endung ``.DEX`` (IFX.DEX)."""
from __future__ import annotations

from datetime import UTC, date, datetime, time

import pandas as pd

from app.data.base import AnbieterFehler, Kurs, PriceProvider, anbieter, verlauf_df
from app.data.maerkte import markt
from app.data.ratelimit import LimitErreicht, RateLimiter


def av_symbol(symbol: str) -> str:
    return symbol[:-3] + ".DEX" if markt(symbol) == "XETRA" else symbol


@anbieter("alphavantage")
class AlphaVantageProvider(PriceProvider):
    schluessel_env = "ALPHAVANTAGE_API_KEY"
    nur_schlusskurs = True
    URL = "https://www.alphavantage.co/query"

    def standard_limiter(self) -> RateLimiter:
        return RateLimiter(min_abstand=1.1, pro_tag=25)

    def unterstuetzt(self, symbol: str) -> bool:
        return markt(symbol) in ("US", "XETRA")

    async def _abfrage(self, **params) -> dict:
        d = await self._get(self.URL, params={**params, "apikey": self.api_key})
        if not isinstance(d, dict):
            raise AnbieterFehler("alphavantage: unerwartete Antwort")
        for feld in ("Note", "Information"):
            if feld in d:                    # Limit-Hinweis statt Daten
                raise LimitErreicht(f"alphavantage: {d[feld][:120]}")
        if "Error Message" in d:
            raise AnbieterFehler(f"alphavantage: {d['Error Message'][:120]}")
        return d

    async def latest_price(self, symbol: str) -> Kurs:
        d = (await self._abfrage(function="GLOBAL_QUOTE", symbol=av_symbol(symbol))).get("Global Quote") or {}
        if not d.get("05. price"):
            raise AnbieterFehler(f"alphavantage: kein Schlusskurs für {symbol}")
        tag = date.fromisoformat(d["07. latest trading day"])
        return Kurs(symbol, float(d["05. price"]), datetime.combine(tag, time(22, 0), UTC),
                    self.name, 86400, schlusskurs=True)

    async def daily_history(self, symbol: str, tage: int) -> pd.DataFrame:
        d = await self._abfrage(function="TIME_SERIES_DAILY", symbol=av_symbol(symbol), outputsize="compact")
        reihe = d.get("Time Series (Daily)") or {}
        if not reihe:
            raise AnbieterFehler(f"alphavantage: kein Verlauf für {symbol}")
        return verlauf_df([{"datum": date.fromisoformat(k), "open": float(v["1. open"]),
                            "high": float(v["2. high"]), "low": float(v["3. low"]),
                            "close": float(v["4. close"]), "volume": float(v["5. volume"])}
                           for k, v in reihe.items()]).tail(tage).reset_index(drop=True)
