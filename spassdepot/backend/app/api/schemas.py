"""Pydantic-Schemas der API (Ein- und Ausgaben), soweit sie nicht in
``journal/tabellen.py`` bei den Tabellen stehen."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Kennzeichnung = Literal["Fakt", "Annahme", "Modellwert"]


class KursAusgabe(BaseModel):
    symbol: str
    kurs: float
    waehrung: str
    zeitstempel: datetime
    empfangen: datetime
    quelle: str
    verzoegerung_sek: int
    schlusskurs: bool
    etikett: str
    veraltet: bool
    markt: str
    markt_offen: bool
    gettex_offen: bool
    hinweis: str | None = None
    kennzeichnung: Kennzeichnung = "Fakt"
    weitere_quellen: list[KursAusgabe] = []


class VolAusgabe(BaseModel):
    symbol: str
    vol20: float
    vol60: float | None
    sigma_vorschlag: float = Field(description="Der höhere der beiden Werte (vorsichtige Annahme)")
    letzter_schluss: float
    stand: date
    quelle: str
    tage: int
    naechste_quartalszahlen: date | None = None
    kennzeichnung: Kennzeichnung = "Modellwert"


class RegelAusgabe(BaseModel):
    regel: str
    ok: bool
    begruendung: str
    wert: float | None = None


class FilterAusgabe(BaseModel):
    typ: str
    richtung: str
    laufzeit: str
    hebel_von: float
    hebel_bis: float
    ko_schwelle: float
    bezugsverhaeltnis: float
    max_spread_pct: float
    kurs: float
    symbol: str | None = None
    hinweis: str = "Suchwerte für die Derivate-Suche des Brokers. Die App nennt keine WKN."


class KnockoutEingabe(BaseModel):
    symbol: str | None = None
    kurs: float = Field(gt=0, description="Eingefrorener Kurs des Basiswerts")
    sigma: float = Field(gt=0, le=3, description="Annualisierte Volatilität, 0.57 = 57 %")
    hebel: float = Field(gt=1, le=100)
    tage: int = Field(default=10, ge=1, le=30)
    einsatz: float = Field(default=100, gt=0)
    richtung: Literal["long", "short"] = "long"
    zahlen_ueber_nacht: bool = False
    spread: float = Field(default=0.01, ge=0, le=0.2)
    fin: float = Field(default=0.05, ge=0, le=0.5)
    n: int | None = Field(default=None, ge=1000, le=100000)
    seed: int | None = None
    histogramm: bool = True


class HistogrammKlasse(BaseModel):
    von: float
    bis: float
    anteil: float
    ko: bool


class KnockoutAusgabe(BaseModel):
    ko_schwelle: float
    p_ko: float
    p_gewinn: float
    p_verdopplung: float
    median: float
    top25: float
    top10: float
    erwartung: float
    histogramm: list[HistogrammKlasse] | None = None
    max_hebel: int
    hebel_regel: RegelAusgabe
    filter: FilterAusgabe
    verwendeter_kurs: float
    gap_sd: float
    n: int
    seed: int
    dauer_ms: float
    kennzeichnung: Kennzeichnung = "Modellwert"


class ZielStopEingabe(BaseModel):
    kurs: float = Field(gt=0)
    sigma: float = Field(gt=0, le=3)
    ziel_pct: float = Field(gt=0, le=5, description="Abstand zum Ziel, 0.08 = 8 %")
    stop_pct: float = Field(gt=0, lt=1)
    tage: int = Field(default=10, ge=1, le=30)
    richtung: Literal["long", "short"] = "long"
    n: int | None = Field(default=None, ge=1000, le=100000)
    seed: int | None = None


class ZielStopAusgabe(BaseModel):
    p_ziel: float
    p_stop: float
    p_offen: float
    crv: float
    n: int
    seed: int
    kennzeichnung: Kennzeichnung = "Modellwert"


class OptionsscheinEingabe(BaseModel):
    kurs: float = Field(gt=0)
    basispreis: float = Field(gt=0)
    tage: int = Field(ge=1, le=3650, description="Restlaufzeit in Kalendertagen")
    sigma: float = Field(gt=0, le=3)
    typ: Literal["call", "put"] = "call"
    zins: float = Field(default=0.025, ge=-0.05, le=0.3)
    bezugsverhaeltnis: float = Field(default=0.1, gt=0)
    preis: float | None = Field(default=None, gt=0, description="Briefkurs des Scheins in €")
    wechselkurs: float = Field(default=1.0, gt=0, description="EUR/USD bei US-Basiswerten")


class OptionsscheinAusgabe(BaseModel):
    fairer_preis: float
    delta: float
    omega: float
    break_even: float
    p_im_geld: float
    p_ueber_break_even: float
    zeitwertverlust_woche: float
    innerer_wert: float
    zeitwert: float
    aufgeld_zum_fairen_preis_pct: float | None
    kennzeichnung: Kennzeichnung = "Modellwert"


class RegelCheckEingabe(BaseModel):
    typ: Literal["aktie", "ko_long", "ko_short"]
    einsatz: float = Field(gt=0)
    symbol: str | None = None


class RegelCheckAusgabe(BaseModel):
    ok: bool
    regeln: list[RegelAusgabe]
    depotwert: float
    bargeld: float
    risk_off: bool


class Position(BaseModel):
    trade_id: int
    wertpapier: str
    symbol: str
    typ: str
    stueck: float
    kaufkurs: float
    einsatz: float
    ko_schwelle: float | None
    bezugsverhaeltnis: float | None
    ziel: float | None
    stop: float | None
    handelstage: int
    kurs: float | None
    wert: float | None
    wert_je_stueck: float | None
    perf_pct: float | None
    ko_abstand_pct: float | None
    geschaetzt: bool
    hinweis: str | None
    signale: list[RegelAusgabe]
    ampel: Literal["gruen", "gelb", "rot", "grau"]
    kurs_info: KursAusgabe | None = None
    eurusd: float | None = None


class Depot(BaseModel):
    startkapital: float
    depotwert: float
    veraenderung_eur: float
    veraenderung_pct: float
    bargeld: float
    reserve_anteil: float
    reserve_minimum: float
    gebunden: float
    hebel_einsatz: float
    wert_offen: float
    realisiert: float
    offene_positionen: int


class Risiko(BaseModel):
    risk_off: bool
    risk_off_text: str
    verlustbremse: bool
    verlustbremse_text: str
    max_knockout: float
    max_aktie: float


class PositionsCheck(BaseModel):
    art: str
    zeit: datetime
    depot: Depot
    risiko: Risiko
    positionen: list[Position]
    gespeichert_am: datetime | None = None


class Termin(BaseModel):
    id: int | None = None
    datum: date
    symbol: str | None
    art: str
    notiz: str | None
    quelle: str = "manuell"


class Morgenbericht(PositionsCheck):
    plan: list[dict[str, Any]]
    termine: list[Termin]
    zusammenfassung: list[str]


class Wochenbilanz(BaseModel):
    art: str
    zeit: datetime
    woche: str
    von: date
    bis: date
    depot: Depot
    gekauft: list[dict[str, Any]]
    verkauft: list[dict[str, Any]]
    ergebnis_woche: float
    trefferquote_woche: float | None
    offene_positionen: int
    regelverstoesse: list[dict[str, Any]]
    picks: list[dict[str, Any]]
    lehren: list[str]
    gespeichert_am: datetime | None = None


class KalibrierungGruppe(BaseModel):
    gruppe: str
    anzahl: int
    prognose_mittel: float | None
    trefferquote: float | None


class Verstoss(BaseModel):
    trade_id: int | None
    wertpapier: str
    datum: date
    regel: str
    text: str


class DepotPunkt(BaseModel):
    datum: date
    depotwert: float


class Statistik(BaseModel):
    anzahl_geschlossen: int
    anzahl_offen: int
    gewinner: int
    verlierer: int
    trefferquote: float | None
    gewinnfaktor: float | None
    summe_gewinne: float
    summe_verluste: float
    ergebnis_gesamt: float
    durchschnitt_gewinn: float | None
    durchschnitt_verlust: float | None
    depotverlauf: list[DepotPunkt]
    kalibrierung: list[KalibrierungGruppe]
    regelverstoesse: list[Verstoss]


class AlertAusgabe(BaseModel):
    id: int
    zeit: datetime
    position: str
    trade_id: int | None
    regel: str
    text: str
    gelesen: bool


class Einstellung(BaseModel):
    schluessel: str
    wert: float | bool | str
    vorgabe: float | bool | str
    beschreibung: str


class AnbieterStatusAusgabe(BaseModel):
    name: str
    verbunden: bool
    stream: bool
    nur_schlusskurs: bool
    pausiert: bool
    letzter_erfolg: datetime | None
    letzter_fehler: str | None
    abfragen_heute: int
    limit_tag: int | None
    verbleibend_heute: int | None


class AnbieterUebersicht(BaseModel):
    reihenfolge: list[str]
    aktiv: list[AnbieterStatusAusgabe]
    nicht_konfiguriert: list[dict[str, str]]
    live_dienst: bool
    symbole: list[str]


class PickPruefung(BaseModel):
    ok: bool
    gespeichert: bool
    regeln: list[RegelAusgabe]
    p_ziel: float
    p_stop: float
    p_offen: float
    sigma: float
    sigma_quelle: str
    pick: dict[str, Any] | None = None
