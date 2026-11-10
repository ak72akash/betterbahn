import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Api } from "../api/client";
import type { Trade } from "../api/types";
import { TradeFormular } from "../components/TradeFormular";
import { Feld, Karte, Knopf, Laden, Leer, Meldung, Segmente, Seitentitel } from "../components/ui";
import { anteil, datum, eur, eurVz, heuteIso, parseZahl, pct, TYP_NAME, vzFarbe, zahl } from "../lib/format";

function Schliessen({ t, fertig }: { t: Trade; fertig: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ datum: heuteIso(), kurs: "", stueck: zahl(t.stueck, 0), gebuehren: "0,99", lehre: "" });
  const kurs = parseZahl(f.kurs);
  const stueck = parseZahl(f.stueck);
  const m = useMutation({
    mutationFn: () => Api.tradeSchliessen(t.id, { datum_verkauf: f.datum, verkaufskurs: kurs, stueck: stueck !== t.stueck ? stueck : null, gebuehren: parseZahl(f.gebuehren) ?? 0, lehre: f.lehre.trim() || null }),
    onSuccess: () => { void qc.invalidateQueries(); fertig(); },
  });
  const gueltig = kurs !== null && kurs >= 0 && stueck !== null && stueck > 0 && stueck <= t.stueck && !!f.datum;
  return (
    <div className="mt-3 space-y-3 rounded-xl border border-linie bg-erhoben p-3">
      <div className="grid grid-cols-2 gap-3">
        <Feld label="Verkaufsdatum" required type="date" value={f.datum} onChange={(e) => setF({ ...f, datum: e.target.value })} />
        <Feld label="Verkaufskurs (€)" required inputMode="decimal" value={f.kurs} onChange={(e) => setF({ ...f, kurs: e.target.value })} hinweis="0 bei Knock-out" />
        <Feld label="Stück" required inputMode="decimal" value={f.stueck} onChange={(e) => setF({ ...f, stueck: e.target.value })} hinweis={`Bestand ${zahl(t.stueck, 0)} – weniger = Teilverkauf`} />
        <Feld label="Gebühren Verkauf (€)" inputMode="decimal" value={f.gebuehren} onChange={(e) => setF({ ...f, gebuehren: e.target.value })} />
      </div>
      <Feld label="Lehre aus dem Trade" value={f.lehre} onChange={(e) => setF({ ...f, lehre: e.target.value })} placeholder="Was nehme ich mit?" />
      {kurs !== null && stueck ? <p className={`zahl text-sm ${vzFarbe(kurs - t.kaufkurs)}`}>Ergebnis vor Gebühren: {eurVz((kurs - t.kaufkurs) * stueck)}</p> : null}
      {m.isError && <Meldung art="fehler">{m.error.message}</Meldung>}
      <div className="flex gap-2">
        <Knopf klein onClick={fertig} className="flex-1">Abbrechen</Knopf>
        <Knopf klein art="primaer" disabled={!gueltig || m.isPending} onClick={() => m.mutate()} className="flex-1">Verkauf buchen</Knopf>
      </div>
    </div>
  );
}

function TradeZeile({ t }: { t: Trade }) {
  const qc = useQueryClient();
  const [schliessen, setSchliessen] = useState(false);
  const loeschen = useMutation({ mutationFn: () => Api.tradeLoeschen(t.id), onSuccess: () => qc.invalidateQueries() });
  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-medium">{t.wertpapier}</div>
          <div className="text-xs text-text2">
            {TYP_NAME[t.typ]} · {t.symbol}{t.wkn ? ` · WKN ${t.wkn}` : ""} · {datum(t.datum_kauf)}{t.datum_verkauf ? ` → ${datum(t.datum_verkauf)}` : ""}
          </div>
          <div className="zahl text-xs text-text2">
            {zahl(t.stueck, 0)} Stück × {zahl(t.kaufkurs, t.kaufkurs < 5 ? 3 : 2)} € = {eur(t.einsatz)}
            {t.prognose_p_gewinn !== null && ` · Prognose ${anteil(t.prognose_p_gewinn, 0)}`}
          </div>
        </div>
        <div className="shrink-0 text-right">
          {t.offen ? (
            <span className="rounded border border-akzent/50 px-1.5 py-0.5 text-xs text-akzent">offen</span>
          ) : (
            <div className={`zahl font-semibold ${vzFarbe(t.ergebnis_eur)}`}>
              {eurVz(t.ergebnis_eur)}
              <div className="text-xs font-normal">{pct(t.ergebnis_pct, 0, true)}</div>
            </div>
          )}
        </div>
      </div>
      {t.these && <p className="mt-1 text-xs text-text2">These: {t.these}</p>}
      {t.lehre && <p className="mt-1 text-xs text-text2">Lehre: {t.lehre}</p>}
      {schliessen ? (
        <Schliessen t={t} fertig={() => setSchliessen(false)} />
      ) : (
        <div className="mt-2 flex gap-2">
          {t.offen && <Knopf klein onClick={() => setSchliessen(true)}>Schließen / Teilverkauf</Knopf>}
          <Knopf klein art="leise" onClick={() => { if (window.confirm(`„${t.wertpapier}“ wirklich löschen?`)) loeschen.mutate(); }}>Löschen</Knopf>
        </div>
      )}
    </li>
  );
}

export default function Journal() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"alle" | "offen" | "geschlossen">("offen");
  const [neu, setNeu] = useState(false);
  const trades = useQuery({ queryKey: ["trades", filter], queryFn: () => Api.trades(filter) });
  const anlegen = useMutation({ mutationFn: Api.tradeNeu, onSuccess: () => { void qc.invalidateQueries(); setNeu(false); } });
  return (
    <div className="space-y-4">
      <Seitentitel rechts={!neu && <Knopf klein art="primaer" onClick={() => { anlegen.reset(); setNeu(true); }}>+ Trade</Knopf>}>Journal</Seitentitel>
      {neu && (
        <Karte titel="Neuer Trade">
          <TradeFormular onSpeichern={(t) => anlegen.mutate(t)} onAbbrechen={() => setNeu(false)} laeuft={anlegen.isPending} fehler={anlegen.error?.message} />
        </Karte>
      )}
      <Segmente label="Filter" wert={filter} onChange={setFilter} optionen={[{ wert: "offen", text: "Offen" }, { wert: "geschlossen", text: "Geschlossen" }, { wert: "alle", text: "Alle" }]} />
      <Karte>
        {trades.isLoading ? <Laden /> : trades.data?.length ? (
          <ul className="divide-y divide-linie">{trades.data.map((t) => <TradeZeile key={t.id} t={t} />)}</ul>
        ) : <Leer>Keine Trades in dieser Ansicht.</Leer>}
      </Karte>
      <a href="/api/trades/export.csv" download className="block rounded-xl border border-linie bg-erhoben py-3 text-center text-sm font-medium">
        CSV-Export herunterladen
      </a>
    </div>
  );
}
