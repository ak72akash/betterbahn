export type Kennzeichnung = "Fakt" | "Annahme" | "Modellwert";
export type TradeTyp = "aktie" | "ko_long" | "ko_short";
export type Richtung = "long" | "short";

export interface Kurs {
  symbol: string;
  kurs: number;
  waehrung: string;
  zeitstempel: string;
  empfangen: string;
  quelle: string;
  verzoegerung_sek: number;
  schlusskurs: boolean;
  etikett: string;
  veraltet: boolean;
  markt: string;
  markt_offen: boolean;
  gettex_offen: boolean;
  hinweis: string | null;
  weitere_quellen: Kurs[];
}

export interface Vol {
  symbol: string;
  vol20: number;
  vol60: number | null;
  sigma_vorschlag: number;
  letzter_schluss: number;
  stand: string;
  quelle: string;
  tage: number;
  naechste_quartalszahlen: string | null;
}

export interface Regel {
  regel: string;
  ok: boolean;
  begruendung: string;
  wert: number | null;
}

export interface Filterwerte {
  typ: string;
  richtung: string;
  laufzeit: string;
  hebel_von: number;
  hebel_bis: number;
  ko_schwelle: number;
  bezugsverhaeltnis: number;
  max_spread_pct: number;
  kurs: number;
  symbol: string | null;
  hinweis: string;
}

export interface HistKlasse {
  von: number;
  bis: number;
  anteil: number;
  ko: boolean;
}

export interface KnockoutEingabe {
  symbol?: string | null;
  kurs: number;
  sigma: number;
  hebel: number;
  tage: number;
  einsatz: number;
  richtung: Richtung;
  zahlen_ueber_nacht: boolean;
}

export interface KnockoutErgebnis {
  ko_schwelle: number;
  p_ko: number;
  p_gewinn: number;
  p_verdopplung: number;
  median: number;
  top25: number;
  top10: number;
  erwartung: number;
  histogramm: HistKlasse[] | null;
  max_hebel: number;
  hebel_regel: Regel;
  filter: Filterwerte;
  verwendeter_kurs: number;
  gap_sd: number;
  n: number;
  seed: number;
  dauer_ms: number;
}

export interface OptionsscheinErgebnis {
  fairer_preis: number;
  delta: number;
  omega: number;
  break_even: number;
  p_im_geld: number;
  p_ueber_break_even: number;
  zeitwertverlust_woche: number;
  innerer_wert: number;
  zeitwert: number;
  aufgeld_zum_fairen_preis_pct: number | null;
}

export interface Trade {
  id: number;
  datum_kauf: string;
  wertpapier: string;
  wkn: string | null;
  typ: TradeTyp;
  basiswert: string | null;
  symbol: string;
  stueck: number;
  kaufkurs: number;
  ko_schwelle: number | null;
  bezugsverhaeltnis: number | null;
  prognose_p_gewinn: number | null;
  ziel: number | null;
  stop: number | null;
  these: string | null;
  datum_verkauf: string | null;
  verkaufskurs: number | null;
  gebuehren: number;
  lehre: string | null;
  einsatz: number;
  ergebnis_eur: number | null;
  ergebnis_pct: number | null;
  offen: boolean;
}
export type TradeNeu = Omit<Trade, "id" | "einsatz" | "ergebnis_eur" | "ergebnis_pct" | "offen">;

export interface Position {
  trade_id: number;
  wertpapier: string;
  symbol: string;
  typ: TradeTyp;
  stueck: number;
  kaufkurs: number;
  einsatz: number;
  ko_schwelle: number | null;
  bezugsverhaeltnis: number | null;
  ziel: number | null;
  stop: number | null;
  handelstage: number;
  kurs: number | null;
  wert: number | null;
  wert_je_stueck: number | null;
  perf_pct: number | null;
  ko_abstand_pct: number | null;
  geschaetzt: boolean;
  hinweis: string | null;
  signale: Regel[];
  ampel: "gruen" | "gelb" | "rot" | "grau";
  kurs_info: Kurs | null;
  eurusd: number | null;
}

