"""Finnhub: WebSocket-Trades in Echtzeit und REST-Quote – im kostenlosen Zugang nur US-Aktien."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.data.base import AnbieterFehler, Kurs, PriceProvider, anbieter
from app.data.maerkte import markt
from app.data.ratelimit import RateLimiter


@anbieter("finnhub")
class FinnhubProvider(PriceProvider):
    schluessel_env = "FINNHUB_API_KEY"
    kann_stream = True
    kann_historie = False            # Tageskerzen sind bei Finnhub kostenpflichtig
    REST = "https://finnhub.io/api/v1"
    WS = "wss://ws.finnhub.io"
    MAX_STREAM_SYMBOLE = 50

    def standard_limiter(self) -> RateLimiter:
        return RateLimiter(min_abstand=0.05, pro_minute=55)

    def unterstuetzt(self, symbol: str) -> bool:
        return markt(symbol) == "US"

    async def latest_price(self, symbol: str) -> Kurs:
        d = await self._get(f"{self.REST}/quote", params={"symbol": symbol},
                            headers={"X-Finnhub-Token": self.api_key})
        if not isinstance(d, dict) or not d.get("c"):
            raise AnbieterFehler(f"finnhub: kein Kurs für {symbol}")
        ts = datetime.fromtimestamp(d["t"], UTC) if d.get("t") else datetime.now(UTC)
        return Kurs(symbol, float(d["c"]), ts, self.name, 0)

    async def stream(self, symbols: list[str]) -> AsyncIterator[Kurs]:
        syms = [s for s in symbols if self.unterstuetzt(s)][: self.MAX_STREAM_SYMBOLE]
        async with self.ws_connect(f"{self.WS}?token={self.api_key}") as ws:
            for s in syms:
                await ws.send(json.dumps({"type": "subscribe", "symbol": s}))
            async for roh in ws:
                msg = json.loads(roh)
                if msg.get("type") == "error":
                    raise AnbieterFehler(f"finnhub: {msg.get('msg')}")
                if msg.get("type") != "trade":
                    continue                 # ping u. Ä.
                letzte: dict[str, dict] = {}
                for t in msg.get("data", []):
                    letzte[t["s"]] = t       # je Symbol nur der jüngste Trade der Nachricht
                for s, t in letzte.items():
                    yield Kurs(s, float(t["p"]), datetime.fromtimestamp(t["t"] / 1000, UTC), self.name, 0)
