import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Api } from "../api/client";
import type { RegelCheck, TradeNeu, TradeTyp } from "../api/types";
import { eur, heuteIso, parseZahl } from "../lib/format";
import { Auswahl, Feld, Knopf, Meldung, Regelliste } from "./ui";

export interface TradeVorgabe {
  wertpapier?: string;
  symbol?: string;
  typ?: TradeTyp;
  einsatz?: number;
}

type Felder = Record<"wertpapier" | "wkn" | "symbol" | "stueck" | "kaufkurs" | "ko" | "bv" | "prognose" | "ziel" | "stop" | "these" | "gebuehren" | "datum", string>;

/** Formular zum Erfassen eines Trades. Prüft Pflichtfelder und zeigt vor dem Speichern
 *  die Größenregeln für den geplanten Einsatz. */
export function TradeFormular({ vorgabe, onSpeichern, onAbbrechen, laeuft, fehler }: {
  vorgabe?: TradeVorgabe;
  onSpeichern: (t: Partial<TradeNeu>) => void;
  onAbbrechen: () => void;
  laeuft: boolean;
  fehler?: string | null;
}) {
  const watchlist = useQuery({ queryKey: ["watchlist"], queryFn: Api.watchlist });
  const [typ, setTyp] = useState<TradeTyp>(vorgabe?.typ ?? "ko_long");
  const [f, setF] = useState<Felder>({
    wertpapier: vorgabe?.wertpapier ?? "", wkn: "", symbol: vorgabe?.symbol ?? "", stueck: "", kaufkurs: "", ko: "", bv: "0,1",
    prognose: "", ziel: "", stop: "", these: "", gebuehren: "0,99", datum: heuteIso(),
  });
  const [gezeigt, setGezeigt] = useState(false);
  const [check, setCheck] = useState<RegelCheck | null>(null);
  const setze = (k: keyof Felder) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setF({ ...f, [k]: e.target.value });
    setCheck(null);
  };
  const istKo = typ !== "aktie";
  const z = { stueck: parseZahl(f.stueck), kaufkurs: parseZahl(f.kaufkurs), ko: parseZahl(f.ko), bv: parseZahl(f.bv), prognose: parseZahl(f.prognose), ziel: parseZahl(f.ziel), stop: parseZahl(f.stop), gebuehren: parseZahl(f.gebuehren) };
  const einsatz = z.stueck && z.kaufkurs ? z.stueck * z.kaufkurs : null;

  const fehlerJe: Partial<Record<keyof Felder, string>> = {};
  if (!f.wertpapier.trim()) fehlerJe.wertpapier = "Pflichtfeld";
  if (!f.symbol.trim()) fehlerJe.symbol = "Pflichtfeld";
  if (!f.datum) fehlerJe.datum = "Pflichtfeld";
  if (!z.stueck || z.stueck <= 0) fehlerJe.stueck = "Zahl größer 0";
  if (!z.kaufkurs || z.kaufkurs <= 0) fehlerJe.kaufkurs = "Zahl größer 0";
  if (istKo && (!z.ko || z.ko <= 0)) fehlerJe.ko = "Pflichtfeld bei Knock-outs";
  if (istKo && (!z.bv || z.bv <= 0)) fehlerJe.bv = "Pflichtfeld bei Knock-outs";
  if (z.prognose !== null && (z.prognose < 0 || z.prognose > 100)) fehlerJe.prognose = "0 bis 100";
  const gueltig = Object.keys(fehlerJe).length === 0;
  const zeige = (k: keyof Felder) => (gezeigt ? fehlerJe[k] : undefined);

  const daten = (): Partial<TradeNeu> => ({
    datum_kauf: f.datum, wertpapier: f.wertpapier.trim(), wkn: f.wkn.trim() || null, typ, symbol: f.symbol.trim().toUpperCase(),
    basiswert: watchlist.data?.find((w) => w.symbol === f.symbol.trim().toUpperCase())?.name ?? null,
    stueck: z.stueck!, kaufkurs: z.kaufkurs!, ko_schwelle: istKo ? z.ko : null, bezugsverhaeltnis: istKo ? z.bv : null,
    prognose_p_gewinn: z.prognose !== null ? z.prognose / 100 : null, ziel: z.ziel, stop: z.stop,
    these: f.these.trim() || null, gebuehren: z.gebuehren ?? 0,
  });

  const absenden = async () => {
    setGezeigt(true);
    if (!gueltig || !einsatz) return;
    if (!check) {
      try {
        const c = await Api.regelCheck({ typ, einsatz, symbol: f.symbol.trim().toUpperCase() });
        setCheck(c);
        if (!c.ok) return; // Verstöße erst zeigen, zweiter Klick speichert trotzdem
      } catch {
        /* Regelprüfung nicht erreichbar: Speichern nicht blockieren */
      }
    }
    onSpeichern(daten());
  };

  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void absenden(); }} noValidate>
      <Auswahl label="Typ" wert={typ} onChange={(t) => { setTyp(t); setCheck(null); }} optionen={[{ wert: "ko_long", text: "Knock-out Long" }, { wert: "ko_short", text: "Knock-out Short" }, { wert: "aktie", text: "Aktie" }]} />
      <Feld label="Wertpapier (Name)" required value={f.wertpapier} onChange={setze("wertpapier")} fehler={zeige("wertpapier")} placeholder="z. B. Turbo Long Infineon" />
      <div className="grid grid-cols-2 gap-3">
        <Feld label="Symbol Basiswert" required value={f.symbol} onChange={setze("symbol")} fehler={zeige("symbol")} list="sd-symbole" placeholder="IFX.DE / NVDA" autoCapitalize="characters" />
        <Feld label="WKN (optional)" value={f.wkn} onChange={setze("wkn")} hinweis="aus dem Broker übernehmen" />
        <datalist id="sd-symbole">{(watchlist.data ?? []).map((w) => <option key={w.symbol} value={w.symbol}>{w.name}</option>)}</datalist>
        <Feld label="Kaufdatum" required type="date" value={f.datum} onChange={setze("datum")} fehler={zeige("datum")} />
        <Feld label="Gebühren (€)" inputMode="decimal" value={f.gebuehren} onChange={setze("gebuehren")} />
        <Feld label="Stück" required inputMode="decimal" value={f.stueck} onChange={setze("stueck")} fehler={zeige("stueck")} />
        <Feld label="Kaufkurs (€)" required inputMode="decimal" value={f.kaufkurs} onChange={setze("kaufkurs")} fehler={zeige("kaufkurs")} hinweis={einsatz ? `Einsatz ${eur(einsatz)}` : undefined} />
        {istKo && <Feld label="KO-Schwelle (Basiswert)" required inputMode="decimal" value={f.ko} onChange={setze("ko")} fehler={zeige("ko")} />}
        {istKo && <Feld label="Bezugsverhältnis" required inputMode="decimal" value={f.bv} onChange={setze("bv")} fehler={zeige("bv")} />}
        <Feld label="Ziel (Kurs Basiswert)" inputMode="decimal" value={f.ziel} onChange={setze("ziel")} />
        <Feld label="Stop (Kurs Basiswert)" inputMode="decimal" value={f.stop} onChange={setze("stop")} />
      </div>
      <Feld label="Prognose P(Gewinn) in %" inputMode="decimal" value={f.prognose} onChange={setze("prognose")} fehler={zeige("prognose")} hinweis="aus dem Rechner – wird später mit dem Ergebnis verglichen" />
      <Feld label="These" value={f.these} onChange={setze("these")} placeholder="Warum dieser Trade?" />
      {vorgabe?.einsatz && einsatz && Math.abs(einsatz - vorgabe.einsatz) > vorgabe.einsatz * 0.15 && (
        <Meldung art="warn">Geplant waren {eur(vorgabe.einsatz)} Einsatz, eingetragen sind {eur(einsatz)}.</Meldung>
      )}
      {check && (
        <div className="rounded-xl border border-linie bg-erhoben p-3">
          <p className="mb-2 text-sm font-semibold">{check.ok ? "Regelprüfung bestanden" : "Regelverstoß – nochmal tippen, um trotzdem zu speichern"}</p>
          <Regelliste regeln={check.regeln} />
        </div>
      )}
      {gezeigt && !gueltig && <Meldung art="fehler">Bitte die markierten Pflichtfelder ausfüllen.</Meldung>}
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      <div className="flex gap-2">
        <Knopf onClick={onAbbrechen} className="flex-1">Abbrechen</Knopf>
        <Knopf art={check && !check.ok ? "gefahr" : "primaer"} type="submit" disabled={laeuft} className="flex-1">
          {check && !check.ok ? "Trotzdem speichern" : "Trade speichern"}
        </Knopf>
      </div>
    </form>
  );
}
