"""Twelve Data: REST und WebSocket. Europäische Börsen (XETR) je nach Tarif."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pandas as pd

from app.data.base import AnbieterFehler, Kurs, NichtUnterstuetzt, PriceProvider, anbieter, verlauf_df
from app.data.maerkte import markt
from app.data.ratelimit import RateLimiter


def td_symbol(symbol: str) -> tuple[str, str | None]:
    """Internes Symbol -> (Twelve-Data-Symbol, Börse)."""
    m = markt(symbol)
    if m == "FX":
        return "EUR/USD", None
    if m == "XETRA":
        return symbol[:-3], "XETR"
    return symbol, None


@anbieter("twelvedata")
class TwelveDataProvider(PriceProvider):
    schluessel_env = "TWELVEDATA_API_KEY"
    kann_stream = True
    REST = "https://api.twelvedata.com"
    WS = "wss://ws.twelvedata.com/v1/quotes/price"

    def standard_limiter(self) -> RateLimiter:
        return RateLimiter(min_abstand=0.2, pro_minute=8, pro_tag=800)

    def unterstuetzt(self, symbol: str) -> bool:
        return markt(symbol) in ("US", "XETRA", "FX")

    def _params(self, symbol: str) -> dict:
        sym, boerse = td_symbol(symbol)
        return {"symbol": sym, **({"exchange": boerse} if boerse else {})}

    async def _abfrage(self, pfad: str, params: dict) -> dict:
        d = await self._get(f"{self.REST}/{pfad}", params=params,
                            headers={"Authorization": f"apikey {self.api_key}"})
        if isinstance(d, dict) and d.get("status") == "error":
            text = f"twelvedata: {d.get('message', 'Fehler')}"
            if d.get("code") in (400, 403, 404):          # Symbol/Börse nicht im Tarif
                raise NichtUnterstuetzt(text)
            raise AnbieterFehler(text)
        return d

    async def latest_price(self, symbol: str) -> Kurs:
        d = await self._abfrage("price", self._params(symbol))
        try:
            return Kurs(symbol, float(d["price"]), datetime.now(UTC), self.name, 0)
        except (KeyError, TypeError, ValueError) as e:
            raise AnbieterFehler(f"twelvedata: unerwartete Antwort für {symbol}") from e

    async def daily_history(self, symbol: str, tage: int) -> pd.DataFrame:
        d = await self._abfrage("time_series", {**self._params(symbol), "interval": "1day",
                                                "outputsize": min(tage, 5000)})
        werte = d.get("values") or []
        if not werte:
            raise AnbieterFehler(f"twelvedata: kein Verlauf für {symbol}")
        f = lambda x: float(x) if x not in (None, "") else None
        return verlauf_df([{"datum": date.fromisoformat(v["datetime"][:10]), "open": f(v.get("open")),
                            "high": f(v.get("high")), "low": f(v.get("low")), "close": f(v.get("close")),
                            "volume": f(v.get("volume"))} for v in werte])

    async def stream(self, symbols: list[str]) -> AsyncIterator[Kurs]:
        zuordnung: dict[str, str] = {}
        abo: list[str] = []
        for s in symbols:
            if self.unterstuetzt(s):
                sym, boerse = td_symbol(s)
                abo.append(f"{sym}:{boerse}" if boerse else sym)
                zuordnung[abo[-1]] = zuordnung[sym] = s     # Antworten nennen die Börse nicht immer
        async with self.ws_connect(f"{self.WS}?apikey={self.api_key}") as ws:
            await ws.send(json.dumps({"action": "subscribe", "params": {"symbols": ",".join(abo)}}))
            async for roh in ws:
                msg = json.loads(roh)
                if msg.get("event") == "subscribe-status" and msg.get("status") == "error":
                    raise AnbieterFehler("twelvedata: Abonnement abgelehnt (Tarif?)")
                if msg.get("event") != "price":
                    continue
                intern = zuordnung.get(msg.get("symbol", ""))
                if intern is None:
                    continue
                ts = datetime.fromtimestamp(msg["timestamp"], UTC) if msg.get("timestamp") else datetime.now(UTC)
                yield Kurs(intern, float(msg["price"]), ts, self.name, 0)
