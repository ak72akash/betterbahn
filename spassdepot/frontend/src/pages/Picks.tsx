import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Api } from "../api/client";
import { useKurs } from "../api/live";
import type { PickPruefung, Richtung } from "../api/types";
import { Auswahl, Feld, Karte, Kennzahl, Kennzeichnung, Knopf, Laden, Leer, Meldung, Regelliste, Segmente, Seitentitel } from "../components/ui";
import { anteil, datum, heuteIso, kursText, parseZahl, pct, vzFarbe, zahl } from "../lib/format";

function NeuerPick({ fertig }: { fertig: () => void }) {
  const qc = useQueryClient();
  const watchlist = useQuery({ queryKey: ["watchlist"], queryFn: Api.watchlist });
  const [symbol, setSymbol] = useState("");
  const [richtung, setRichtung] = useState<Richtung>("long");
  const [f, setF] = useState({ kurs: "", ziel: "", stop: "", katalysator: "", sigma: "" });
  const [pruefung, setPruefung] = useState<PickPruefung | null>(null);
  const live = useKurs(symbol);
  const setze = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => { setF({ ...f, [k]: e.target.value }); setPruefung(null); };
  const eintrag = watchlist.data?.find((w) => w.symbol === symbol);
  const kurs = parseZahl(f.kurs) ?? (live && !live.schlusskurs ? live.kurs : null);
  const ziel = parseZahl(f.ziel);
  const stop = parseZahl(f.stop);
  const sigma = parseZahl(f.sigma);
  const m = useMutation({
    mutationFn: (trotzdem: boolean) => Api.pickNeu({
      datum: heuteIso(), aktie: eintrag?.name ?? symbol, symbol, richtung, kurs, ziel, stop,
      quelle: parseZahl(f.kurs) ? "eigene Eingabe" : live?.quelle, katalysator: f.katalysator.trim() || null,
      sigma: sigma ? sigma / 100 : null, trotzdem_speichern: trotzdem,
    }),
    onSuccess: (p) => {
      setPruefung(p);
      if (p.gespeichert) { void qc.invalidateQueries({ queryKey: ["picks"] }); if (p.ok) fertig(); }
    },
  });
  return (
    <Karte titel="Neuer Pick">
      <div className="space-y-3">
        <Auswahl label="Aktie" wert={symbol} onChange={(s) => { setSymbol(s); setPruefung(null); }} optionen={[{ wert: "", text: "– wählen –" }, ...(watchlist.data ?? []).map((w) => ({ wert: w.symbol, text: `${w.name} (${w.symbol})` }))]} />
        <Segmente label="Richtung" wert={richtung} onChange={(r) => { setRichtung(r); setPruefung(null); }} optionen={[{ wert: "long", text: "Long" }, { wert: "short", text: "Short" }]} />
        <div className="grid grid-cols-3 gap-3">
          <Feld label="Kurs" inputMode="decimal" value={f.kurs} onChange={setze("kurs")} placeholder={live ? zahl(live.kurs) : ""} hinweis={live ? `leer = ${live.quelle}` : undefined} />
          <Feld label="Ziel" required inputMode="decimal" value={f.ziel} onChange={setze("ziel")} />
          <Feld label="Stop" required inputMode="decimal" value={f.stop} onChange={setze("stop")} />
        </div>
        <Feld label="Katalysator" value={f.katalysator} onChange={setze("katalysator")} placeholder="Warum jetzt?" />
        <Feld label="Volatilität (%)" inputMode="decimal" value={f.sigma} onChange={setze("sigma")} hinweis="leer = realisierte Volatilität aus dem Kursverlauf" />
        {pruefung && (
          <div className="space-y-3 rounded-xl border border-linie bg-erhoben p-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">{pruefung.ok ? "Qualitätsschwelle bestanden" : "Qualitätsschwelle nicht bestanden"}</p>
              <Kennzeichnung art="Modellwert" />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Kennzahl klein label="P(Ziel zuerst)" wert={anteil(pruefung.p_ziel)} />
              <Kennzahl klein label="P(Stop zuerst)" wert={anteil(pruefung.p_stop)} />
              <Kennzahl klein label="P(offen)" wert={anteil(pruefung.p_offen)} />
            </div>
            <Regelliste regeln={pruefung.regeln} />
            <p className="text-[11px] text-gedimmt">Volatilität {pct(pruefung.sigma * 100, 0)} ({pruefung.sigma_quelle}), 10 Handelstage.</p>
            {pruefung.gespeichert && !pruefung.ok && <Meldung art="info">Trotz Verstoß gespeichert.</Meldung>}
          </div>
        )}
        {m.isError && <Meldung art="fehler">{m.error.message}</Meldung>}
        <div className="flex gap-2">
          <Knopf onClick={fertig} className="flex-1">{pruefung?.gespeichert ? "Schließen" : "Abbrechen"}</Knopf>
          {pruefung && !pruefung.ok && !pruefung.gespeichert ? (
            <Knopf art="gefahr" disabled={m.isPending} onClick={() => m.mutate(true)} className="flex-1">Trotzdem speichern</Knopf>
          ) : !pruefung?.gespeichert ? (
            <Knopf art="primaer" disabled={!symbol || !kurs || !ziel || !stop || m.isPending} onClick={() => m.mutate(false)} className="flex-1">Prüfen und speichern</Knopf>
          ) : null}
        </div>
      </div>
    </Karte>
  );
}

