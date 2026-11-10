import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Api } from "../api/client";
import type { PlanEintrag, TradeTyp } from "../api/types";
import { LiveKurs } from "../components/LiveKurs";
import { TradeFormular } from "../components/TradeFormular";
import { Auswahl, Feld, Karte, Knopf, Laden, Leer, Meldung, Seitentitel } from "../components/ui";
import { eur, parseZahl, TYP_NAME } from "../lib/format";

const STATUS: { wert: PlanEintrag["status"]; text: string }[] = [
  { wert: "offen", text: "offen" }, { wert: "signal", text: "Signal" }, { wert: "gekauft", text: "gekauft" }, { wert: "verworfen", text: "verworfen" },
];
const STATUS_STIL: Record<PlanEintrag["status"], string> = {
  offen: "border-linie text-text2", signal: "border-warn/60 text-warn", gekauft: "border-gut/60 text-gut-text", verworfen: "border-linie text-gedimmt line-through",
};

function kalenderwoche(): string {
  const d = new Date();
  const tag = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - tag + 3);
  const jahr = d.getFullYear();
  const ersterDo = new Date(jahr, 0, 4);
  const kw = 1 + Math.round(((d.getTime() - ersterDo.getTime()) / 86400000 - 3 + ((ersterDo.getDay() + 6) % 7)) / 7);
  return `${jahr}-KW${String(kw).padStart(2, "0")}`;
}

function PlanKarte({ p }: { p: PlanEintrag }) {
  const qc = useQueryClient();
  const [uebernehmen, setUebernehmen] = useState(false);
  const neu = () => qc.invalidateQueries();
  const aendern = useMutation({ mutationFn: (status: PlanEintrag["status"]) => Api.planAendern(p.id, { status }), onSuccess: neu });
  const loeschen = useMutation({ mutationFn: () => Api.planLoeschen(p.id), onSuccess: neu });
  const trade = useMutation({ mutationFn: (t: Parameters<typeof Api.planUebernehmen>[1]) => Api.planUebernehmen(p.id, t), onSuccess: () => { void neu(); setUebernehmen(false); } });
  const zeile = (name: string, wert: string | null) => wert ? (<div className="flex gap-2 text-sm"><dt className="w-28 shrink-0 text-text2">{name}</dt><dd className="min-w-0">{wert}</dd></div>) : null;
  return (
    <article className="rounded-2xl border border-linie bg-karte p-4">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-semibold">{p.position}</h3>
          <p className="text-xs text-text2">{p.woche} · {TYP_NAME[p.typ]} · Einsatz {eur(p.einsatz)}</p>
        </div>
        <span className={`shrink-0 rounded border px-1.5 py-0.5 text-xs ${STATUS_STIL[p.status]}`}>{STATUS.find((s) => s.wert === p.status)?.text}</span>
      </header>
      {p.symbol && <div className="mt-2"><LiveKurs symbol={p.symbol} /></div>}
      <dl className="mt-2 space-y-1">
        {zeile("Kaufzeitpunkt", p.kaufzeitpunkt)}
        {zeile("Kaufbedingung", p.kaufbedingung)}
        {zeile("Filterwerte", p.filter)}
        {zeile("Ziel", p.ziel)}
        {zeile("Ausstieg", p.ausstieg)}
      </dl>
      {uebernehmen ? (
        <div className="mt-3 border-t border-linie pt-3">
          <TradeFormular vorgabe={{ wertpapier: p.position, symbol: p.symbol ?? "", typ: p.typ, einsatz: p.einsatz }} onSpeichern={(t) => trade.mutate(t)} onAbbrechen={() => setUebernehmen(false)} laeuft={trade.isPending} fehler={trade.error?.message} />
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Auswahl label="Status" wert={p.status} onChange={(s) => aendern.mutate(s)} optionen={STATUS} className="w-32" />
          {p.status !== "gekauft" && p.status !== "verworfen" && <Knopf art="primaer" onClick={() => setUebernehmen(true)}>Als Trade übernehmen</Knopf>}
          <Knopf art="leise" klein onClick={() => { if (window.confirm(`„${p.position}“ aus dem Plan löschen?`)) loeschen.mutate(); }}>Löschen</Knopf>
        </div>
      )}
    </article>
  );
}

