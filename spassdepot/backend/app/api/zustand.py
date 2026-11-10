"""Gemeinsamer Anwendungszustand und FastAPI-Abhängigkeiten."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from fastapi import Depends, Request, WebSocket
from sqlmodel import Session

from app import db
from app.config import Konfig
from app.data.kette import AnbieterKette
from app.data.news import ManuellerNewsProvider, NewsProvider
from app.data.store import KursSpeicher
from app.journal.dienst import WarnDienst
from app.live import LiveDienst, Verteiler


@dataclass
class Zustand:
    cfg: Konfig
    engine: object
    kette: AnbieterKette
    store: KursSpeicher = field(default_factory=KursSpeicher)
    verteiler: Verteiler = field(default_factory=Verteiler)
    warnungen: WarnDienst = field(default_factory=WarnDienst)
    news: NewsProvider = field(default_factory=ManuellerNewsProvider)
    nicht_konfiguriert: list[dict] = field(default_factory=list)
    live: LiveDienst | None = None
    scheduler: object | None = None


def zustand(request: Request = None, websocket: WebSocket = None) -> Zustand:  # type: ignore[assignment]
    return (request or websocket).app.state.z


def sitzung(z: Zustand = Depends(zustand)) -> Iterator[Session]:
    with Session(z.engine) as s:
        yield s


def grenzen(s: Session = Depends(sitzung)) -> dict:
    return db.lade_grenzen(s)
