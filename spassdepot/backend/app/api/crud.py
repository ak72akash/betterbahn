"""CRUD für Trades, Picks, Plan, Watchlist und Termine."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlmodel import Session, select

from app.api import schemas as sc
from app.api.zustand import Zustand, grenzen, sitzung, zustand
from app.data.base import AnbieterFehler
from app.journal import tabellen as t
from app.journal.berechnung import ist_offen, teile_fuer_teilverkauf, trade_ausgabe
from app.models.kennzahlen import p_target_before_stop, realized_vol
from app.reports.berichte import bewerte_picks
from app.rules.regeln import qualitaetsschwelle

router = APIRouter()


def hole(s: Session, modell, id_: int):
    obj = s.get(modell, id_)
    if obj is None:
        raise HTTPException(404, "Eintrag nicht gefunden.")
    return obj


def einfaches_crud(pfad: str, modell, neu, aendern, tag: str, sortierung=None, vor_speichern=None):
    """Erzeugt Liste/Anlegen/Lesen/Ändern/Löschen für eine Tabelle."""
    r = APIRouter(prefix=pfad, tags=[tag])

    @r.get("", response_model=list[modell])
    def liste(s: Session = Depends(sitzung)):
        q = select(modell)
        return list(s.exec(q.order_by(sortierung) if sortierung is not None else q))

    @r.post("", response_model=modell, status_code=201)
    def anlegen(daten: neu, s: Session = Depends(sitzung)):  # type: ignore[valid-type]
        obj = modell(**daten.model_dump())
        if vor_speichern:
            vor_speichern(s, obj)
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj

    @r.get("/{id_}", response_model=modell)
    def lesen(id_: int, s: Session = Depends(sitzung)):
        return hole(s, modell, id_)

    @r.patch("/{id_}", response_model=modell)
    def aendern_(id_: int, daten: aendern, s: Session = Depends(sitzung)):  # type: ignore[valid-type]
        obj = hole(s, modell, id_)
        for k, v in daten.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj

    @r.delete("/{id_}", status_code=204)
    def loeschen(id_: int, s: Session = Depends(sitzung)):
        s.delete(hole(s, modell, id_))
        s.commit()
        return Response(status_code=204)

    return r


def _symbol_gross(s: Session, obj) -> None:
    if getattr(obj, "symbol", None):
        obj.symbol = obj.symbol.strip().upper()


def _watchlist_eindeutig(s: Session, obj) -> None:
    _symbol_gross(s, obj)
    if s.exec(select(t.WatchlistEintrag).where(t.WatchlistEintrag.symbol == obj.symbol)).first():
        raise HTTPException(409, f"{obj.symbol} steht schon auf der Watchlist.")


router.include_router(einfaches_crud("/plan", t.PlanEintrag, t.PlanNeu, t.PlanAendern, "Plan",
                                     t.PlanEintrag.id.desc(), _symbol_gross))  # type: ignore[union-attr]
router.include_router(einfaches_crud("/watchlist", t.WatchlistEintrag, t.WatchlistBasis, t.WatchlistAendern,
                                     "Watchlist", t.WatchlistEintrag.name, _watchlist_eindeutig))
router.include_router(einfaches_crud("/events", t.Event, t.EventBasis, t.EventAendern, "Termine und Notizen",
                                     t.Event.datum, _symbol_gross))

# ---------- Trades ----------
trades = APIRouter(prefix="/trades", tags=["Journal"])


def _validiere(tr: t.Trade) -> None:
    try:
        t.TradeNeu.model_validate(tr.model_dump())
    except ValueError as e:
        meldungen = [f["msg"].removeprefix("Value error, ") for f in e.errors()] if hasattr(e, "errors") else [str(e)]
        raise HTTPException(422, " ".join(meldungen)) from e


@trades.get("", response_model=list[t.TradeAusgabe])
def trade_liste(status: str = Query("alle", pattern="^(alle|offen|geschlossen)$"), s: Session = Depends(sitzung)):
    alle = s.exec(select(t.Trade).order_by(t.Trade.datum_kauf.desc(), t.Trade.id.desc()))  # type: ignore[attr-defined,union-attr]
    return [trade_ausgabe(tr) for tr in alle
            if status == "alle" or (status == "offen") == ist_offen(tr)]


@trades.get("/export.csv", summary="CSV-Export (Semikolon, Dezimalkomma)")
def trade_export(s: Session = Depends(sitzung)):
    puffer = io.StringIO()
    spalten = list(t.TradeBasis.model_fields) + ["einsatz", "ergebnis_eur", "ergebnis_pct"]
    w = csv.writer(puffer, delimiter=";")
    w.writerow(spalten)
    fmt = lambda v: "" if v is None else (f"{v:.4f}".rstrip("0").rstrip(".").replace(".", ",") if isinstance(v, float) else str(v))
    for tr in s.exec(select(t.Trade).order_by(t.Trade.datum_kauf, t.Trade.id)):  # type: ignore[arg-type]
        a = trade_ausgabe(tr)
        w.writerow([fmt(a[c]) for c in spalten])
    return Response("﻿" + puffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="spassdepot-trades.csv"'})


@trades.post("", response_model=t.TradeAusgabe, status_code=201)
def trade_anlegen(daten: t.TradeNeu, s: Session = Depends(sitzung)):
    tr = t.Trade(**daten.model_dump())
    tr.symbol = tr.symbol.strip().upper()
    s.add(tr)
    s.commit()
    s.refresh(tr)
    return trade_ausgabe(tr)


@trades.get("/{id_}", response_model=t.TradeAusgabe)
def trade_lesen(id_: int, s: Session = Depends(sitzung)):
    return trade_ausgabe(hole(s, t.Trade, id_))


@trades.patch("/{id_}", response_model=t.TradeAusgabe)
def trade_aendern(id_: int, daten: t.TradeAendern, s: Session = Depends(sitzung)):
    tr = hole(s, t.Trade, id_)
    for k, v in daten.model_dump(exclude_unset=True).items():
        setattr(tr, k, v)
    tr.symbol = tr.symbol.strip().upper()
    _validiere(tr)
    s.add(tr)
    s.commit()
    s.refresh(tr)
    return trade_ausgabe(tr)


@trades.post("/{id_}/schliessen", response_model=t.TradeAusgabe)
def trade_schliessen(id_: int, daten: t.TradeSchliessen, s: Session = Depends(sitzung)):
    """Schließt einen Trade. Mit kleinerer Stückzahl als der Bestand wird ein Teilverkauf
    gebucht: der verkaufte Teil wird als eigener, geschlossener Trade abgespalten."""
    tr = hole(s, t.Trade, id_)
    if not ist_offen(tr):
        raise HTTPException(409, "Der Trade ist bereits geschlossen.")
    if daten.datum_verkauf < tr.datum_kauf:
        raise HTTPException(422, "Das Verkaufsdatum liegt vor dem Kaufdatum.")
    if daten.stueck is not None and daten.stueck > tr.stueck:
        raise HTTPException(422, "Es können nicht mehr Stücke verkauft werden als im Bestand.")
    if daten.stueck is not None and daten.stueck < tr.stueck:
        teil_daten, rest = teile_fuer_teilverkauf(tr, daten.stueck)
        ziel = t.Trade(**teil_daten)
        tr.gebuehren = (tr.gebuehren or 0.0) - teil_daten["gebuehren"]
        tr.stueck = rest
        s.add(tr)
    else:
        ziel = tr
    ziel.datum_verkauf, ziel.verkaufskurs = daten.datum_verkauf, daten.verkaufskurs
    ziel.gebuehren = (ziel.gebuehren or 0.0) + daten.gebuehren
    if daten.lehre:
        ziel.lehre = daten.lehre
    s.add(ziel)
    s.commit()
    s.refresh(ziel)
    return trade_ausgabe(ziel)


@trades.delete("/{id_}", status_code=204)
def trade_loeschen(id_: int, s: Session = Depends(sitzung)):
    s.delete(hole(s, t.Trade, id_))
    s.commit()
    return Response(status_code=204)


@router.post("/plan/{id_}/uebernehmen", response_model=t.TradeAusgabe, status_code=201, tags=["Plan"])
def plan_uebernehmen(id_: int, daten: t.TradeNeu, s: Session = Depends(sitzung)):
    """Legt aus einem Plan-Eintrag einen Trade an und setzt den Plan-Status auf "gekauft"."""
    plan = hole(s, t.PlanEintrag, id_)
    tr = t.Trade(**daten.model_dump())
    tr.symbol = tr.symbol.strip().upper()
    plan.status = "gekauft"
    s.add(tr)
    s.add(plan)
    s.commit()
    s.refresh(tr)
    return trade_ausgabe(tr)


# ---------- Picks ----------
picks = APIRouter(prefix="/picks", tags=["Picks"])




@picks.get("", response_model=list[t.Pick])
def pick_liste(s: Session = Depends(sitzung)):
    return list(s.exec(select(t.Pick).order_by(t.Pick.datum.desc(), t.Pick.id.desc())))  # type: ignore[attr-defined,union-attr]


@picks.post("", response_model=sc.PickPruefung)
async def pick_anlegen(daten: t.PickNeu, z: Zustand = Depends(zustand), s: Session = Depends(sitzung),
                       g: dict = Depends(grenzen)):
    """Prüft einen neuen Pick gegen die Qualitätsschwelle. Gespeichert wird nur, wenn er
    besteht – oder ausdrücklich mit ``trotzdem_speichern``."""
    symbol = daten.symbol.strip().upper()
    lang = daten.richtung == "long"
    if not ((daten.stop < daten.kurs < daten.ziel) if lang else (daten.ziel < daten.kurs < daten.stop)):
        raise HTTPException(422, "Ziel und Stop passen nicht zur Richtung (Long: Stop < Kurs < Ziel; Short umgekehrt).")
    if daten.sigma:
        sigma, quelle = daten.sigma, "Eingabe (Annahme)"
    else:
        try:
            df, hq = await z.kette.daily_history(symbol, 120)
            sigma = max(realized_vol(df, 20), realized_vol(df, 60) if len(df) >= 61 else 0.0)
            quelle = f"realisierte Volatilität, {hq}"
        except (AnbieterFehler, ValueError) as e:
            raise HTTPException(503, f"Volatilität nicht verfügbar – bitte sigma angeben. ({e})") from e
    ziel_pct, stop_pct = abs(daten.ziel / daten.kurs - 1), abs(daten.stop / daten.kurs - 1)
    sim = p_target_before_stop(daten.kurs, sigma, ziel_pct, stop_pct, daten.tage, n=20000 if daten.tage <= 10 else 8000,
                               seed=int(g["sim_seed"]), richtung=daten.richtung)
    regeln = qualitaetsschwelle(sim["p_ziel"], daten.kurs, daten.ziel, daten.stop, daten.richtung, g)
    ok = all(r.ok for r in regeln)
    pick = None
    if ok or daten.trotzdem_speichern:
        obj = t.Pick(**daten.model_dump(exclude={"tage", "sigma", "trotzdem_speichern", "symbol"}),
                     symbol=symbol, p_ziel_vor_stop=sim["p_ziel"])
        s.add(obj)
        s.commit()
        s.refresh(obj)
        pick = obj.model_dump(mode="json")
    return sc.PickPruefung(ok=ok, gespeichert=pick is not None, regeln=[r.dict() for r in regeln],
                           sigma=sigma, sigma_quelle=quelle, pick=pick, **sim)


@picks.post("/bewerten", summary="Ergebnisse nach 5 und 10 Handelstagen nachtragen")
async def pick_bewerten(z: Zustand = Depends(zustand), s: Session = Depends(sitzung)) -> dict[str, int]:
    return {"aktualisiert": await bewerte_picks(s, z.kette)}


@picks.patch("/{id_}", response_model=t.Pick)
def pick_aendern(id_: int, daten: t.PickAendern, s: Session = Depends(sitzung)):
    p = hole(s, t.Pick, id_)
    for k, v in daten.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    s.add(p)
    s.commit()
    s.refresh(p)
    return p


@picks.delete("/{id_}", status_code=204)
def pick_loeschen(id_: int, s: Session = Depends(sitzung)):
    s.delete(hole(s, t.Pick, id_))
    s.commit()
    return Response(status_code=204)


router.include_router(trades)
router.include_router(picks)
