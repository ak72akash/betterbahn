import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Api } from "../api/client";
import { useKurs } from "../api/live";
import type { Filterwerte, KnockoutErgebnis, OptionsscheinErgebnis, Richtung } from "../api/types";
import { Histogramm } from "../components/Histogramm";
import { LiveKurs } from "../components/LiveKurs";
import { Auswahl, Feld, Karte, Kennzahl, Kennzeichnung, Knopf, Meldung, Regler, Schalter, Segmente, Seitentitel } from "../components/ui";
import { anteil, datum, eur, kursText, parseZahl, pct, uhrzeit, zahl } from "../lib/format";

interface Eingefroren {
  kurs: number;
  quelle: string;
  zeit: string;
  waehrung: string;
}

function Kopierzeile({ label, wert, kopierwert }: { label: string; wert: string; kopierwert?: string }) {
  const [kopiert, setKopiert] = useState(false);
  const kopieren = async () => {
    try {
      await navigator.clipboard.writeText(kopierwert ?? wert);
      setKopiert(true);
      setTimeout(() => setKopiert(false), 1500);
    } catch {
      /* Zwischenablage nicht verfügbar */
    }
  };
  return (
    <div className="flex items-center justify-between gap-2 py-1.5">
      <span className="text-sm text-text2">{label}</span>
      <button type="button" onClick={kopieren} className="zahl min-h-9 rounded-lg border border-linie bg-erhoben px-3 text-sm font-medium" aria-label={`${label} ${wert} kopieren`}>
        {kopiert ? "kopiert ✓" : wert}
      </button>
    </div>
  );
}

export function filterText(f: Filterwerte): string {
  return `${f.typ}, ${f.richtung}, ${f.laufzeit}, Hebel ${zahl(f.hebel_von, 0)}–${zahl(f.hebel_bis, 0)}, KO-Schwelle ca. ${zahl(f.ko_schwelle)}, Bezugsverhältnis ${zahl(f.bezugsverhaeltnis, 1)}, Spread < ${zahl(f.max_spread_pct, 0)} %`;
}

function FilterKarte({ f, waehrung }: { f: Filterwerte; waehrung: string }) {
  return (
    <Karte titel="Suchwerte für Scalable" rechts={<Kennzeichnung art="Modellwert" />}>
      <div className="divide-y divide-linie">
        <Kopierzeile label="Typ" wert={f.typ} />
        <Kopierzeile label="Richtung" wert={f.richtung} />
        <Kopierzeile label="Laufzeit" wert={f.laufzeit} />
        <Kopierzeile label="Hebel" wert={`${zahl(f.hebel_von, 0)} bis ${zahl(f.hebel_bis, 0)}`} />
        <Kopierzeile label="KO-Schwelle (ca.)" wert={kursText(f.ko_schwelle, waehrung)} />
        <Kopierzeile label="Bezugsverhältnis" wert={zahl(f.bezugsverhaeltnis, 1)} />
        <Kopierzeile label="Spread" wert={`unter ${zahl(f.max_spread_pct, 0)} %`} />
      </div>
      <div className="mt-3">
        <Kopierzeile label="Alles als Text" wert="kopieren" kopierwert={filterText(f)} />
      </div>
      <p className="mt-2 text-[11px] text-gedimmt">{f.hinweis}</p>
    </Karte>
  );
}

