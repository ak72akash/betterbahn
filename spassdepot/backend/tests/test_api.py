"""API-Endpunkte mit TestClient (Anbieter gemockt)."""
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.config import Konfig
from app.data.base import Kurs
from app.data.kette import AnbieterKette
from app.jobs import ZEITPLAN, erstelle_scheduler
from app.main import create_app
from tests.conftest import FakeAnbieter, trade_daten


def test_health_und_doku(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    spec = client.get("/api/openapi.json").json()
    for pfad in ("/api/quote/{symbol}", "/api/vol/{symbol}", "/api/sim/knockout", "/api/sim/target-stop",
                 "/api/sim/warrant", "/api/filter", "/api/trades", "/api/picks", "/api/plan", "/api/watchlist",
                 "/api/events", "/api/positions/check", "/api/stats", "/api/reports/morning",
                 "/api/reports/week", "/api/settings", "/api/alerts"):
        assert pfad in spec["paths"], pfad
    assert client.get("/api/docs").status_code == 200


def test_quote_und_vol(client, fake):
    q = client.get("/api/quote/ifx.de").json()
    assert q["kurs"] == 40.0 and q["quelle"] == "fake" and q["etikett"] == "Echtzeit" and q["waehrung"] == "EUR"
    assert q["kennzeichnung"] == "Fakt" and q["weitere_quellen"] == []
    client.get("/api/quote/IFX.DE")
    assert fake.aufrufe == 1                                     # zweite Abfrage aus dem Kursspeicher
    assert client.get("/api/quote/GIBTSNICHT").status_code == 503
    v = client.get("/api/vol/IFX.DE").json()
    assert 0.2 < v["vol20"] < 0.7 and v["sigma_vorschlag"] == max(v["vol20"], v["vol60"])
    assert v["kennzeichnung"] == "Modellwert" and v["quelle"] == "fake"
    assert client.get("/api/vol/IFX.DE").json()["quelle"] == "fake (Cache)"
    assert [k["symbol"] for k in client.get("/api/quotes").json()] == ["IFX.DE"]


def test_sim_knockout(client):
    r = client.post("/api/sim/knockout", json={"symbol": "IFX.DE", "kurs": 100, "sigma": 0.57, "hebel": 10}).json()
    assert 0.30 <= r["p_ko"] <= 0.38 and r["verwendeter_kurs"] == 100 and r["max_hebel"] == 9
    assert r["hebel_regel"]["ok"] is False and r["kennzeichnung"] == "Modellwert"
    assert r["filter"]["ko_schwelle"] == 90.0 and "wkn" not in r["filter"]
    assert abs(sum(k["anteil"] for k in r["histogramm"]) - 1) < 1e-9
    assert r["dauer_ms"] < 2000 and r["n"] == 40000 and r["seed"] == 1
    kurz = {"kurs": 100, "sigma": 0.57, "hebel": 10, "n": 4000, "histogramm": False}
    a, b = client.post("/api/sim/knockout", json=kurz).json(), client.post("/api/sim/knockout", json=kurz).json()
    assert a["p_ko"] == b["p_ko"] and a["histogramm"] is None
    assert client.post("/api/sim/knockout", json={**kurz, "seed": 5}).json()["p_ko"] != a["p_ko"]
    s = client.post("/api/sim/knockout", json={**kurz, "richtung": "short", "zahlen_ueber_nacht": True}).json()
    assert s["ko_schwelle"] == 110.0 and s["gap_sd"] == 0.06 and s["max_hebel"] == 8
    assert client.post("/api/sim/knockout", json={**kurz, "hebel": 1}).status_code == 422
    lang = client.post("/api/sim/knockout", json={"kurs": 100, "sigma": 0.5, "hebel": 5, "tage": 30}).json()
    assert lang["n"] < 40000 and lang["dauer_ms"] < 2000


def test_sim_ziel_stop_optionsschein_filter(client):
    z = client.post("/api/sim/target-stop", json={"kurs": 100, "sigma": 0.5, "ziel_pct": 0.08, "stop_pct": 0.04}).json()
    assert abs(z["p_ziel"] + z["p_stop"] + z["p_offen"] - 1) < 1e-9 and z["crv"] == 2.0
    w = client.post("/api/sim/warrant", json={"kurs": 42, "basispreis": 40, "tage": 182, "sigma": 0.2,
                                              "zins": 0.1, "bezugsverhaeltnis": 1}).json()
    assert abs(w["fairer_preis"] - 4.76) < 0.03 and w["omega"] > 1
    f = client.get("/api/filter", params={"symbol": "ifx.de", "hebel": 8, "richtung": "long"}).json()
    assert f["kurs"] == 40.0 and f["ko_schwelle"] == 35.0 and f["bezugsverhaeltnis"] == 0.1 and f["laufzeit"] == "Open End"
    assert client.get("/api/filter", params={"hebel": 8}).status_code == 422
    assert client.get("/api/filter", params={"kurs": 50, "hebel": 5, "richtung": "short"}).json()["ko_schwelle"] == 60.0


def test_trades_lebenslauf(client):
    r = client.post("/api/trades", json=trade_daten())
    assert r.status_code == 201
    tr = r.json()
    assert tr["einsatz"] == 100 and tr["offen"] and tr["ergebnis_eur"] is None
    assert client.post("/api/trades", json=trade_daten(ko_schwelle=None)).status_code == 422
    assert client.post("/api/trades", json=trade_daten(stueck=-1)).status_code == 422
    assert client.patch(f"/api/trades/{tr['id']}", json={"these": "neu"}).json()["these"] == "neu"
    assert client.patch(f"/api/trades/{tr['id']}", json={"typ": "aktie", "verkaufskurs": 1}).status_code == 422
    # Teilverkauf der Hälfte bei +100 %
    teil = client.post(f"/api/trades/{tr['id']}/schliessen",
                       json={"datum_verkauf": str(date.today()), "verkaufskurs": 1.0, "stueck": 100, "gebuehren": 0.99}).json()
    assert teil["id"] != tr["id"] and teil["stueck"] == 100 and abs(teil["ergebnis_eur"] - 49.01) < 1e-9
    assert [x["stueck"] for x in client.get("/api/trades", params={"status": "offen"}).json()] == [100]
    zu = client.post(f"/api/trades/{tr['id']}/schliessen",
                     json={"datum_verkauf": str(date.today()), "verkaufskurs": 0.25, "lehre": "Stop früher"}).json()
    assert zu["ergebnis_eur"] == -25 and zu["ergebnis_pct"] == -50 and zu["lehre"] == "Stop früher"
    assert client.post(f"/api/trades/{tr['id']}/schliessen",
                       json={"datum_verkauf": str(date.today()), "verkaufskurs": 1}).status_code == 409
    assert len(client.get("/api/trades", params={"status": "geschlossen"}).json()) == 2
    st = client.get("/api/stats").json()
    assert st["anzahl_geschlossen"] == 2 and st["trefferquote"] == 0.5
    assert st["kalibrierung"][2]["anzahl"] == 2 and st["depotverlauf"][-1]["depotwert"] == 1024.01
    csv = client.get("/api/trades/export.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    zeilen = csv.text.lstrip("﻿").strip().splitlines()
    assert len(zeilen) == 3 and zeilen[0].startswith("datum_kauf;wertpapier;wkn") and "49,01" in csv.text
    assert client.delete(f"/api/trades/{teil['id']}").status_code == 204
    assert client.get(f"/api/trades/{teil['id']}").status_code == 404


def test_positions_check_und_depot(client, app):
    client.post("/api/trades", json=trade_daten())
    client.post("/api/trades", json=trade_daten(symbol="NVDA", wertpapier="Turbo Long Nvidia", ko_schwelle=180.0,
                                                kaufkurs=1.6, stueck=50))
    client.get("/api/quote/IFX.DE"), client.get("/api/quote/NVDA"), client.get("/api/quote/EURUSD")
    c = client.get("/api/positions/check").json()
    ifx, nvda = c["positionen"]
    assert ifx["wert"] == 100 and ifx["perf_pct"] == 0 and round(ifx["ko_abstand_pct"], 1) == 12.5
    assert ifx["ampel"] == "gruen" and ifx["kurs_info"]["quelle"] == "fake" and ifx["geschaetzt"]
    assert abs(nvda["wert"] - 80) < 1e-9 and nvda["eurusd"] == 1.25
    assert c["depot"]["depotwert"] == 1000 and c["depot"]["bargeld"] == 820 and c["depot"]["hebel_einsatz"] == 180
    assert c["risiko"]["max_knockout"] == 100
    # zweite Quelle weicht um 5 % ab -> beide anzeigen
    jetzt = datetime.now(UTC)
    app.state.z.store.aktualisiere(Kurs("IFX.DE", 42.0, jetzt, "andere", empfangen=jetzt - timedelta(seconds=30)))
    q = client.get("/api/quote/IFX.DE").json()
    assert q["quelle"] == "fake" and [w["quelle"] for w in q["weitere_quellen"]] == ["andere"]


def test_regel_check(client):
    ok = client.post("/api/rules/check", json={"typ": "ko_long", "einsatz": 100, "symbol": "IFX.DE"}).json()
    assert ok["ok"] and len(ok["regeln"]) == 4
    assert not client.post("/api/rules/check", json={"typ": "ko_long", "einsatz": 150}).json()["ok"]
    for sym in ("NVDA", "AMD"):
        client.post("/api/trades", json=trade_daten(symbol=sym, kaufkurs=0.25))
    r = client.post("/api/rules/check", json={"typ": "ko_long", "einsatz": 50, "symbol": "IFX.DE"}).json()
    branche = next(x for x in r["regeln"] if x["regel"] == "branche")
    assert not branche["ok"]                                     # dritte Halbleiter-Position
    client.put("/api/settings", json={"risk_off": True})
    r = client.post("/api/rules/check", json={"typ": "ko_long", "einsatz": 100}).json()
    assert r["risk_off"] and not r["ok"]


def test_einstellungen(client):
    e = {x["schluessel"]: x for x in client.get("/api/settings").json()}
    assert e["max_ko_einsatz"]["wert"] == 100 and e["risk_off"]["wert"] is False and e["max_ko_einsatz"]["beschreibung"]
    neu = {x["schluessel"]: x["wert"] for x in client.put("/api/settings", json={"max_ko_einsatz": 80, "risk_off": True}).json()}
    assert neu["max_ko_einsatz"] == 80 and neu["risk_off"] is True
    assert client.post("/api/rules/check", json={"typ": "ko_long", "einsatz": 50}).json()["ok"] is False   # 80 × 0,5
    assert client.put("/api/settings", json={"gibtsnicht": 1}).status_code == 422
    assert client.put("/api/settings", json={"max_ko_einsatz": "viel"}).status_code == 422


def test_picks_qualitaetsschwelle(client):
    basis = {"datum": str(date.today()), "aktie": "Infineon", "symbol": "ifx.de", "kurs": 40.0, "quelle": "fake",
             "katalysator": "Zahlen", "sigma": 0.5}
    schlecht = client.post("/api/picks", json={**basis, "ziel": 41.0, "stop": 39.0}).json()
    assert not schlecht["ok"] and not schlecht["gespeichert"]                       # CRV 1,0
    assert any(not r["ok"] and r["regel"] == "pick_crv" for r in schlecht["regeln"])
    assert client.get("/api/picks").json() == []
    gut = client.post("/api/picks", json={**basis, "ziel": 44.0, "stop": 38.0}).json()
    assert gut["ok"] and gut["gespeichert"] and gut["pick"]["symbol"] == "IFX.DE"
    assert gut["pick"]["p_ziel_vor_stop"] == gut["p_ziel"] >= 0.2
    erzwungen = client.post("/api/picks", json={**basis, "ziel": 41.0, "stop": 39.0, "trotzdem_speichern": True}).json()
    assert not erzwungen["ok"] and erzwungen["gespeichert"]
    assert client.post("/api/picks", json={**basis, "ziel": 38.0, "stop": 44.0}).status_code == 422
    ohne_sigma = {k: v for k, v in basis.items() if k != "sigma"}
    auto = client.post("/api/picks", json={**ohne_sigma, "ziel": 44.0, "stop": 38.0}).json()
    assert "realisierte Volatilität" in auto["sigma_quelle"]
    pid = gut["pick"]["id"]
    assert client.patch(f"/api/picks/{pid}", json={"ergebnis_5t": 3.2}).json()["ergebnis_5t"] == 3.2
    assert client.post("/api/picks/bewerten").json() == {"aktualisiert": 0}          # Zeitraum läuft noch
    assert client.delete(f"/api/picks/{pid}").status_code == 204


def test_plan_watchlist_events(client):
    p = client.post("/api/plan", json={"woche": "2026-KW46", "position": "Turbo Long Infineon", "symbol": "ifx.de",
                                       "kaufbedingung": "Schluss über 40", "filter": "Hebel 7–9"}).json()
    assert p["status"] == "offen" and p["symbol"] == "IFX.DE"
    assert client.patch(f"/api/plan/{p['id']}", json={"status": "signal"}).json()["status"] == "signal"
    assert client.patch(f"/api/plan/{p['id']}", json={"status": "vielleicht"}).status_code == 422
    tr = client.post(f"/api/plan/{p['id']}/uebernehmen", json=trade_daten())
    assert tr.status_code == 201 and client.get(f"/api/plan/{p['id']}").json()["status"] == "gekauft"
    assert len(client.get("/api/watchlist").json()) == 11
    assert client.post("/api/watchlist", json={"symbol": "nvda", "name": "Nvidia"}).status_code == 409
    w = client.post("/api/watchlist", json={"symbol": "avgo", "name": "Broadcom", "branche": "Halbleiter"}).json()
    assert w["symbol"] == "AVGO" and "AVGO" in client.get("/api/providers").json()["symbole"]
    assert client.delete(f"/api/watchlist/{w['id']}").status_code == 204
    e = client.post("/api/events", json={"datum": str(date.today() + timedelta(days=3)), "symbol": "IFX.DE",
                                         "art": "Quartalszahlen", "notiz": "vor Börsenstart"}).json()
    assert client.get("/api/vol/IFX.DE").json()["naechste_quartalszahlen"] == e["datum"]
    assert client.delete(f"/api/events/{e['id']}").status_code == 204
    assert client.get("/api/plan/999").status_code == 404


def test_berichte(client):
    client.post("/api/trades", json=trade_daten())
    client.get("/api/quote/IFX.DE")
    client.post("/api/plan", json={"woche": "2026-KW46", "position": "Turbo Long SAP", "symbol": "SAP.DE", "einsatz": 150})
    client.post("/api/events", json={"datum": str(date.today() + timedelta(days=2)), "symbol": "SAP.DE", "art": "Quartalszahlen"})
    m = client.get("/api/reports/morning").json()
    assert m["art"] == "morgen" and len(m["positionen"]) == 1 and len(m["termine"]) == 1 and m["gespeichert_am"]
    hinweise = " ".join(m["plan"][0]["hinweise"])
    assert "über dem aktuellen Limit" in hinweise and "Quartalszahlen" in hinweise
    assert "Depotwert 1.000,00 €" in m["zusammenfassung"][0]
    assert client.get("/api/reports/morning").json()["bericht_id"] == m["bericht_id"]        # gespeichert
    assert client.get("/api/reports/morning", params={"neu": True}).json()["bericht_id"] != m["bericht_id"]
    w = client.get("/api/reports/week").json()
    assert w["art"] == "woche" and w["woche"].startswith("20") and w["offene_positionen"] == 1
    assert client.get("/api/reports/positions").json() is None


def test_alerts_api(client, app):
    from sqlmodel import Session

    from app import db
    client.post("/api/trades", json=trade_daten())
    z = app.state.z
    jetzt = datetime.now(UTC)
    z.store.aktualisiere(Kurs("IFX.DE", 36.0, jetzt, "fake", empfangen=jetzt))
    with Session(z.engine) as s:
        z.warnungen.pruefe(s, z.store, db.lade_grenzen(s), "IFX.DE")
    a = client.get("/api/alerts", params={"nur_ungelesen": True}).json()
    assert {x["regel"] for x in a} == {"ko_verlust", "ko_abstand"} and all(x["position"] == "Turbo Long Infineon" for x in a)
    assert client.post(f"/api/alerts/{a[0]['id']}/gelesen").json()["gelesen"] is True
    assert client.post("/api/alerts/gelesen").json() == {"gelesen": 1}
    assert client.get("/api/alerts", params={"nur_ungelesen": True}).json() == []
    assert len(client.get("/api/alerts").json()) == 2


def test_websocket_und_sse(client, app):
    client.get("/api/quote/IFX.DE")
    with client.websocket_connect("/api/ws/prices") as ws:
        erste = ws.receive_json()
        assert erste["typ"] == "kurs" and erste["daten"]["symbol"] == "IFX.DE"
        app.state.z.verteiler.sende({"typ": "alert", "daten": {"text": "Warnung"}})
        assert ws.receive_json() == {"typ": "alert", "daten": {"text": "Warnung"}}


def test_passwortschutz(tmp_path):
    cfg = Konfig(database_url=f"sqlite:///{tmp_path / 'p.db'}", provider_order=[], app_password="geheim",
                 live_aktiv=False, jobs_aktiv=False)
    with TestClient(create_app(cfg, AnbieterKette([FakeAnbieter()]))) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/auth/status").json() == {"passwort_noetig": True, "angemeldet": False}
        assert c.get("/api/trades").status_code == 401
        assert c.post("/api/login", json={"passwort": "falsch"}).status_code == 401
        import pytest
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect("/api/ws/prices"):
                pass
        r = c.post("/api/login", json={"passwort": "geheim"})
        assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
        assert "geheim" not in r.headers["set-cookie"]
        assert c.get("/api/trades").status_code == 200
        c.post("/api/logout")
        c.cookies.clear()
        assert c.get("/api/trades").status_code == 401


def test_zeitplan(app):
    sch = erstelle_scheduler(app.state.z)
    jobs = {j.id: str(j.trigger) for j in sch.get_jobs()}
    assert set(jobs) == {n for n, *_ in ZEITPLAN}
    assert "day_of_week='mon-fri', hour='7', minute='45'" in jobs["morgenbericht"]
    assert "hour='13', minute='25'" in jobs["positionen_mittag"] and "hour='22', minute='25'" in jobs["positionen_abend"]
    assert "day_of_week='fri', hour='19', minute='15'" in jobs["wochenbilanz"]
    assert str(sch.timezone) == "Europe/Berlin"
