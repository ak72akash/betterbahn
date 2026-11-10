"""Geplante Aufgaben (APScheduler, Zeitzone Europe/Berlin, werktags).

Die Aufgaben halten das Tageslimit von Alpha Vantage ein: Kurse kommen aus dem
Kursspeicher (Live-Dienst), Verläufe zuerst aus dem Cache, dann von den
Live-Anbietern und erst zuletzt von Alpha Vantage."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session

from app import db
from app.reports import berichte

log = logging.getLogger("spassdepot.jobs")
ZEITPLAN = [
    ("morgenbericht", "mon-fri", 7, 45),
    ("positionen_mittag", "mon-fri", 13, 25),
    ("positionen_abend", "mon-fri", 22, 25),
    ("wochenbilanz", "fri", 19, 15),
]


async def index_vortag(z) -> float | None:
    """Veränderung des Index am Vortag in % – Grundlage für automatisches Risk-off."""
    with Session(z.engine) as s:
        g = db.lade_grenzen(s)
    try:
        df, _ = await z.kette.daily_history(str(g["index_symbol"]), 60)
        wert = float((df["close"].iloc[-1] / df["close"].iloc[-2] - 1) * 100)
    except Exception as e:
        log.warning("Index-Veränderung nicht verfügbar: %s", e)
        return None
    with Session(z.engine) as s:
        db.speichere_grenzen(s, {"index_vortag_pct": round(wert, 2)})
    return wert


async def job_morgenbericht(z) -> dict:
    await index_vortag(z)
    with Session(z.engine) as s:
        b = berichte.morgenbericht(s, z.store, db.lade_grenzen(s))
        berichte.speichere(s, "morgen", b)
    return b


async def job_positionen(z) -> dict:
    with Session(z.engine) as s:
        b = berichte.positions_check(s, z.store, db.lade_grenzen(s))
        berichte.speichere(s, "positionen", b)
    return b


async def job_wochenbilanz(z) -> dict:
    with Session(z.engine) as s:
        await berichte.bewerte_picks(s, z.kette)
        b = berichte.wochenbilanz(s, z.store, db.lade_grenzen(s))
        berichte.speichere(s, "woche", b)
    return b


def erstelle_scheduler(z) -> AsyncIOScheduler:
    sch = AsyncIOScheduler(timezone="Europe/Berlin")
    funktionen = {"morgenbericht": job_morgenbericht, "positionen_mittag": job_positionen,
                  "positionen_abend": job_positionen, "wochenbilanz": job_wochenbilanz}
    for name, tage, stunde, minute in ZEITPLAN:
        sch.add_job(funktionen[name], CronTrigger(day_of_week=tage, hour=stunde, minute=minute,
                                                  timezone="Europe/Berlin"),
                    args=[z], id=name, misfire_grace_time=600, coalesce=True)
    return sch
