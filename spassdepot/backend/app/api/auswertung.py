"""Positions-Check, Statistik, Berichte, Einstellungen und Warnungen."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlmodel import Session, select

from app import db, jobs
from app.api import schemas as sc
from app.api.zustand import Zustand, grenzen, sitzung, zustand
from app.journal import tabellen as t
from app.journal.berechnung import auswertung
from app.journal.dienst import alert_dict, heute_berlin
from app.reports import berichte
from app.rules.grenzen import BESCHREIBUNG, STANDARD

router = APIRouter()


@router.get("/positions/check", response_model=sc.PositionsCheck, tags=["Positionen"])
def positions_check(z: Zustand = Depends(zustand), s: Session = Depends(sitzung), g: dict = Depends(grenzen)):
    """Offene Positionen mit Live-Kurs, geschätztem Wert, Abständen, Signalen und Ampel."""
    return berichte.positions_check(s, z.store, g)


@router.get("/stats", response_model=sc.Statistik, tags=["Auswertung"])
def stats(s: Session = Depends(sitzung), g: dict = Depends(grenzen)):
    return auswertung(list(s.exec(select(t.Trade))), g, heute_berlin())


@router.get("/reports/morning", response_model=sc.Morgenbericht, tags=["Berichte"])
async def morgen(neu: bool = Query(False, description="Bericht jetzt neu erzeugen und speichern"),
                 z: Zustand = Depends(zustand), s: Session = Depends(sitzung)):
    """Letzter gespeicherter Morgenbericht (07:45). Gibt es noch keinen, wird er erzeugt."""
    b = None if neu else berichte.letzter(s, "morgen")
    if b is None:
        await jobs.job_morgenbericht(z)
        b = berichte.letzter(s, "morgen")
    return b


@router.get("/reports/positions", response_model=sc.PositionsCheck | None, tags=["Berichte"])
def positionen_bericht(s: Session = Depends(sitzung)):
    """Letzte gespeicherte Positions-Zusammenfassung (13:25 bzw. 22:25)."""
    return berichte.letzter(s, "positionen")


@router.get("/reports/week", response_model=sc.Wochenbilanz, tags=["Berichte"])
async def woche(neu: bool = False, z: Zustand = Depends(zustand), s: Session = Depends(sitzung)):
    """Letzte gespeicherte Wochenbilanz (Freitag 19:15). Gibt es noch keine, wird sie erzeugt."""
    b = None if neu else berichte.letzter(s, "woche")
    if b is None:
        await jobs.job_wochenbilanz(z)
        b = berichte.letzter(s, "woche")
    return b


def _einstellungen(g: dict) -> list[sc.Einstellung]:
    return [sc.Einstellung(schluessel=k, wert=g[k], vorgabe=v, beschreibung=BESCHREIBUNG.get(k, k))
            for k, v in STANDARD.items()]


@router.get("/settings", response_model=list[sc.Einstellung], tags=["Einstellungen"])
def einstellungen_lesen(g: dict = Depends(grenzen)):
    return _einstellungen(g)


@router.put("/settings", response_model=list[sc.Einstellung], tags=["Einstellungen"])
def einstellungen_schreiben(werte: dict[str, float | bool | str] = Body(..., examples=[{"risk_off": True}]),
                            s: Session = Depends(sitzung)):
    """Ändert einzelne Grenzwerte, z. B. ``{"max_ko_einsatz": 80, "risk_off": true}``."""
    try:
        return _einstellungen(db.speichere_grenzen(s, werte))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/alerts", response_model=list[sc.AlertAusgabe], tags=["Warnungen"])
def alerts(nur_ungelesen: bool = False, limit: int = Query(50, ge=1, le=500), s: Session = Depends(sitzung)):
    q = select(t.Alert).order_by(t.Alert.zeit.desc()).limit(limit)  # type: ignore[attr-defined]
    if nur_ungelesen:
        q = q.where(t.Alert.gelesen == False)  # noqa: E712
    return [alert_dict(a) for a in s.exec(q)]


@router.post("/alerts/{id_}/gelesen", response_model=sc.AlertAusgabe, tags=["Warnungen"])
def alert_gelesen(id_: int, s: Session = Depends(sitzung)):
    a = s.get(t.Alert, id_)
    if a is None:
        raise HTTPException(404, "Warnung nicht gefunden.")
    a.gelesen = True
    s.add(a)
    s.commit()
    s.refresh(a)
    return alert_dict(a)


@router.post("/alerts/gelesen", tags=["Warnungen"])
def alle_gelesen(s: Session = Depends(sitzung)) -> dict[str, int]:
    offen = list(s.exec(select(t.Alert).where(t.Alert.gelesen == False)))  # noqa: E712
    for a in offen:
        a.gelesen = True
        s.add(a)
    s.commit()
    return {"gelesen": len(offen)}