export interface Depot {
  startkapital: number;
  depotwert: number;
  veraenderung_eur: number;
  veraenderung_pct: number;
  bargeld: number;
  reserve_anteil: number;
  reserve_minimum: number;
  gebunden: number;
  hebel_einsatz: number;
  wert_offen: number;
  realisiert: number;
  offene_positionen: number;
}

export interface Risiko {
  risk_off: boolean;
  risk_off_text: string;
  verlustbremse: boolean;
  verlustbremse_text: string;
  max_knockout: number;
  max_aktie: number;
}

export interface PositionsCheck {
  zeit: string;
  depot: Depot;
  risiko: Risiko;
  positionen: Position[];
}

export interface Termin {
  id: number;
  datum: string;
  symbol: string | null;
  art: string;
  notiz: string | null;
}

export interface Alarm {
  id: number;
  zeit: string;
  position: string;
  trade_id: number | null;
  regel: string;
  text: string;
  gelesen: boolean;
}

export interface PlanEintrag {
  id: number;
  woche: string;
  position: string;
  symbol: string | null;
  typ: TradeTyp;
  einsatz: number;
  kaufzeitpunkt: string | null;
  kaufbedingung: string | null;
  filter: string | null;
  ziel: string | null;
  ausstieg: string | null;
  status: "offen" | "signal" | "gekauft" | "verworfen";
}

export interface Pick {
  id: number;
  datum: string;
  aktie: string;
  symbol: string;
  richtung: Richtung;
  kurs: number;
  quelle: string | null;
  ziel: number;
  stop: number;
  p_ziel_vor_stop: number | null;
  katalysator: string | null;
  ergebnis_5t: number | null;
  ergebnis_10t: number | null;
}

export interface PickPruefung {
  ok: boolean;
  gespeichert: boolean;
  regeln: Regel[];
  p_ziel: number;
  p_stop: number;
  p_offen: number;
  sigma: number;
  sigma_quelle: string;
}

export interface WatchlistEintrag {
  id: number;
  symbol: string;
  name: string;
  branche: string | null;
}

export interface Statistik {
  anzahl_geschlossen: number;
  anzahl_offen: number;
  gewinner: number;
  verlierer: number;
  trefferquote: number | null;
  gewinnfaktor: number | null;
  summe_gewinne: number;
  summe_verluste: number;
  ergebnis_gesamt: number;
  durchschnitt_gewinn: number | null;
  durchschnitt_verlust: number | null;
  depotverlauf: { datum: string; depotwert: number }[];
  kalibrierung: { gruppe: string; anzahl: number; prognose_mittel: number | null; trefferquote: number | null }[];
  regelverstoesse: { trade_id: number | null; wertpapier: string; datum: string; regel: string; text: string }[];
}

export interface Einstellung {
  schluessel: string;
  wert: number | boolean | string;
  vorgabe: number | boolean | string;
  beschreibung: string;
}

export interface AnbieterStatus {
  name: string;
  verbunden: boolean;
  stream: boolean;
  nur_schlusskurs: boolean;
  pausiert: boolean;
  letzter_erfolg: string | null;
  letzter_fehler: string | null;
  abfragen_heute: number;
  limit_tag: number | null;
  verbleibend_heute: number | null;
}

export interface AnbieterUebersicht {
  reihenfolge: string[];
  aktiv: AnbieterStatus[];
  nicht_konfiguriert: { name: string; grund: string }[];
  live_dienst: boolean;
  symbole: string[];
}

export interface RegelCheck {
  ok: boolean;
  regeln: Regel[];
  depotwert: number;
  bargeld: number;
  risk_off: boolean;
}

export interface Morgenbericht extends PositionsCheck {
  zusammenfassung: string[];
  termine: Termin[];
  gespeichert_am: string | null;
}

export interface Wochenbilanz {
  woche: string;
  von: string;
  bis: string;
  ergebnis_woche: number;
  trefferquote_woche: number | null;
  gekauft: { id: number; wertpapier: string; einsatz: number }[];
  verkauft: { id: number; wertpapier: string; ergebnis_eur: number | null }[];
  lehren: string[];
  gespeichert_am: string | null;
}
