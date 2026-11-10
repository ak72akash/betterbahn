"""Anbieter (gemocktes HTTP und WebSocket), Ratenbegrenzung, Kette, Kursspeicher, Handelszeiten."""
from datetime import date, datetime, timedelta

import httpx
import pytest

from app.config import Konfig
from app.data.base import ANBIETER, AnbieterFehler, Kurs, NichtUnterstuetzt, lade_anbieter
from app.data.kette import AnbieterKette, KeinKurs, baue_kette, pause_nach_fehlern
from app.data.maerkte import ist_veraltet, kurs_etikett, kurs_status, markt, markt_offen
from app.data.providers.alphavantage import AlphaVantageProvider, av_symbol
from app.data.providers.finnhub import FinnhubProvider
from app.data.providers.twelvedata import TwelveDataProvider, td_symbol
from app.data.providers.yfinance import YFinanceProvider
from app.data.ratelimit import LimitErreicht, RateLimiter
from app.data.store import KursSpeicher
from tests.conftest import MO_ABEND, MO_MITTAG, SAMSTAG, FakeAnbieter, FakeWS

UTC = MO_MITTAG.tzinfo


def http(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def frei():
    return RateLimiter()


# ---------- Ratenbegrenzung ----------
class Uhr:
    def __init__(self):
        self.t, self.tag, self.geschlafen = 0.0, date(2026, 11, 9), []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.geschlafen.append(s)
        self.t += s


async def test_ratelimit_mindestabstand():
    u = Uhr()
    r = RateLimiter(min_abstand=1.1, clock=u.clock, sleep=u.sleep, heute=lambda: u.tag)
    await r.acquire()
    await r.acquire()
    await r.acquire()
    assert u.geschlafen == pytest.approx([1.1, 1.1])


async def test_ratelimit_minutenfenster():
    u = Uhr()
    r = RateLimiter(pro_minute=3, clock=u.clock, sleep=u.sleep, heute=lambda: u.tag)
    for _ in range(3):
        await r.acquire()
    with pytest.raises(LimitErreicht):
        await r.acquire()
    u.t += 61
    await r.acquire()


async def test_ratelimit_tageszaehler_und_speicher():
    u, gespeichert = Uhr(), {}
    r = RateLimiter(pro_tag=25, clock=u.clock, sleep=u.sleep, heute=lambda: u.tag,
                    laden=lambda tag: gespeichert.get(tag, 23), speichern=gespeichert.__setitem__)
    assert r.verbleibend_heute == 2                       # 23 aus dem Speicher (Neustart)
    await r.acquire()
    await r.acquire()
    assert gespeichert[u.tag] == 25 and r.verbleibend_heute == 0
    with pytest.raises(LimitErreicht):
        await r.acquire()
    u.tag = date(2026, 11, 10)                            # neuer Tag: Zähler beginnt neu
    gespeichert.clear()
    gespeichert[u.tag] = 0
    await r.acquire()
    assert r.heute_anzahl == 1


# ---------- Symbole und Handelszeiten ----------
def test_symbol_zuordnung():
    assert [markt(s) for s in ("NVDA", "IFX.DE", "EURUSD", "^GDAXI")] == ["US", "XETRA", "FX", "INDEX"]
    assert av_symbol("IFX.DE") == "IFX.DEX" and av_symbol("ENR.DE") == "ENR.DEX" and av_symbol("NVDA") == "NVDA"
    assert td_symbol("IFX.DE") == ("IFX", "XETR") and td_symbol("EURUSD") == ("EUR/USD", None)


def test_handelszeiten():
    assert markt_offen("XETRA", MO_MITTAG) and not markt_offen("US", MO_MITTAG)
    assert markt_offen("US", MO_ABEND) and markt_offen("XETRA", MO_ABEND)
    assert not markt_offen("XETRA", datetime(2026, 11, 9, 16, 31, tzinfo=UTC))    # 17:31
    assert markt_offen("GETTEX", datetime(2026, 11, 9, 20, 0, tzinfo=UTC))        # 21:00
    assert not markt_offen("US", datetime(2026, 11, 9, 21, 1, tzinfo=UTC))        # 22:01
    assert not markt_offen("XETRA", SAMSTAG) and not markt_offen("GETTEX", SAMSTAG)
    # Sommerzeit: 9:00 Berlin = 7:00 UTC
    assert markt_offen("XETRA", datetime(2026, 7, 6, 7, 0, tzinfo=UTC))


def test_etikett():
    k = lambda **kw: Kurs("IFX.DE", 40.0, MO_MITTAG, "x", **kw)
    assert kurs_etikett(k()) == "Echtzeit"
    assert kurs_etikett(k(verzoegerung_sek=900)) == "verzögert (15 Min)"
    assert kurs_etikett(k(verzoegerung_sek=86400, schlusskurs=True)) == "Schlusskurs"


def test_veraltet_kennzeichnung():
    frisch = Kurs("IFX.DE", 40.0, MO_MITTAG, "x", empfangen=MO_MITTAG - timedelta(seconds=30))
    alt = Kurs("IFX.DE", 40.0, MO_MITTAG, "x", empfangen=MO_MITTAG - timedelta(seconds=61))
    assert not ist_veraltet(frisch, MO_MITTAG)
    assert ist_veraltet(alt, MO_MITTAG)
    assert not ist_veraltet(alt, SAMSTAG)                           # Markt zu: nicht "veraltet"
    us = Kurs("NVDA", 200.0, MO_MITTAG, "x", empfangen=MO_MITTAG - timedelta(hours=2))
    assert not ist_veraltet(us, MO_MITTAG) and ist_veraltet(us, MO_ABEND)
    st = kurs_status(us, MO_MITTAG)
    assert st["hinweis"] == "Markt geschlossen" and st["markt_offen"] is False and st["gettex_offen"] is True
    assert kurs_status(alt, MO_MITTAG)["veraltet"] is True
    assert ist_veraltet(frisch, MO_MITTAG, nach_sek=10)


# ---------- Finnhub ----------
async def test_finnhub_quote():
    def h(req):
        assert req.url.path == "/api/v1/quote" and req.url.params["symbol"] == "NVDA"
        assert req.headers["X-Finnhub-Token"] == "k" and "k" not in str(req.url)
        return httpx.Response(200, json={"c": 201.5, "t": 1794200000})
    p = FinnhubProvider("k", client=http(h), limiter=frei())
    kurs, zeit, quelle, verz = await p.latest_price("NVDA")
    assert (kurs, quelle, verz) == (201.5, "finnhub", 0) and zeit.tzinfo is not None
    assert p.unterstuetzt("NVDA") and not p.unterstuetzt("IFX.DE") and not p.unterstuetzt("EURUSD")


async def test_finnhub_fehlerfaelle():
    p = FinnhubProvider("k", client=http(lambda r: httpx.Response(200, json={"c": 0, "t": 0})), limiter=frei())
    with pytest.raises(AnbieterFehler):
        await p.latest_price("XXXX")
    p = FinnhubProvider("k", client=http(lambda r: httpx.Response(429)), limiter=frei())
    with pytest.raises(AnbieterFehler):
        await p.latest_price("NVDA")


async def test_finnhub_stream():
    ws = FakeWS([{"type": "ping"},
                 {"type": "trade", "data": [{"s": "NVDA", "p": 200.0, "t": 1794200000000, "v": 5},
                                            {"s": "NVDA", "p": 200.2, "t": 1794200000500, "v": 1},
                                            {"s": "AMD", "p": 150.0, "t": 1794200000400, "v": 2}]}])
    urls = []
    p = FinnhubProvider("geheim", ws_connect=lambda url: urls.append(url) or ws)
    kurse = [k async for k in p.stream(["NVDA", "AMD", "IFX.DE"])]
    assert urls == ["wss://ws.finnhub.io?token=geheim"]
    assert ws.gesendet == [{"type": "subscribe", "symbol": "NVDA"}, {"type": "subscribe", "symbol": "AMD"}]
    assert [(k.symbol, k.kurs) for k in kurse] == [("NVDA", 200.2), ("AMD", 150.0)]
    assert all(k.quelle == "finnhub" and k.verzoegerung_sek == 0 for k in kurse)


async def test_finnhub_stream_fehlermeldung():
    p = FinnhubProvider("k", ws_connect=lambda url: FakeWS([{"type": "error", "msg": "Invalid API key"}]))
    with pytest.raises(AnbieterFehler):
        _ = [k async for k in p.stream(["NVDA"])]


# ---------- Twelve Data ----------
async def test_twelvedata_kurs_xetra():
    def h(req):
        assert req.url.path == "/price"
        assert req.url.params["symbol"] == "IFX" and req.url.params["exchange"] == "XETR"
        assert req.headers["Authorization"] == "apikey k"
        return httpx.Response(200, json={"price": "40.12"})
    p = TwelveDataProvider("k", client=http(h), limiter=frei())
    assert (await p.latest_price("IFX.DE")).kurs == 40.12


async def test_twelvedata_tarifgrenze_und_limit():
    p = TwelveDataProvider("k", limiter=frei(), client=http(lambda r: httpx.Response(200, json={
        "code": 404, "status": "error", "message": "symbol not available with your plan"})))
    with pytest.raises(NichtUnterstuetzt):
        await p.latest_price("IFX.DE")
    p = TwelveDataProvider("k", limiter=frei(), client=http(lambda r: httpx.Response(200, json={
        "code": 429, "status": "error", "message": "credits"})))
    with pytest.raises(AnbieterFehler) as e:
        await p.latest_price("NVDA")
    assert not isinstance(e.value, NichtUnterstuetzt)


async def test_twelvedata_verlauf():
    werte = [{"datetime": "2026-11-06", "open": "39", "high": "41", "low": "38", "close": "40", "volume": "100"},
             {"datetime": "2026-11-05", "open": "38", "high": "40", "low": "37", "close": "39", "volume": "90"}]
    p = TwelveDataProvider("k", limiter=frei(), client=http(lambda r: httpx.Response(200, json={"values": werte})))
    df = await p.daily_history("IFX.DE", 60)
    assert list(df["close"]) == [39.0, 40.0] and df["datum"].iloc[-1] == date(2026, 11, 6)


async def test_twelvedata_stream():
    ws = FakeWS([{"event": "subscribe-status", "status": "ok"},
                 {"event": "price", "symbol": "IFX", "exchange": "XETR", "price": 40.5, "timestamp": 1794200000},
                 {"event": "price", "symbol": "EUR/USD", "price": 1.16, "timestamp": 1794200001},
                 {"event": "heartbeat"}])
    p = TwelveDataProvider("k", ws_connect=lambda url: ws)
    kurse = [k async for k in p.stream(["IFX.DE", "EURUSD"])]
    assert ws.gesendet == [{"action": "subscribe", "params": {"symbols": "IFX:XETR,EUR/USD"}}]
    assert [(k.symbol, k.kurs) for k in kurse] == [("IFX.DE", 40.5), ("EURUSD", 1.16)]


# ---------- Yahoo ----------
def yahoo_antwort(preis=40.0, verz=15):
    return {"chart": {"result": [{
        "meta": {"regularMarketPrice": preis, "regularMarketTime": 1794200000, "exchangeDataDelayedBy": verz},
        "timestamp": [1793900000, 1793990000, 1794080000],
        "indicators": {"quote": [{"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3],
                                  "close": [38.0, None, 40.0], "volume": [1, 1, 1]}]}}], "error": None}}


async def test_yahoo_kurs_und_verlauf():
    pfade = []
    def h(req):
        pfade.append(req.url.path)
        return httpx.Response(200, json=yahoo_antwort())
    p = YFinanceProvider(client=http(h), limiter=frei())
    k = await p.latest_price("IFX.DE")
    assert (k.kurs, k.verzoegerung_sek, k.quelle) == (40.0, 900, "yfinance")
    assert kurs_etikett(k) == "verzögert (15 Min)"
    await p.latest_price("EURUSD")
    assert pfade[-1].endswith("/EURUSD=X")
    df = await p.daily_history("IFX.DE", 60)
    assert list(df["close"]) == [38.0, 40.0]              # Lücke entfernt


async def test_yahoo_unbekanntes_symbol():
    p = YFinanceProvider(limiter=frei(), client=http(lambda r: httpx.Response(
        404, json={"chart": {"result": None, "error": {"code": "Not Found"}}})))
    with pytest.raises(AnbieterFehler):
        await p.latest_price("XXXX")


# ---------- Alpha Vantage ----------
async def test_alphavantage_schlusskurs_und_verlauf():
    def h(req):
        assert req.url.params["symbol"] == "IFX.DEX"
        if req.url.params["function"] == "GLOBAL_QUOTE":
            return httpx.Response(200, json={"Global Quote": {"05. price": "39.50", "07. latest trading day": "2026-11-06"}})
        assert req.url.params["outputsize"] == "compact"
        return httpx.Response(200, json={"Time Series (Daily)": {
            "2026-11-06": {"1. open": "39", "2. high": "40", "3. low": "38", "4. close": "39.5", "5. volume": "10"},
            "2026-11-05": {"1. open": "38", "2. high": "39", "3. low": "37", "4. close": "38.5", "5. volume": "10"}}})
    p = AlphaVantageProvider("k", client=http(h), limiter=frei())
    k = await p.latest_price("IFX.DE")
    assert k.schlusskurs and kurs_etikett(k) == "Schlusskurs" and p.nur_schlusskurs
    df = await p.daily_history("IFX.DE", 60)
    assert list(df["close"]) == [38.5, 39.5]


async def test_alphavantage_limit_hinweis_und_tageslimit():
    p = AlphaVantageProvider("k", limiter=frei(), client=http(lambda r: httpx.Response(
        200, json={"Information": "Our standard API rate limit is 25 requests per day."})))
    with pytest.raises(LimitErreicht):
        await p.daily_history("IFX.DE", 60)
    u, aufrufe = Uhr(), []
    def h(req):
        aufrufe.append(1)
        return httpx.Response(200, json={"Global Quote": {"05. price": "1", "07. latest trading day": "2026-11-06"}})
    p = AlphaVantageProvider("k", client=http(h))
    p.limiter = RateLimiter(min_abstand=1.1, pro_tag=25, clock=u.clock, sleep=u.sleep, heute=lambda: u.tag)
    for _ in range(25):
        await p.latest_price("IFX.DE")
    with pytest.raises(LimitErreicht):
        await p.latest_price("IFX.DE")
    assert len(aufrufe) == 25                              # die 26. Abfrage geht nicht mehr raus
    assert min(u.geschlafen) >= 1.0                        # höchstens 1 Abfrage pro Sekunde


def test_standard_limits():
    assert (AlphaVantageProvider("k").limiter.pro_tag, AlphaVantageProvider("k").limiter.min_abstand) == (25, 1.1)
    assert TwelveDataProvider("k").limiter.pro_minute == 8 and TwelveDataProvider("k").limiter.pro_tag == 800


# ---------- Kette ----------
async def test_wechsel_auf_naechsten_anbieter():
    a = FakeAnbieter("a", kaputt=True)
    b = FakeAnbieter("b", {"NVDA": 200.0})
    kette = AnbieterKette([a, b])
    k = await kette.latest_price("NVDA")
    assert k.quelle == "b" and a.aufrufe == 1
    st = {s["name"]: s for s in kette.status()}
    assert st["a"]["verbunden"] is False and st["a"]["letzter_fehler"] and st["b"]["verbunden"] is True


async def test_reihenfolge_ist_prioritaet_und_symbolfilter():
    a = FakeAnbieter("a", {"NVDA": 1.0}, nur={"NVDA"})
    b = FakeAnbieter("b", {"NVDA": 2.0, "IFX.DE": 3.0})
    kette = AnbieterKette([a, b])
    assert (await kette.latest_price("NVDA")).quelle == "a"
    assert (await kette.latest_price("IFX.DE")).quelle == "b" and a.aufrufe == 1
    assert (await kette.latest_price("NVDA", ausser={"a"})).quelle == "b"


async def test_pause_nach_wiederholtem_ausfall():
    t = [0.0]
    a, b = FakeAnbieter("a", kaputt=True), FakeAnbieter("b", {"NVDA": 2.0})
    kette = AnbieterKette([a, b], clock=lambda: t[0])
    for _ in range(5):
        await kette.latest_price("NVDA")
    assert a.aufrufe == 3                                   # nach 3 Fehlern pausiert
    a.kaputt, a.kurse = False, {"NVDA": 1.0}
    t[0] = 31
    assert (await kette.latest_price("NVDA")).quelle == "a"  # nach der Pause wieder erste Wahl
    assert [pause_nach_fehlern(n) for n in (1, 2, 3, 4, 5, 20)] == [0, 0, 30, 60, 120, 600]


async def test_alle_ausgefallen():
    with pytest.raises(KeinKurs):
        await AnbieterKette([FakeAnbieter("a", kaputt=True)]).latest_price("NVDA")


async def test_schlusskurs_anbieter_nie_fuer_live_aber_fuer_verlauf():
    av = FakeAnbieter("alphavantage", {"IFX.DE": 39.0}, nur_schlusskurs=True)
    live = FakeAnbieter("live", {"IFX.DE": 40.0}, kann_historie=False)
    kette = AnbieterKette([av, live])
    assert (await kette.latest_price("IFX.DE")).quelle == "live" and av.aufrufe == 0
    df, quelle = await kette.daily_history("IFX.DE", 60)
    assert quelle == "alphavantage" and len(df) == 60
    # Live-Anbieter mit Verlauf kommt vor Alpha Vantage, auch wenn er später in der Reihenfolge steht
    live2 = FakeAnbieter("live2", {"IFX.DE": 40.0})
    assert (await AnbieterKette([av, live2]).daily_history("IFX.DE", 60))[1] == "live2"


async def test_verlauf_zuerst_cache():
    a = FakeAnbieter("a", {"IFX.DE": 40.0})
    speicher = {}
    kette = AnbieterKette([a], verlauf_lesen=lambda s, t: speicher.get(s),
                          verlauf_schreiben=lambda s, q, df: speicher.__setitem__(s, (df, f"{q} (Cache)")))
    assert (await kette.daily_history("IFX.DE", 60))[1] == "a"
    assert (await kette.daily_history("IFX.DE", 60))[1] == "a (Cache)"
    assert a.aufrufe == 1


async def test_tarifgrenze_sperrt_symbol_statt_anbieter():
    class Tarif(FakeAnbieter):
        async def latest_price(self, symbol):
            self.aufrufe += 1
            if symbol == "IFX.DE":
                raise NichtUnterstuetzt("nicht im Tarif")
            return await super().latest_price(symbol)
    a, b = Tarif("a", {"NVDA": 1.0}), FakeAnbieter("b", {"IFX.DE": 3.0})
    kette = AnbieterKette([a, b])
    await kette.latest_price("IFX.DE")
    await kette.latest_price("IFX.DE")
    assert a.aufrufe == 1                                   # nicht jede Runde neu versucht
    assert (await kette.latest_price("NVDA")).quelle == "a"  # Anbieter selbst bleibt nutzbar


def test_kette_aus_konfiguration(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setenv("TWELVEDATA_API_KEY", "k")
    kette, fehlend = baue_kette(Konfig(provider_order=["finnhub", "twelvedata", "yfinance", "gibtsnicht"]))
    assert [p.name for p in kette.anbieter] == ["twelvedata", "yfinance"]
    assert [f["name"] for f in fehlend] == ["finnhub", "gibtsnicht"]
    assert set(lade_anbieter()) >= {"finnhub", "twelvedata", "yfinance", "alphavantage", "demo"}
    assert ANBIETER["finnhub"] is FinnhubProvider


# ---------- Kursspeicher ----------
def test_speicher_bester_und_abweichung():
    st = KursSpeicher()
    t0 = MO_MITTAG
    st.aktualisiere(Kurs("IFX.DE", 39.0, t0, "alphavantage", 86400, True, t0))
    assert st.bester("IFX.DE").schlusskurs
    assert st.aktualisiere(Kurs("IFX.DE", 40.0, t0, "yfinance", 900, False, t0 - timedelta(seconds=5)))
    assert st.bester("IFX.DE").quelle == "yfinance"         # Live schlägt Schlusskurs
    st.aktualisiere(Kurs("IFX.DE", 40.5, t0, "twelvedata", 0, False, t0 - timedelta(seconds=10)))
    assert st.abweichungen("IFX.DE", 3.0, now=t0) == []     # 1,25 % Abweichung
    st.aktualisiere(Kurs("IFX.DE", 42.0, t0, "twelvedata", 0, False, t0 - timedelta(seconds=10)))
    ab = st.abweichungen("IFX.DE", 3.0, now=t0)
    assert [k.quelle for k in ab] == ["twelvedata"]         # 5 % -> beide anzeigen
    n = st.nachricht("IFX.DE", t0)
    assert n["quelle"] == "yfinance" and n["weitere_quellen"][0]["kurs"] == 42.0
    assert n["etikett"] == "verzögert (15 Min)" and n["kennzeichnung"] == "Fakt"
    assert st.abweichungen("IFX.DE", 3.0, now=t0 + timedelta(hours=1)) == []   # alte Vergleichskurse zählen nicht
    assert st.nachricht("XXX") is None
