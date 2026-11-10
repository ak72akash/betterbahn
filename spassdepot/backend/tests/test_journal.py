"""Journal-Berechnungen, Positionsbewertung, Auswertung, Berichte."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.journal.berechnung import (
    auswertung,
    bewerte_position,
    depot,
    einsatz,
    ergebnis_eur,
    ergebnis_pct,
    kalibrierung,
    regelverstoesse,
    schein_wert,
)
from app.journal.dienst import filtere_neue_signale
from app.journal.tabellen import Trade, TradeNeu
from app.reports.berichte import pick_ergebnis
from tests.conftest import trade_daten, verlauf

HEUTE = date(2026, 11, 10)


def tr(id_=1, **kw):
    d = {"datum_kauf": date(2026, 11, 3), "wertpapier": "Turbo", "typ": "ko_long", "symbol": "IFX.DE",
         "stueck": 200, "kaufkurs": 0.5, "ko_schwelle": 35.0, "bezugsverhaeltnis": 0.1, "these": "x"}
    d.update(kw)
    return Trade(id=id_, **d)


def test_einsatz_und_ergebnis():
    t = tr(verkaufskurs=0.8, datum_verkauf=date(2026, 11, 6), gebuehren=1.98)
    assert einsatz(t) == 100
    assert ergebnis_eur(t) == pytest.approx(58.02)
    assert ergebnis_pct(t) == pytest.approx(58.02)
    assert ergebnis_eur(tr()) is None and ergebnis_pct(tr()) is None
    ko = tr(verkaufskurs=0.0, datum_verkauf=date(2026, 11, 6))
    assert ergebnis_pct(ko) == -100


def test_schein_wert():
    assert schein_wert("ko_long", 40, 35, 0.1) == pytest.approx(0.5)
    assert schein_wert("ko_short", 40, 45, 0.1) == pytest.approx(0.5)
    assert schein_wert("ko_long", 200, 180, 0.1, eurusd=1.25, in_usd=True) == pytest.approx(1.6)
    assert schein_wert("ko_long", 34, 35, 0.1) == 0                 # unter der Schwelle: wertlos
    with pytest.raises(ValueError):
        schein_wert("ko_long", 200, 180, 0.1, eurusd=None, in_usd=True)


def test_bewerte_knockout():
    p = bewerte_position(tr(), 42.0, None, HEUTE)
    assert p["wert"] == pytest.approx(140) and p["perf_pct"] == pytest.approx(40)
    assert p["ko_abstand_pct"] == pytest.approx(16.667, abs=0.01)
    assert p["geschaetzt"] and "Schätzung" in p["hinweis"] and p["ampel"] == "gruen" and p["handelstage"] == 5
    p = bewerte_position(tr(), 45.0, None, HEUTE)                   # +100 %
    assert [s["regel"] for s in p["signale"]] == ["ko_verdopplung"] and p["ampel"] == "gelb"
    p = bewerte_position(tr(), 36.0, None, HEUTE)                   # −80 %, Abstand 2,8 %
    assert {s["regel"] for s in p["signale"]} == {"ko_verlust", "ko_abstand"} and p["ampel"] == "rot"
    p = bewerte_position(tr(datum_kauf=date(2026, 10, 20)), 41.0, None, HEUTE)
    assert "ko_zeitstop" in {s["regel"] for s in p["signale"]}


def test_bewerte_us_und_short_und_aktie():
    us = tr(symbol="NVDA", ko_schwelle=180.0, kaufkurs=1.6)
    p = bewerte_position(us, 200.0, 1.25, HEUTE)
    assert p["wert_je_stueck"] == pytest.approx(1.6) and "EUR/USD" in p["hinweis"]
    assert bewerte_position(us, 200.0, None, HEUTE)["hinweis"] == "EUR/USD-Kurs fehlt"
    short = tr(typ="ko_short", ko_schwelle=45.0)
    p = bewerte_position(short, 42.0, None, HEUTE)
    assert p["wert_je_stueck"] == pytest.approx(0.3) and p["ko_abstand_pct"] == pytest.approx(7.14, abs=0.01)
    aktie = tr(typ="aktie", stueck=5, kaufkurs=40.0, ko_schwelle=None, bezugsverhaeltnis=None, ziel=44.0, stop=38.0)
    p = bewerte_position(aktie, 44.5, None, HEUTE)
    assert p["wert"] == pytest.approx(222.5) and not p["geschaetzt"]
    assert [s["regel"] for s in p["signale"]] == ["aktie_ziel"]
    assert [s["regel"] for s in bewerte_position(aktie, 37.9, None, HEUTE)["signale"]] == ["aktie_stop"]
    ohne = bewerte_position(aktie, None, None, HEUTE)
    assert ohne["wert"] is None and ohne["ampel"] == "grau"


def test_depot():
    zu = tr(1, verkaufskurs=0.8, datum_verkauf=date(2026, 11, 6), gebuehren=2.0)     # +58 €
    offen_ko = tr(2)                                                                  # 100 € Einsatz
    offen_aktie = tr(3, typ="aktie", stueck=5, kaufkurs=40.0, ko_schwelle=None, bezugsverhaeltnis=None)
    d = depot([zu, offen_ko, offen_aktie], {2: 140.0, 3: None})
    assert d["bargeld"] == pytest.approx(1000 + 58 - 300)
    assert d["depotwert"] == pytest.approx(758 + 140 + 200)        # ohne Kurs zählt der Einsatz
    assert d["hebel_einsatz"] == 100 and d["offene_positionen"] == 2
    assert d["veraenderung_pct"] == pytest.approx(9.8)
    assert depot([], {})["depotwert"] == 1000


def test_auswertung_und_kalibrierung():
    zu = lambda i, vk, p, tag: tr(i, verkaufskurs=vk, datum_verkauf=date(2026, 11, tag), prognose_p_gewinn=p)
    trades = [zu(1, 1.0, 0.45, 4), zu(2, 0.25, 0.45, 5), zu(3, 0.0, 0.15, 5), zu(4, 0.75, 0.30, 6), tr(5)]
    a = auswertung(trades, heute=HEUTE)
    assert a["anzahl_geschlossen"] == 4 and a["anzahl_offen"] == 1
    assert a["trefferquote"] == 0.5
    assert a["gewinnfaktor"] == pytest.approx(150 / 150)
    assert a["ergebnis_gesamt"] == pytest.approx(0)
    assert [p["depotwert"] for p in a["depotverlauf"]] == [1000, 1100, 950, 1000]
    k = {g["gruppe"]: g for g in kalibrierung(trades)}
    assert k["< 20 %"]["anzahl"] == 1 and k["< 20 %"]["trefferquote"] == 0
    assert k["20–40 %"]["trefferquote"] == 1
    assert k["> 40 %"]["anzahl"] == 2 and k["> 40 %"]["trefferquote"] == 0.5
    assert k["> 40 %"]["prognose_mittel"] == pytest.approx(0.45)
    leer = auswertung([])
    assert leer["trefferquote"] is None and leer["gewinnfaktor"] is None and leer["depotverlauf"] == []


def test_regelverstoesse():
    v = regelverstoesse([
        tr(1, stueck=300),                                                    # 150 € Einsatz
        tr(2, these=None),
        tr(3, datum_kauf=date(2026, 10, 12), datum_verkauf=date(2026, 11, 6), verkaufskurs=0.5),
        tr(4, verkaufskurs=0.0, datum_verkauf=date(2026, 11, 6)),
        tr(5),
    ], heute=HEUTE)
    assert [(x["trade_id"], x["regel"]) for x in v] == [
        (1, "positionsgroesse"), (2, "these"), (3, "ko_zeitstop"), (4, "ko_verlust")]


def test_entprellung_einmal_pro_tag():
    aus: set = set()
    sig = [{"regel": "ko_abstand"}, {"regel": "ko_verlust"}]
    assert len(filtere_neue_signale(sig, 1, HEUTE, aus)) == 2
    assert filtere_neue_signale(sig, 1, HEUTE, aus) == []                    # gleicher Tag: nichts
    assert len(filtere_neue_signale(sig, 2, HEUTE, aus)) == 2                # andere Position
    assert len(filtere_neue_signale(sig, 1, date(2026, 11, 11), aus)) == 2   # nächster Tag wieder


def test_pflichtfelder():
    TradeNeu.model_validate(trade_daten())
    for fehler in ({"ko_schwelle": None}, {"bezugsverhaeltnis": None}, {"stueck": 0}, {"wertpapier": ""},
                   {"verkaufskurs": 1.0}, {"typ": "zertifikat"}):
        with pytest.raises(ValueError):
            TradeNeu.model_validate(trade_daten(**fehler))
    TradeNeu.model_validate(trade_daten(typ="aktie", ko_schwelle=None, bezugsverhaeltnis=None))


def test_pick_ergebnis():
    df = verlauf(30, ende=110.0)
    start = df["datum"].iloc[-11]
    k5, k10 = float(df["close"].iloc[-6]), float(df["close"].iloc[-1])
    assert pick_ergebnis(start, 100.0, "long", df, 5) == pytest.approx((k5 / 100 - 1) * 100)
    assert pick_ergebnis(start, 100.0, "long", df, 10) == pytest.approx((k10 / 100 - 1) * 100)
    assert pick_ergebnis(start, 100.0, "short", df, 10) == pytest.approx(-(k10 / 100 - 1) * 100)
    assert pick_ergebnis(df["datum"].iloc[-3], 100.0, "long", df, 5) is None       # noch nicht abgelaufen
    _ = SimpleNamespace