export default function Picks() {
  const qc = useQueryClient();
  const [neu, setNeu] = useState(false);
  const picks = useQuery({ queryKey: ["picks"], queryFn: Api.picks });
  const bewerten = useMutation({ mutationFn: Api.picksBewerten, onSuccess: () => qc.invalidateQueries({ queryKey: ["picks"] }) });
  const loeschen = useMutation({ mutationFn: Api.pickLoeschen, onSuccess: () => qc.invalidateQueries({ queryKey: ["picks"] }) });
  const erg = (x: number | null) => (x === null ? <span className="text-gedimmt">offen</span> : <span className={vzFarbe(x)}>{pct(x, 1, true)}</span>);
  return (
    <div className="space-y-4">
      <Seitentitel rechts={!neu && <Knopf klein art="primaer" onClick={() => setNeu(true)}>+ Pick</Knopf>}>Picks</Seitentitel>
      {neu && <NeuerPick fertig={() => setNeu(false)} />}
      <Karte titel="Pick-Log" rechts={<Knopf klein art="leise" disabled={bewerten.isPending} onClick={() => bewerten.mutate()}>Ergebnisse nachtragen</Knopf>}>
        {bewerten.data && <p className="mb-2 text-xs text-text2">{bewerten.data.aktualisiert} Ergebnis(se) nachgetragen.</p>}
        {picks.isLoading ? <Laden /> : picks.data?.length ? (
          <ul className="divide-y divide-linie">
            {picks.data.map((p) => (
              <li key={p.id} className="py-3">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{p.aktie} <span className="text-xs font-normal text-text2">{p.richtung === "long" ? "Long" : "Short"} · {datum(p.datum)}</span></span>
                  <button type="button" className="text-xs text-gedimmt" aria-label={`Pick ${p.aktie} löschen`} onClick={() => { if (window.confirm("Pick löschen?")) loeschen.mutate(p.id); }}>✕</button>
                </div>
                <div className="zahl text-xs text-text2">
                  Kurs {kursText(p.kurs, p.symbol.endsWith(".DE") ? "EUR" : "USD")} ({p.quelle ?? "?"}) · Ziel {zahl(p.ziel)} · Stop {zahl(p.stop)} · P(Ziel vor Stop) {anteil(p.p_ziel_vor_stop, 0)}
                </div>
                {p.katalysator && <div className="text-xs text-text2">Katalysator: {p.katalysator}</div>}
                <div className="zahl mt-1 flex gap-4 text-sm">
                  <span>5 Tage: {erg(p.ergebnis_5t)}</span>
                  <span>10 Tage: {erg(p.ergebnis_10t)}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : <Leer>Noch keine Picks.</Leer>}
      </Karte>
    </div>
  );
}