function Ergebnis({ e, einsatz, eingefroren, tage }: { e: KnockoutErgebnis; einsatz: number; eingefroren: Eingefroren; tage: number }) {
  return (
    <>
      <Karte titel={`Ergebnis nach ${tage} Handelstagen`} rechts={<Kennzeichnung art="Modellwert" titel="Monte-Carlo-Simulation, keine Prognose" />}>
        <p className="mb-3 text-xs text-text2">
          Verwendeter Kurs: <span className="zahl font-semibold text-text">{kursText(eingefroren.kurs, eingefroren.waehrung)}</span> (eingefroren um {uhrzeit(eingefroren.zeit)}, {eingefroren.quelle}) ·
          KO-Schwelle {kursText(e.ko_schwelle, eingefroren.waehrung)}
        </p>
        <div className="grid grid-cols-3 gap-x-2 gap-y-4">
          <Kennzahl label="P(KO)" wert={anteil(e.p_ko)} farbe="text-kritisch-text" />
          <Kennzahl label="P(Gewinn)" wert={anteil(e.p_gewinn)} />
          <Kennzahl label="P(Verdopplung)" wert={anteil(e.p_verdopplung)} />
          <Kennzahl klein label="Median" wert={eur(e.median)} />
          <Kennzahl klein label="Bestes Viertel ab" wert={eur(e.top25)} />
          <Kennzahl klein label="Bestes Zehntel ab" wert={eur(e.top10)} />
        </div>
        <p className="mt-3 text-xs text-text2">
          Erwartungswert {eur(e.erwartung)} bei {eur(einsatz)} Einsatz · {zahl(e.n, 0)} Pfade, Seed {e.seed}
          {e.gap_sd > 0 && ` · Sprung über Nacht mit ${pct(e.gap_sd * 100, 0)} Standardabweichung`}
        </p>
        {e.histogramm && (
          <div className="mt-4">
            <h3 className="mb-1 text-xs font-semibold text-text2">Verteilung der Endwerte</h3>
            <Histogramm klassen={e.histogramm} einsatz={einsatz} />
          </div>
        )}
      </Karte>
      <Meldung art={e.hebel_regel.ok ? "gut" : "warn"}>
        <span className="font-semibold">Empfohlener Maximalhebel: {e.max_hebel}.</span> {e.hebel_regel.begruendung}
      </Meldung>
      <FilterKarte f={e.filter} waehrung={eingefroren.waehrung} />
    </>
  );
}

function KnockoutRechner() {
  const watchlist = useQuery({ queryKey: ["watchlist"], queryFn: Api.watchlist });
  const [gewaehlt, setGewaehlt] = useState("");
  const symbol = gewaehlt || watchlist.data?.[0]?.symbol || "";
  return (
    <div className="space-y-4">
      <Auswahl label="Aktie (Watchlist)" wert={symbol} onChange={setGewaehlt} optionen={(watchlist.data ?? []).map((w) => ({ wert: w.symbol, text: `${w.name} (${w.symbol})` }))} />
      {/* key: beim Wechsel der Aktie beginnt der Rechner frisch (Kurs, Volatilität, Ergebnis) */}
      {symbol && <SymbolRechner key={symbol} symbol={symbol} />}
    </div>
  );
}

