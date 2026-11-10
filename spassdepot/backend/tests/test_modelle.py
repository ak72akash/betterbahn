import numpy as np
import pandas as pd
import pytest

from app.models.kennzahlen import black_scholes, p_target_before_stop, realized_vol, scalable_filter
from app.models.knockout import knockout, knockout_short, max_hebel, sichere_pfadzahl, simuliere_knockout


def test_knockout_referenzwert():
    r = knockout(100, 0.57, 10, tage=10)
    assert 0.30 <= r["p_ko"] <= 0.38
    assert r["ko_schwelle"] == 90.0
    assert r["p_verdopplung"] <= r["p_gewinn"] <= 1 - r["p_ko"]
    assert r["median"] <= r["top25"] <= r["top10"]


def test_max_hebel():
    assert max_hebel(0.57) == 9
    assert max_hebel(0.30) == 17
    assert max_hebel(0.60) == 8
    assert max_hebel(0.30, earnings_in_haltedauer=True) == 8      # 1 / (2 · 0,06)


def test_reproduzierbar_und_seed():
    a, b = knockout(50, 0.4, 8, n=5000), knockout(50, 0.4, 8, n=5000)
    assert a == b
    assert knockout(50, 0.4, 8, n=5000, seed=2) != a


def test_allgemeine_variante_gleich_referenz():
    ref = knockout(120, 0.45, 7, tage=5, gap_sd=0.06, n=6000)
    allg = simuliere_knockout(120, 0.45, 7, tage=5, gap_sd=0.06, n=6000, richtung="long")
    assert all(allg[k] == ref[k] for k in ref)


def test_short_variante():
    r = knockout_short(100, 0.57, 10, n=20000)
    assert r["ko_schwelle"] == 110.0
    assert 0.28 <= r["p_ko"] <= 0.42
    # höherer Hebel = näher an der Schwelle = häufiger KO
    assert knockout_short(100, 0.57, 20, n=20000)["p_ko"] > r["p_ko"]


def test_gap_erhoeht_ko():
    assert knockout(100, 0.4, 10, gap_sd=0.06, n=20000)["p_ko"] > knockout(100, 0.4, 10, n=20000)["p_ko"]


def test_histogramm_summiert_auf_eins():
    r = simuliere_knockout(100, 0.5, 8, n=8000, histogramm=True, bins=20)
    h = r["histogramm"]
    assert len(h) == 21 and h[0]["ko"] is True
    assert h[0]["anteil"] == pytest.approx(r["p_ko"])
    assert sum(b["anteil"] for b in h) == pytest.approx(1.0)


def test_ungueltige_eingaben():
    with pytest.raises(ValueError):
        simuliere_knockout(100, 0.5, 1)
    with pytest.raises(ValueError):
        simuliere_knockout(100, 0.5, 5, richtung="seitwaerts")


def test_sichere_pfadzahl():
    assert sichere_pfadzahl(10) == 40000
    assert sichere_pfadzahl(40) == 10000
    assert sichere_pfadzahl(10, n=5000) == 5000


def test_realized_vol():
    rng = np.random.default_rng(0)
    kurse = 100 * np.exp(np.cumsum(rng.normal(0, 0.3 / np.sqrt(252), 400)))
    df = pd.DataFrame({"close": kurse})
    assert realized_vol(df, 60) == pytest.approx(0.30, abs=0.08)
    assert realized_vol(df, 20) > 0
    konstant = pd.DataFrame({"close": [100.0] * 30})
    assert realized_vol(konstant, 20) == 0
    with pytest.raises(ValueError):
        realized_vol(df.iloc[:10], 20)


def test_p_target_before_stop():
    r = p_target_before_stop(100, 0.5, 0.08, 0.04, 10, n=8000)
    assert r["p_ziel"] + r["p_stop"] + r["p_offen"] == pytest.approx(1.0)
    assert r["p_stop"] > r["p_ziel"]                    # Stop liegt näher
    sym = p_target_before_stop(100, 0.5, 0.05, 0.05, 10, n=8000)
    assert sym["p_ziel"] == pytest.approx(sym["p_stop"], abs=0.05)
    weit = p_target_before_stop(100, 0.2, 0.5, 0.5, 2, n=4000)
    assert weit["p_offen"] > 0.95
    short = p_target_before_stop(100, 0.5, 0.08, 0.04, 10, n=8000, richtung="short")
    assert short["p_stop"] > short["p_ziel"]
    assert p_target_before_stop(100, 0.5, 0.08, 0.04, 10, n=3000) == p_target_before_stop(100, 0.5, 0.08, 0.04, 10, n=3000)


def test_black_scholes_lehrbuch():
    # Hull: S=42, K=40, r=10 %, sigma=20 %, T=0,5 -> Call 4,76, Put 0,81
    c = black_scholes(42, 40, 182.5, 0.2, "call", r=0.10, bezugsverhaeltnis=1)
    p = black_scholes(42, 40, 182.5, 0.2, "put", r=0.10, bezugsverhaeltnis=1)
    assert c["fairer_preis"] == pytest.approx(4.76, abs=0.01)
    assert p["fairer_preis"] == pytest.approx(0.81, abs=0.01)
    assert c["p_im_geld"] + p["p_im_geld"] == pytest.approx(1.0)
    assert c["break_even"] == pytest.approx(40 + c["fairer_preis"])
    assert c["p_ueber_break_even"] < c["p_im_geld"]
    assert c["zeitwertverlust_woche"] < 0
    assert c["omega"] > 1


def test_black_scholes_bezugsverhaeltnis_und_wechselkurs():
    a = black_scholes(100, 105, 90, 0.4, bezugsverhaeltnis=1)
    b = black_scholes(100, 105, 90, 0.4, bezugsverhaeltnis=0.1, wechselkurs=1.25)
    assert b["fairer_preis"] == pytest.approx(a["fairer_preis"] * 0.1 / 1.25)
    assert b["omega"] == pytest.approx(a["omega"])
    teuer = black_scholes(100, 105, 90, 0.4, bezugsverhaeltnis=1, preis=a["fairer_preis"] * 1.2)
    assert teuer["aufgeld_zum_fairen_preis_pct"] == pytest.approx(20)
    assert teuer["break_even"] > a["break_even"]


def test_scalable_filter():
    f = scalable_filter(40.0, 8, "long")
    assert f == {"typ": "Knock-out / Turbo", "richtung": "Long", "laufzeit": "Open End",
                 "hebel_von": 7, "hebel_bis": 9, "ko_schwelle": 35.0,
                 "bezugsverhaeltnis": 0.1, "max_spread_pct": 1.0}
    s = scalable_filter(40.0, 8, "short")
    assert s["richtung"] == "Short" and s["ko_schwelle"] == 45.0
    assert "wkn" not in f