function NeuerEintrag({ fertig }: { fertig: () => void }) {
  const qc = useQueryClient();
  const [typ, setTyp] = useState<TradeTyp>("ko_long");
  const [f, setF] = useState({ woche: kalenderwoche(), position: "", symbol: "", einsatz: "100", kaufzeitpunkt: "", kaufbedingung: "", filter: "", ziel: "", ausstieg: "" });
  const setze = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const einsatz = parseZahl(f.einsatz);
  const m = useMutation({
    mutationFn: () => Api.planNeu({ ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.trim() || null])), typ, einsatz: einsatz ?? 100, woche: f.woche, position: f.position.trim() }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["plan"] }); fertig(); },
  });
  return (
    <Karte titel="Neuer Plan-Eintrag">
      <div className="space-y-3">
        <Feld label="Position" required value={f.position} onChange={setze("position")} placeholder="z. B. Turbo Long Infineon" />
        <div className="grid grid-cols-2 gap-3">
          <Feld label="Woche" required value={f.woche} onChange={setze("woche")} />
          <Feld label="Symbol" value={f.symbol} onChange={setze("symbol")} placeholder="IFX.DE" hinweis="für den Live-Kurs" />
          <Auswahl label="Typ" wert={typ} onChange={setTyp} optionen={[{ wert: "ko_long", text: "Knock-out Long" }, { wert: "ko_short", text: "Knock-out Short" }, { wert: "aktie", text: "Aktie" }]} />
          <Feld label="Einsatz (€)" inputMode="decimal" value={f.einsatz} onChange={setze("einsatz")} />
        </div>
        <Feld label="Kaufzeitpunkt" value={f.kaufzeitpunkt} onChange={setze("kaufzeitpunkt")} placeholder="z. B. Dienstag nach 9:30" />
        <Feld label="Kaufbedingung" value={f.kaufbedingung} onChange={setze("kaufbedingung")} placeholder="z. B. Kurs über 40 €" />
        <Feld label="Filterwerte" value={f.filter} onChange={setze("filter")} hinweis="aus dem Rechner kopieren („Alles als Text“)" />
        <Feld label="Ziel" value={f.ziel} onChange={setze("ziel")} />
        <Feld label="Ausstieg" value={f.ausstieg} onChange={setze("ausstieg")} placeholder="z. B. −50 % oder 10 Handelstage" />
        {m.isError && <Meldung art="fehler">{m.error.message}</Meldung>}
        <div className="flex gap-2">
          <Knopf onClick={fertig} className="flex-1">Abbrechen</Knopf>
          <Knopf art="primaer" disabled={!f.position.trim() || !f.woche.trim() || !einsatz || m.isPending} onClick={() => m.mutate()} className="flex-1">Speichern</Knopf>
        </div>
      </div>
    </Karte>
  );
}

export default function Plan() {
  const [neu, setNeu] = useState(false);
  const plan = useQuery({ queryKey: ["plan"], queryFn: Api.plan });
  return (
    <div className="space-y-4">
      <Seitentitel rechts={!neu && <Knopf klein art="primaer" onClick={() => setNeu(true)}>+ Eintrag</Knopf>}>Wochenplan</Seitentitel>
      {neu && <NeuerEintrag fertig={() => setNeu(false)} />}
      {plan.isLoading ? <Laden /> : plan.data?.length ? plan.data.map((p) => <PlanKarte key={p.id} p={p} />) : <Leer>Noch kein Plan. Lege Positionen für die Woche an.</Leer>}
    </div>
  );
}