function SymbolRechner({ symbol }: { symbol: string }) {
  const [hebel, setHebel] = useState(8);
  const [einsatz, setEinsatz] = useState(100);
  const [tage, setTage] = useState(10);
  const [richtung, setRichtung] = useState<Richtung>("long");
  const [zahlen, setZahlen] = useState(false);
  const [sigmaEigen, setSigmaEigen] = useState<string | null>(null);
  const [kursText_, setKursText] = useState("");
  const [eingefroren, setEingefroren] = useState<Eingefroren | null>(null);

  const live = useKurs(symbol);
  const quote = useQuery({ queryKey: ["quote", symbol], queryFn: () => Api.quote(symbol), retry: false });
  const vol = useQuery({ queryKey: ["vol", symbol], queryFn: () => Api.vol(symbol), retry: false, staleTime: 3600_000 });
  const sim = useMutation({ mutationFn: Api.simKnockout });
  const kurs = live ?? quote.data;
  const waehrung = symbol.endsWith(".DE") ? "EUR" : "USD";
  const sigmaText = sigmaEigen ?? (vol.data ? zahl(vol.data.sigma_vorschlag * 100, 0) : "");
  const sigma = parseZahl(sigmaText);
  const manuell = parseZahl(kursText_);
  const startKurs = manuell ?? (kurs && !kurs.schlusskurs ? kurs.kurs : null);

  const starten = () => {
    if (!startKurs || !sigma) return;
    const frost: Eingefroren = manuell
      ? { kurs: manuell, quelle: "eigene Eingabe (Annahme)", zeit: new Date().toISOString(), waehrung }
      : { kurs: kurs!.kurs, quelle: `${kurs!.quelle}, ${kurs!.etikett}`, zeit: kurs!.zeitstempel, waehrung };
    setEingefroren(frost);
    sim.mutate({ symbol, kurs: frost.kurs, sigma: sigma / 100, hebel, tage, einsatz, richtung, zahlen_ueber_nacht: zahlen });
  };

  return (
    <div className="space-y-4">
      <Karte>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="mb-1 text-xs text-text2">Aktueller Kurs</div>
              <LiveKurs symbol={symbol} start={quote.data} gross />
              {quote.isError && !kurs && <p className="text-xs text-warn">Kein Kurs verfügbar – bitte unten eintragen.</p>}
            </div>
            <div>
              <div className="mb-1 flex items-center gap-1.5 text-xs text-text2">Volatilität p. a. <Kennzeichnung art="Modellwert" /></div>
              {vol.data ? (
                <>
                  <div className="zahl text-2xl font-semibold">{pct(vol.data.sigma_vorschlag * 100, 0)}</div>
                  <div className="text-[11px] text-gedimmt">
                    20 T: {pct(vol.data.vol20 * 100, 0)} · 60 T: {vol.data.vol60 ? pct(vol.data.vol60 * 100, 0) : "–"} · {vol.data.quelle}, Stand {datum(vol.data.stand)}
                  </div>
                </>
              ) : (
                <div className="text-sm text-gedimmt">{vol.isLoading ? "lädt …" : "nicht verfügbar – bitte eintragen"}</div>
              )}
            </div>
          </div>
          {vol.data?.naechste_quartalszahlen && (
            <Meldung art="warn">Quartalszahlen am {datum(vol.data.naechste_quartalszahlen)} eingetragen – Schalter „Zahlen über Nacht“ prüfen.</Meldung>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Feld label="Volatilität für die Simulation (%)" inputMode="decimal" value={sigmaText} onChange={(e) => setSigmaEigen(e.target.value)} hinweis="Annahme, änderbar" />
            <Feld label={`Kurs überschreiben (${waehrung === "USD" ? "$" : "€"})`} inputMode="decimal" value={kursText_} onChange={(e) => setKursText(e.target.value)} placeholder="Live-Kurs" hinweis="leer = Live-Kurs" />
          </div>
          <Segmente label="Richtung" wert={richtung} onChange={setRichtung} optionen={[{ wert: "long", text: "Long (steigt)" }, { wert: "short", text: "Short (fällt)" }]} />
          <Regler label="Hebel" wert={hebel} min={2} max={30} anzeige={`${hebel}×`} onChange={setHebel} />
          <Regler label="Einsatz" wert={einsatz} min={10} max={250} schritt={10} anzeige={eur(einsatz)} onChange={setEinsatz} />
          <Regler label="Haltedauer" wert={tage} min={1} max={20} anzeige={`${tage} Handelstag${tage === 1 ? "" : "e"}`} onChange={setTage} />
          <Schalter label="Zahlen über Nacht" hinweis="Quartalszahlen in der Haltedauer: Kurssprung zum Start einrechnen" an={zahlen} onChange={setZahlen} />
          <Knopf art="primaer" className="w-full" disabled={!startKurs || !sigma || sim.isPending} onClick={starten}>
            {sim.isPending ? "Simulation läuft …" : "Simulation starten"}
          </Knopf>
          {!startKurs && <p className="text-xs text-gedimmt">Ohne Kurs keine Simulation: Live-Kurs abwarten oder Kurs eintragen.</p>}
        </div>
      </Karte>
      {sim.isError && <Meldung art="fehler">Simulation fehlgeschlagen: {sim.error.message}</Meldung>}
      {sim.data && eingefroren && <Ergebnis e={sim.data} einsatz={einsatz} eingefroren={eingefroren} tage={tage} />}
    </div>
  );
}

function OptionsscheinCheck() {
  const [f, setF] = useState({ kurs: "", basispreis: "", tage: "90", sigma: "40", preis: "", bv: "0,1", fx: "1" });
  const [typ, setTyp] = useState<"call" | "put">("call");
  const sim = useMutation<OptionsscheinErgebnis, Error, Record<string, unknown>>({ mutationFn: Api.simOptionsschein });
  const setze = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const z = { kurs: parseZahl(f.kurs), basispreis: parseZahl(f.basispreis), tage: parseZahl(f.tage), sigma: parseZahl(f.sigma), preis: parseZahl(f.preis), bv: parseZahl(f.bv), fx: parseZahl(f.fx) };
  const gueltig = z.kurs && z.basispreis && z.tage && z.sigma && z.bv && z.fx;
  const e = sim.data;
  return (
    <div className="space-y-4">
      <Karte>
        <div className="space-y-3">
          <Segmente label="Typ" wert={typ} onChange={setTyp} optionen={[{ wert: "call", text: "Call" }, { wert: "put", text: "Put" }]} />
          <div className="grid grid-cols-2 gap-3">
            <Feld label="Kurs Basiswert" required inputMode="decimal" value={f.kurs} onChange={setze("kurs")} />
            <Feld label="Basispreis" required inputMode="decimal" value={f.basispreis} onChange={setze("basispreis")} />
            <Feld label="Restlaufzeit (Tage)" required inputMode="numeric" value={f.tage} onChange={setze("tage")} />
            <Feld label="Volatilität (%)" required inputMode="decimal" value={f.sigma} onChange={setze("sigma")} hinweis="Annahme" />
            <Feld label="Briefkurs Schein (€)" inputMode="decimal" value={f.preis} onChange={setze("preis")} hinweis="leer = fairer Preis" />
            <Feld label="Bezugsverhältnis" required inputMode="decimal" value={f.bv} onChange={setze("bv")} />
            <Feld label="EUR/USD" inputMode="decimal" value={f.fx} onChange={setze("fx")} hinweis="1 bei Euro-Basiswert" />
          </div>
          <Knopf art="primaer" className="w-full" disabled={!gueltig || sim.isPending}
            onClick={() => sim.mutate({ kurs: z.kurs, basispreis: z.basispreis, tage: Math.round(z.tage!), sigma: z.sigma! / 100, typ, bezugsverhaeltnis: z.bv, preis: z.preis, wechselkurs: z.fx })}>
            Optionsschein prüfen
          </Knopf>
        </div>
      </Karte>
      {sim.isError && <Meldung art="fehler">{sim.error.message}</Meldung>}
      {e && (
        <Karte titel="Black-Scholes-Kennzahlen" rechts={<Kennzeichnung art="Modellwert" titel="Europäisch, ohne Dividenden, risikoneutrale Wahrscheinlichkeiten" />}>
          <div className="grid grid-cols-2 gap-x-3 gap-y-4">
            <Kennzahl label="Fairer Preis" wert={`${zahl(e.fairer_preis, 3)} €`} />
            <Kennzahl label="Omega (Hebel)" wert={zahl(e.omega, 1)} />
            <Kennzahl label="Break-even" wert={zahl(e.break_even)} />
            <Kennzahl label="P(im Geld)" wert={anteil(e.p_im_geld)} />
            <Kennzahl label="P(über Break-even)" wert={anteil(e.p_ueber_break_even)} />
            <Kennzahl label="Zeitwertverlust / Woche" wert={`${zahl(e.zeitwertverlust_woche, 3)} €`} farbe="text-kritisch-text" />
          </div>
          {e.aufgeld_zum_fairen_preis_pct !== null && z.preis && (
            <p className="mt-3 text-sm text-text2">
              Der Briefkurs liegt {pct(e.aufgeld_zum_fairen_preis_pct, 1, true)} gegenüber dem fairen Preis. Zeitwert {zahl(e.zeitwert, 3)} €, innerer Wert {zahl(e.innerer_wert, 3)} €.
            </p>
          )}
        </Karte>
      )}
    </div>
  );
}

export default function Rechner() {
  const [reiter, setReiter] = useState<"ko" | "os">("ko");
  return (
    <div className="space-y-4">
      <Seitentitel>Rechner</Seitentitel>
      <Segmente label="Rechner" wert={reiter} onChange={setReiter} optionen={[{ wert: "ko", text: "Knock-out" }, { wert: "os", text: "Optionsschein-Check" }]} />
      {reiter === "ko" ? <KnockoutRechner /> : <OptionsscheinCheck />}
    </div>
  );
}
