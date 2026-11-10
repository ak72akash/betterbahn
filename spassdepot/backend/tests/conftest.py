"""Gemeinsame Test-Helfer. Kein Test ruft eine echte Schnittstelle auf."""
import json
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.config import Konfig
from app.data.base import AnbieterFehler, Kurs, PriceProvider, verlauf_df
from app.data.kette import AnbieterKette
from app.main import create_app

MO_MITTAG = datetime(2026, 11, 9, 11, 0, tzinfo=UTC)       # Montag 12:00 Berlin: Xetra offen, USA zu
MO_ABEND = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)        # Montag 17:00 Berlin: Xetra und USA offen
SAMSTAG = datetime(2026, 11, 7, 11, 0, tzinfo=UTC)


class FakeWS:
    """Gemockter WebSocket: liefert vorbereitete Nachrichten, merkt sich Gesendetes."""

    def __init__(self, nachrichten, fehler: Exception | None = None):
        self.nachrichten, self.fehler, self.gesendet = list(nachrichten), fehler, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def send(self, text):
        self.gesendet.append(json.loads(text))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.nachrichten:
            return json.dumps(self.nachrichten.pop(0))
        if self.fehler:
            raise self.fehler
        raise StopAsyncIteration


class FakeAnbieter(PriceProvider):
    """Kursquelle für Tests: feste Kurse, zählbare Aufrufe, schaltbarer Ausfall."""

    def __init__(self, name="fake", kurse=None, kaputt=False, verzoegerung=0, nur=None, **kw):
        super().__init__()
        self.name = name
        self.kurse = kurse or {}
        self.kaputt, self.verzoegerung, self.nur = kaputt, verzoegerung, nur
        self.aufrufe = 0
        self.__dict__.update(kw)

    def unterstuetzt(self, symbol):
        return self.nur is None or symbol in self.nur

    async def latest_price(self, symbol):
        self.aufrufe += 1
        if self.kaputt or symbol not in self.kurse:
            raise AnbieterFehler(f"{self.name}: Ausfall")
        return Kurs(symbol, self.kurse[symbol], datetime.now(UTC), self.name, self.verzoegerung)

    async def daily_history(self, symbol, tage):
        self.aufrufe += 1
        if self.kaputt:
            raise AnbieterFehler(f"{self.name}: Ausfall")
        return verlauf(tage, ende=self.kurse.get(symbol, 100.0))


def verlauf(tage=120, ende=100.0, sigma=0.4, seed=3):
    rng = np.random.default_rng(seed)
    r = rng.normal(0, sigma / np.sqrt(252), tage)
    kurse = ende * np.exp(np.cumsum(r) - r.sum())
    tage_liste = [d.date() for d in pd.bdate_range(end=date(2026, 11, 6), periods=tage)]
    return verlauf_df([{"datum": d, "open": k, "high": k, "low": k, "close": k, "volume": 1.0}
                       for d, k in zip(tage_liste, kurse, strict=True)])


@pytest.fixture
def fake():
    return FakeAnbieter(kurse={"IFX.DE": 40.0, "NVDA": 200.0, "EURUSD": 1.25, "SAP.DE": 240.0})


@pytest.fixture
def app(fake, tmp_path):
    cfg = Konfig(database_url=f"sqlite:///{tmp_path / 'test.db'}", provider_order=["fake"],
                 app_password="", live_aktiv=False, jobs_aktiv=False)
    return create_app(cfg, AnbieterKette([fake]))


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def trade_daten(**kw):
    d = {"datum_kauf": str(date.today() - timedelta(days=1)), "wertpapier": "Turbo Long Infineon",
         "typ": "ko_long", "basiswert": "Infineon", "symbol": "IFX.DE", "stueck": 200, "kaufkurs": 0.5,
         "ko_schwelle": 35.0, "bezugsverhaeltnis": 0.1, "prognose_p_gewinn": 0.45, "ziel": 44.0,
         "stop": 38.0, "these": "Ausbruch über 40"}
    d.update(kw)
    return d
