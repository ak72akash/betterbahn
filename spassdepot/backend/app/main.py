"""FastAPI-Anwendung "Spaßdepot". Start: ``uvicorn app.main:app``.

Die App führt keine Orders aus und verbindet sich nicht mit dem Broker."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app import db
from app.api import auswertung, crud, kurse, sim
from app.api import auth as auth_api
from app.api.zustand import Zustand
from app.config import Konfig, konfig
from app.data.kette import AnbieterKette, baue_kette
from app.journal.dienst import abo_symbole, alert_dict, offene_trades
from app.live import LiveDienst

log = logging.getLogger("spassdepot")


def _symbole(z: Zustand) -> list[str]:
    with Session(z.engine) as s:
        return abo_symbole(s)


def _positions_symbole(z: Zustand) -> list[str]:
    with Session(z.engine) as s:
        return sorted({tr.symbol for tr in offene_trades(s)})


def _bei_update(z: Zustand, symbol: str) -> list[dict]:
    """Bei jedem Kurs-Update: Ausstiegsregeln der betroffenen offenen Positionen prüfen.
    Ein EUR/USD-Update betrifft alle Positionen auf US-Werte."""
    with Session(z.engine) as s:
        g = db.lade_grenzen(s)
        return [alert_dict(a) for a in z.warnungen.pruefe(s, z.store, g, None if symbol == "EURUSD" else symbol)]


def _nachricht(z: Zustand, symbol: str) -> dict | None:
    with Session(z.engine) as s:
        g = db.lade_grenzen(s)
    return z.store.nachricht(symbol, None, float(g["kurs_abweichung_pct"]), float(g["veraltet_nach_sek"]))


def create_app(cfg: Konfig | None = None, kette: AnbieterKette | None = None) -> FastAPI:
    cfg = cfg or konfig()
    engine = db.erstelle_engine(cfg.database_url)
    db.initialisiere(engine)
    fehlend: list[dict] = []
    if kette is None:
        def limiter(p):                       # Tageszähler übersteht Neustarts
            if p.limiter.pro_tag is not None:
                p.limiter._laden = db.zaehler_laden(engine, p.name)
                p.limiter._speichern = db.zaehler_speichern(engine, p.name)
        kette, fehlend = baue_kette(cfg, limiter, verlauf_lesen=partial(db.verlauf_lesen, engine),
                                    verlauf_schreiben=partial(db.verlauf_schreiben, engine))
    if kette._verlauf_lesen is None:          # übergebene Kette: Verlaufs-Cache nachrüsten
        kette._verlauf_lesen = partial(db.verlauf_lesen, engine)
        kette._verlauf_schreiben = partial(db.verlauf_schreiben, engine)
    z = Zustand(cfg=cfg, engine=engine, kette=kette, nicht_konfiguriert=fehlend)
    for k in db.lese_kurse(engine):           # letzter bekannter Stand aus price_cache
        z.store.aktualisiere(k)

    @asynccontextmanager
    async def lebenszyklus(app: FastAPI):
        if cfg.live_aktiv:
            z.live = LiveDienst(kette, z.store, z.verteiler, symbole=partial(_symbole, z),
                                bei_update=partial(_bei_update, z),
                                cache_schreiben=partial(db.schreibe_kurse, engine),
                                positions_symbole=partial(_positions_symbole, z),
                                nachricht=partial(_nachricht, z))
            await z.live.start()
        if cfg.jobs_aktiv:
            from app.jobs import erstelle_scheduler
            z.scheduler = erstelle_scheduler(z)
            z.scheduler.start()
        log.info("Spaßdepot gestartet. Anbieter: %s", [p.name for p in kette.anbieter])
        yield
        if z.scheduler:
            z.scheduler.shutdown(wait=False)
        if z.live:
            await z.live.stop()
        await kette.schliessen()

    app = FastAPI(
        title="Spaßdepot", version="0.1.0", lifespan=lebenszyklus,
        description="Analyse- und Journal-Tool für kurzfristige Aktien- und Knock-out-Trades. "
                    "Führt keine Orders aus. Keine Anlageberatung. Modellwerte sind keine Prognosen.",
        docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.z = z
    app.middleware("http")(auth_api.auth_middleware)
    app.add_middleware(CORSMiddleware, allow_origins=cfg.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/health", tags=["System"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for r in (auth_api.router, kurse.router, sim.router, crud.router, auswertung.router):
        app.include_router(r, prefix="/api")
    return app


def __getattr__(name: str):                  # `uvicorn app.main:app` ohne Import-Nebenwirkung in Tests
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
