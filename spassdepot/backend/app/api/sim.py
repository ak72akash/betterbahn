"""Simulationen und Regelprüfungen. Die Rechenarbeit läuft im Threadpool (sync-Endpunkte)."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api import schemas as sc
from app.api.zustand import Zustand, grenzen, sitzung, zustand
from app.journal.dienst import branchen_belegung, depot_stand
from app.models.kennzahlen import black_scholes, p_target_before_stop, scalable_filter
from app.models.knockout import max_hebel, sichere_pfadzahl, simuliere_knockout
from app.rules.regeln import hebel_obergrenze, pruefe_position, risk_off_aktiv

router = APIRouter(tags=["Simulation und Regeln"])


@router.post("/sim/knockout", response_model=sc.KnockoutAusgabe)
def sim_knockout(e: sc.KnockoutEingabe, g: dict = Depends(grenzen)):
    """Knock-out-Simulation (Long/Short). Der übergebene Kurs ist eingefroren und wird
    in der Antwort als ``verwendeter_kurs`` zurückgegeben."""
    n = sichere_pfadzahl(e.tage, n=e.n or int(g["sim_pfade"]))
    seed = e.seed if e.seed is not None else int(g["sim_seed"])
    gap = float(g["earnings_gap_sd"]) if e.zahlen_ueber_nacht else 0.0
    t0 = time.perf_counter()
    erg = simuliere_knockout(e.kurs, e.sigma, e.hebel, tage=e.tage, einsatz=e.einsatz, spread=e.spread,
                             fin=e.fin, gap_sd=gap, n=n, seed=seed, richtung=e.richtung,
                             histogramm=e.histogramm)
    return sc.KnockoutAusgabe(
        **erg, max_hebel=max_hebel(e.sigma, e.zahlen_ueber_nacht, float(g["earnings_gap_sd"])),
        hebel_regel=hebel_obergrenze(e.hebel, e.sigma, e.zahlen_ueber_nacht, g).dict(),
        filter={**scalable_filter(e.kurs, e.hebel, e.richtung), "kurs": e.kurs, "symbol": e.symbol},
        verwendeter_kurs=e.kurs, gap_sd=gap, n=n, seed=seed, dauer_ms=(time.perf_counter() - t0) * 1000)


@router.post("/sim/target-stop", response_model=sc.ZielStopAusgabe)
def sim_ziel_stop(e: sc.ZielStopEingabe, g: dict = Depends(grenzen)):
    n = sichere_pfadzahl(e.tage, n=e.n or 20000, budget=5_200_000)
    seed = e.seed if e.seed is not None else int(g["sim_seed"])
    erg = p_target_before_stop(e.kurs, e.sigma, e.ziel_pct, e.stop_pct, e.tage, n=n, seed=seed, richtung=e.richtung)
    return sc.ZielStopAusgabe(**erg, crv=e.ziel_pct / e.stop_pct, n=n, seed=seed)


@router.post("/sim/warrant", response_model=sc.OptionsscheinAusgabe)
def sim_optionsschein(e: sc.OptionsscheinEingabe):
    try:
        return black_scholes(e.kurs, e.basispreis, e.tage, e.sigma, e.typ, e.zins,
                             e.bezugsverhaeltnis, e.preis, e.wechselkurs)
    except ValueError as f:
        raise HTTPException(422, str(f)) from f


@router.get("/filter", response_model=sc.FilterAusgabe)
async def filter_werte(symbol: str | None = None, hebel: float = Query(gt=1, le=100),
                       richtung: str = Query("long", pattern="^(long|short)$"),
                       kurs: float | None = Query(None, gt=0), z: Zustand = Depends(zustand)):
    """Fertige Suchwerte für den Broker. Ohne ``kurs`` wird der aktuelle Kurs des Symbols genommen."""
    if kurs is None:
        if not symbol:
            raise HTTPException(422, "Bitte symbol oder kurs angeben.")
        b = z.store.bester(symbol.upper())
        if b is None or b.schlusskurs:
            try:
                b = await z.kette.latest_price(symbol.upper())
            except Exception as f:
                raise HTTPException(503, str(f)) from f
        kurs = b.kurs
    return {**scalable_filter(kurs, hebel, richtung), "kurs": kurs, "symbol": symbol.upper() if symbol else None}


@router.post("/rules/check", response_model=sc.RegelCheckAusgabe)
def regel_check(e: sc.RegelCheckEingabe, z: Zustand = Depends(zustand), s: Session = Depends(sitzung),
                g: dict = Depends(grenzen)):
    """Prüft eine geplante Position gegen Größen-, Reserve- und Branchenregeln."""
    d = depot_stand(s, z.store, g)
    ro = not risk_off_aktiv(bool(g["risk_off"]), float(g["index_vortag_pct"]), g).ok
    regeln = pruefe_position(e.typ, e.einsatz, d["depotwert"], d["bargeld"], d["hebel_einsatz"],
                             branchen_belegung(s, e.symbol.upper()) if e.symbol else 0, ro, g)
    return sc.RegelCheckAusgabe(ok=all(r.ok for r in regeln), regeln=[r.dict() for r in regeln],
                                depotwert=d["depotwert"], bargeld=d["bargeld"], risk_off=ro)
