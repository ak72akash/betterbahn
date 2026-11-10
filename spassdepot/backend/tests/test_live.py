"""Live-Dienst: Verarbeitung, Verteilung, Abfrage-Runden, Stream mit Wiederaufbau, Warnungen."""
import asyncio
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app import db
from app.data.base import AnbieterFehler, Kurs
from app.data.kette import AnbieterKette
from app.data.store import KursSpeicher
from app.journal import tabellen as t
from app.journal.dienst import WarnDienst, abo_symbole
from app.live import LiveDienst, Verteiler, wartezeit
from tests.conftest import MO_MITTAG, FakeAnbieter, trade_daten


def test_wartezeit_waechst():
    assert [wartezeit(n) for n in range(8)] == [1, 2, 4, 8, 16, 32, 60, 60]


def dienst(anbieter, symbole=("NVDA",), **kw):
    store, vert = KursSpeicher(), Verteiler()
    return LiveDienst(AnbieterKette(list(anbieter)), store, vert, symbole=lambda: list(symbole), **kw), store, vert


async def test_verarbeiten_verteilen_und_cache():
    geschrieben, alarme = [], []
    d, store, vert = dienst([FakeAnbieter("a", {"NVDA": 200.0})], cache_schreiben=geschrieben.extend,
                            bei_update=lambda s: alarme.append(s) or [{"text": "Warnung"}])
    q = vert.abonniere()
    for preis in (200.0, 200.5, 201.0):                         # drei Updates in einem Takt
        d.verarbeite(Kurs("NVDA", preis, datetime.now(UTC), "a"))
    d.verteile()
    nachrichten = [q.get_nowait() for _ in range(q.qsize())]
    assert [n["typ"] for n in nachrichten] == ["kurs", "alert"]  # gebündelt: ein Update je Symbol und Takt
    assert nachrichten[0]["daten"]["kurs"] == 201.0 and alarme == ["NVDA"]
    d.verteile()
    assert q.empty()                                             # nichts geändert, nichts gesendet
    d.cache_leeren()
    assert [(k.symbol, k.kurs) for k in geschrieben] == [("NVDA", 201.0)]


async def test_abfrage_runde_nur_wenn_faellig():
    a = FakeAnbieter("a", {"NVDA": 200.0, "EURUSD": 1.25})
    d, store, _ = dienst([a], symbole=("NVDA", "EURUSD"))
    assert await d.poll_runde() == 2
    assert await d.poll_runde() == 0 and a.aufrufe == 2          # frisch: keine neue Abfrage
    alt = datetime.now(UTC) - timedelta(seconds=400)
    store.aktualisiere(Kurs("NVDA", 200.0, alt, "a", empfangen=alt))
    store._kurse["NVDA"] = {"a": Kurs("NVDA", 200.0, alt, "a", empfangen=alt)}
    assert d.faellig("NVDA")
    # Markt geschlossen: längeres Intervall
    jung = MO_MITTAG - timedelta(seconds=120)
    store._kurse["NVDA"] = {"a": Kurs("NVDA", 200.0, jung, "a", empfangen=jung)}
    assert not d.faellig("NVDA", MO_MITTAG)                      # USA zu: 120 s sind in Ordnung
    store._kurse["IFX.DE"] = {"a": Kurs("IFX.DE", 40.0, jung, "a", empfangen=jung)}
    assert d.faellig("IFX.DE", MO_MITTAG)                        # Xetra offen: fällig


async def test_abfrage_runde_wechselt_anbieter():
    a, b = FakeAnbieter("a", kaputt=True), FakeAnbieter("b", {"NVDA": 200.0})
    d, store, _ = dienst([a, b])
    await d.poll_runde()
    assert store.bester("NVDA").quelle == "b"


async def test_vergleichsquelle_bleibt_zweite_wahl():
    a, b = FakeAnbieter("a", {"NVDA": 200.0}), FakeAnbieter("b", {"NVDA": 210.0})
    d, store, _ = dienst([a, b], positions_symbole=lambda: ["NVDA"])
    await d.poll_runde()
    await d.vergleich_runde()
    assert store.bester("NVDA").quelle == "a"
    assert [k.quelle for k in store.abweichungen("NVDA", 3.0)] == ["b"]    # 5 % -> beide anzeigen


class StreamAnbieter(FakeAnbieter):
    kann_stream = True

    def __init__(self, *a, laeufe=(), **kw):
        super().__init__(*a, **kw)
        self.laeufe, self.abos = list(laeufe), []

    async def stream(self, symbols):
        self.abos.append(list(symbols))
        kurse, fehler = self.laeufe.pop(0) if self.laeufe else ([], None)
        for k in kurse:
            yield Kurs(symbols[0], k, datetime.now(UTC), self.name)
        if fehler:
            raise fehler
        await asyncio.sleep(3600)


async def test_stream_wiederaufbau_nach_abbruch(monkeypatch):
    monkeypatch.setattr("app.live.wartezeit", lambda versuch: 0.01)
    p = StreamAnbieter("s", laeufe=[([200.0], AnbieterFehler("Verbindung weg")), ([201.0], None)])
    d, store, _ = dienst([p])
    aufgabe = asyncio.create_task(d._stream_schleife(p, pruef_takt=0.02))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if len(p.abos) >= 2 and store.bester("NVDA") and store.bester("NVDA").kurs == 201.0:
            break
    aufgabe.cancel()
    await asyncio.gather(aufgabe, return_exceptions=True)
    assert len(p.abos) == 2 and store.bester("NVDA").kurs == 201.0
    assert p.status.letzter_fehler is None or "Stream" in p.status.letzter_fehler


