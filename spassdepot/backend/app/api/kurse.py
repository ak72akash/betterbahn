"""Kurse, Volatilität, Live-WebSocket und SSE-Rückfall."""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlmodel import Session
from starlette.responses import StreamingResponse

from app import db
from app.api.auth import angemeldet
from app.api.schemas import AnbieterUebersicht, KursAusgabe, VolAusgabe
from app.api.zustand import Zustand, grenzen, sitzung, zustand
from app.data.base import AnbieterFehler, jetzt
from app.journal.dienst import abo_symbole, heute_berlin
from app.models.kennzahlen import realized_vol

router = APIRouter(tags=["Kurse"])


def _nachricht(z: Zustand, symbol: str, g: dict) -> dict | None:
    return z.store.nachricht(symbol, None, float(g["kurs_abweichung_pct"]), float(g["veraltet_nach_sek"]))


@router.get("/quote/{symbol}", response_model=KursAusgabe)
async def quote(symbol: str, z: Zustand = Depends(zustand), g: dict = Depends(grenzen)):
    """Aktueller Kurs mit Quelle, Zeitstempel und Etikett. Nutzt den Kursspeicher des
    Live-Dienstes; ist dort nichts Frisches, wird die Anbieter-Kette abgefragt."""
    symbol = symbol.upper()
    b = z.store.bester(symbol)
    if b is None or b.schlusskurs or (jetzt() - b.empfangen).total_seconds() > 20:
        try:
            z.store.aktualisiere(await z.kette.latest_price(symbol))
        except AnbieterFehler as e:
            if b is None:
                raise HTTPException(503, str(e)) from e
    return _nachricht(z, symbol, g)


@router.get("/quotes", response_model=list[KursAusgabe])
def quotes(z: Zustand = Depends(zustand), g: dict = Depends(grenzen)):
    """Alle Kurse aus dem Kursspeicher (Startzustand für die Oberfläche)."""
    return [n for s in z.store.symbole() if (n := _nachricht(z, s, g))]


@router.get("/vol/{symbol}", response_model=VolAusgabe)
async def vol(symbol: str, z: Zustand = Depends(zustand), s: Session = Depends(sitzung)):
    """Realisierte Volatilität (20 und 60 Handelstage) aus Tagesschlusskursen."""
    symbol = symbol.upper()
    try:
        df, quelle = await z.kette.daily_history(symbol, 120)
        v20 = realized_vol(df, 20)
    except (AnbieterFehler, ValueError) as e:
        raise HTTPException(503, str(e)) from e
    v60 = realized_vol(df, 60) if len(df) >= 61 else None
    heute = heute_berlin()
    return VolAusgabe(symbol=symbol, vol20=v20, vol60=v60, sigma_vorschlag=max(v20, v60 or 0.0),
                      letzter_schluss=float(df["close"].iloc[-1]), stand=df["datum"].iloc[-1],
                      quelle=quelle, tage=len(df),
                      naechste_quartalszahlen=z.news.naechste_quartalszahlen(s, symbol, heute, heute + timedelta(days=30)))


@router.get("/providers", response_model=AnbieterUebersicht)
def providers(z: Zustand = Depends(zustand), s: Session = Depends(sitzung)):
    return AnbieterUebersicht(reihenfolge=z.cfg.provider_order, aktiv=z.kette.status(),
                              nicht_konfiguriert=z.nicht_konfiguriert,
                              live_dienst=bool(z.live and z.live.laeuft), symbole=abo_symbole(s))


def _start_nachrichten(z: Zustand) -> list[dict]:
    with Session(z.engine) as s:
        g = db.lade_grenzen(s)
    return [{"typ": "kurs", "daten": n} for sym in z.store.symbole() if (n := _nachricht(z, sym, g))]


@router.websocket("/ws/prices")
async def ws_prices(ws: WebSocket):
    z: Zustand = ws.app.state.z
    if not angemeldet(z.cfg, ws.cookies):
        await ws.close(code=4401)
        return
    await ws.accept()
    q = z.verteiler.abonniere()
    try:
        for n in _start_nachrichten(z):
            await ws.send_json(n)
        while True:
            try:
                await ws.send_json(await asyncio.wait_for(q.get(), timeout=20))
            except TimeoutError:
                await ws.send_json({"typ": "ping"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        z.verteiler.kuendige(q)


@router.get("/sse/prices", summary="Rückfall für Umgebungen ohne WebSocket (Server-Sent Events)")
async def sse_prices(z: Zustand = Depends(zustand)):
    async def strom():
        q = z.verteiler.abonniere()
        try:
            for n in _start_nachrichten(z):
                yield f"data: {json.dumps(n)}\n\n"
            while True:
                try:
                    yield f"data: {json.dumps(await asyncio.wait_for(q.get(), timeout=20))}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            z.verteiler.kuendige(q)
    return StreamingResponse(strom(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
