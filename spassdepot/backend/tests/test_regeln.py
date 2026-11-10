from datetime import date

import pytest

from app.rules.grenzen import STANDARD
from app.rules.regeln import (
    ampel,
    ausstieg_aktie,
    ausstieg_knockout,
    chance_risiko,
    earnings_regel,
    eur,
    handelstage,
    hebel_obergrenze,
    max_positionsgroesse,
    pruefe_position,
    qualitaetsschwelle,
    risk_off_aktiv,
    verlustbremse,
)


def nach_regel(erg):
    return {e.regel: e for e in erg}


def test_format():
    assert eur(1234.56) == "1.234,56 €"


def test_max_positionsgroesse():
    assert max_positionsgroesse("ko_long", 1000).wert == 100
    assert max_positionsgroesse("aktie", 1000).wert == 250
    assert max_positionsgroesse("ko_long", 650).wert == 50              # Verlustbremse
    assert max_positionsgroesse("aktie", 1000, risk_off=True).wert == 125
    assert max_positionsgroesse("ko_short", 650, risk_off=True).wert == 25
    assert "Verlustbremse" in max_positionsgroesse("ko_long", 650).begruendung


def test_verlustbremse():
    assert verlustbremse(1000).ok
    assert verlustbremse(700).ok
    r = verlustbremse(699.99)
    assert not r.ok and "halbe" in r.begruendung


def test_pruefe_position_alles_ok():
    erg = pruefe_position("ko_long", 100, depotwert=1000, bargeld=1000)
    assert all(e.ok for e in erg)
    assert {e.regel for e in erg} == {"positionsgroesse", "hebel_anteil", "reserve", "branche"}


def test_pruefe_position_verstoesse():
    r = nach_regel(pruefe_position("ko_long", 120, 1000, 1000))
    assert not r["positionsgroesse"].ok and "überschreitet" in r["positionsgroesse"].begruendung
    r = nach_regel(pruefe_position("ko_long", 100, 1000, 600, hebel_bestand=450))
    assert not r["hebel_anteil"].ok
    r = nach_regel(pruefe_position("aktie", 250, 1000, 400))
    assert not r["reserve"].ok                       # 150 € Rest < 200 € Reserve
    assert "hebel_anteil" not in r
    r = nach_regel(pruefe_position("aktie", 100, 1000, 1000, positionen_in_branche=2))
    assert not r["branche"].ok
    r = nach_regel(pruefe_position("ko_long", 100, 1000, 1000, risk_off=True))
    assert not r["positionsgroesse"].ok


def test_grenzen_aenderbar():
    g = {**STANDARD, "max_ko_einsatz": 200.0}
    assert nach_regel(pruefe_position("ko_long", 150, 1000, 1000, g=g))["positionsgroesse"].ok


def test_hebel_obergrenze():
    assert hebel_obergrenze(9, 0.57).ok
    r = hebel_obergrenze(10, 0.57)
    assert not r.ok and r.wert == 9
    assert not hebel_obergrenze(10, 0.30, earnings_in_haltedauer=True).ok
    assert hebel_obergrenze(8, 0.30, earnings_in_haltedauer=True).ok


def test_earnings_regel():
    assert earnings_regel(5, 6, earnings_in_haltedauer=False).ok
    assert not earnings_regel(10, 6, True).ok        # 10 % < 12 %
    assert earnings_regel(12, 6, True).ok


def test_qualitaetsschwelle():
    assert chance_risiko(100, 112, 94) == pytest.approx(2.0)
    assert chance_risiko(100, 88, 106, "short") == pytest.approx(2.0)
    assert all(e.ok for e in qualitaetsschwelle(0.25, 100, 112, 94))
    r = nach_regel(qualitaetsschwelle(0.15, 100, 105, 95))
    assert not r["pick_wahrscheinlichkeit"].ok and not r["pick_crv"].ok
    assert nach_regel(qualitaetsschwelle(0.20, 100, 106, 96))["pick_crv"].ok   # genau 1,5
    with pytest.raises(ValueError):
        chance_risiko(100, 90, 95)


def test_risk_off():
    assert risk_off_aktiv(False, -1.0).ok
    assert not risk_off_aktiv(True, 0.5).ok
    r = risk_off_aktiv(False, -2.4)
    assert not r.ok and "Index" in r.begruendung
    assert risk_off_aktiv(False, None).ok


def test_ausstieg_knockout():
    assert ausstieg_knockout(20, 3, 9) == []
    assert [s.regel for s in ausstieg_knockout(100, 3, 15)] == ["ko_verdopplung"]
    assert [s.regel for s in ausstieg_knockout(-50, 3, 6)] == ["ko_verlust"]
    assert [s.regel for s in ausstieg_knockout(5, 10, 9)] == ["ko_zeitstop"]
    assert [s.regel for s in ausstieg_knockout(-10, 2, 3.9)] == ["ko_abstand"]
    alle = ausstieg_knockout(-60, 12, 2)
    assert {s.regel for s in alle} == {"ko_verlust", "ko_zeitstop", "ko_abstand"}
    assert all(not s.ok and s.begruendung for s in alle)


def test_ausstieg_aktie():
    assert ausstieg_aktie(100, 110, 95) == []
    assert [s.regel for s in ausstieg_aktie(110, 110, 95)] == ["aktie_ziel"]
    assert [s.regel for s in ausstieg_aktie(94.9, 110, 95)] == ["aktie_stop"]
    assert ausstieg_aktie(50, None, None) == []


def test_ampel():
    assert ampel([]) == "gruen"
    assert ampel(ausstieg_knockout(120, 1, 20)) == "gelb"
    assert ampel(ausstieg_knockout(-55, 1, 20)) == "rot"


def test_handelstage():
    assert handelstage(date(2026, 11, 9), date(2026, 11, 10)) == 1
    assert handelstage(date(2026, 11, 6), date(2026, 11, 9)) == 1       # Fr -> Mo
    assert handelstage(date(2026, 11, 2), date(2026, 11, 16)) == 10