async def test_stream_abonniert_neu_bei_symbolwechsel():
    symbole = ["NVDA"]
    p = StreamAnbieter("s")
    d = LiveDienst(AnbieterKette([p]), KursSpeicher(), Verteiler(), symbole=lambda: list(symbole))
    aufgabe = asyncio.create_task(d._stream_schleife(p, pruef_takt=0.01))
    await asyncio.sleep(0.03)
    symbole.append("AMD")
    await asyncio.sleep(0.05)
    aufgabe.cancel()
    await asyncio.gather(aufgabe, return_exceptions=True)
    assert p.abos == [["NVDA"], ["NVDA", "AMD"]]


async def test_start_und_stop():
    p = StreamAnbieter("s", {"NVDA": 200.0}, laeufe=[([200.0], None)])
    d, store, _ = dienst([p], takt=0.01, poll_takt=0.01)
    await d.start()
    await asyncio.sleep(0.05)
    assert d.laeuft and store.bester("NVDA") is not None
    await d.stop()
    assert not d.laeuft and d._aufgaben == []


def test_verteiler_verwirft_bei_langsamem_client():
    v = Verteiler()
    q = v.abonniere()
    for i in range(600):
        v.sende({"i": i})
    assert q.qsize() == 500 and q.get_nowait()["i"] == 100
    v.kuendige(q)
    v.sende({"i": 1})


# ---------- Warnungen mit Datenbank ----------
def test_warnungen_entprellt_ueber_neustart(tmp_path):
    engine = db.erstelle_engine(f"sqlite:///{tmp_path / 'w.db'}")
    db.initialisiere(engine)
    store = KursSpeicher()
    jetzt = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    with Session(engine) as s:
        s.add(t.Trade(**{**trade_daten(), "datum_kauf": jetzt.date() - timedelta(days=1)}))
        s.commit()
        g = db.lade_grenzen(s)
        store.aktualisiere(Kurs("IFX.DE", 36.0, jetzt, "a", empfangen=jetzt))   # −80 %, Abstand 2,8 %
        w = WarnDienst()
        neu = w.pruefe(s, store, g, "IFX.DE", jetzt)
        assert {a.regel for a in neu} == {"ko_verlust", "ko_abstand"}
        assert w.pruefe(s, store, g, "IFX.DE", jetzt + timedelta(minutes=5)) == []
        assert WarnDienst().pruefe(s, store, g, "IFX.DE", jetzt + timedelta(hours=1)) == []   # nach Neustart
        assert w.pruefe(s, store, g, "NVDA", jetzt) == []                        # anderes Symbol
        morgen = w.pruefe(s, store, g, "IFX.DE", jetzt + timedelta(days=1))
        assert {a.regel for a in morgen} == {"ko_verlust", "ko_abstand"}
        assert len(s.exec(select(t.Alert)).all()) == 4
        assert all(not a.gelesen and a.text for a in morgen)


def test_abo_symbole_und_erstbefuellung(tmp_path):
    engine = db.erstelle_engine(f"sqlite:///{tmp_path / 'a.db'}")
    db.initialisiere(engine)
    db.initialisiere(engine)                                    # zweiter Start: nichts doppelt
    with Session(engine) as s:
        namen = {w.name for w in s.exec(select(t.WatchlistEintrag))}
        assert namen == {"Infineon", "Siemens Energy", "Siemens", "Rheinmetall", "SAP", "Nvidia", "AMD",
                         "Tesla", "Palantir", "Micron", "Applied Materials"}
        s.add(t.PlanEintrag(woche="2026-KW46", position="Turbo Long Broadcom", symbol="AVGO"))
        s.add(t.PlanEintrag(woche="2026-KW46", position="alt", symbol="INTC", status="verworfen"))
        s.add(t.Trade(**{**trade_daten(symbol="META"), "datum_kauf": datetime(2026, 11, 9).date()}))
        s.commit()
        syms = abo_symbole(s)
        assert {"IFX.DE", "NVDA", "AVGO", "META", "EURUSD"} <= set(syms) and "INTC" not in syms


def test_kurs_cache_und_verlauf_cache(tmp_path):
    engine = db.erstelle_engine(f"sqlite:///{tmp_path / 'c.db'}")
    db.initialisiere(engine)
    jetzt = datetime(2026, 11, 10, 10, 0, tzinfo=UTC)
    db.schreibe_kurse(engine, [Kurs("NVDA", 200.0, jetzt, "finnhub", empfangen=jetzt)])
    db.schreibe_kurse(engine, [Kurs("NVDA", 201.0, jetzt, "finnhub", empfangen=jetzt)])
    gelesen = db.lese_kurse(engine)
    assert len(gelesen) == 1 and gelesen[0].kurs == 201.0 and gelesen[0].quelle == "finnhub"
    assert gelesen[0].empfangen == jetzt
    from tests.conftest import verlauf
    df = verlauf(120)
    assert db.verlauf_lesen(engine, "NVDA", 120) is None
    db.verlauf_schreiben(engine, "NVDA", "yfinance", df)
    treffer, quelle = db.verlauf_lesen(engine, "NVDA", 120)
    assert quelle == "yfinance (Cache)" and len(treffer) == 120 and treffer["datum"].iloc[-1] == df["datum"].iloc[-1]
    assert db.verlauf_lesen(engine, "NVDA", 120, now=datetime.now(UTC) + timedelta(days=1)) is None
    laden, speichern = db.zaehler_laden(engine, "alphavantage"), db.zaehler_speichern(engine, "alphavantage")
    speichern(jetzt.date(), 7)
    assert laden(jetzt.date()) == 7 and laden(jetzt.date() + timedelta(days=1)) == 0
