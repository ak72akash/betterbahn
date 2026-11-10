import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Api } from "../api/client";
import { useVerbindung } from "../api/live";
import type { Einstellung } from "../api/types";
import { LiveKurs } from "../components/LiveKurs";
import { Feld, Karte, Knopf, Laden, Leer, Meldung, Schalter, Seitentitel } from "../components/ui";
import { datum, datumZeit, heuteIso, parseZahl } from "../lib/format";
import { benachrichtigungenErlauben, benachrichtigungsStatus } from "../lib/benachrichtigung";

const ANTEILE = new Set(["max_hebel_anteil", "min_reserve_anteil", "pick_min_p_ziel", "earnings_gap_sd"]);
const VERSTECKT = new Set(["risk_off", "index_vortag_pct"]);

function Grenzwert({ e }: { e: Einstellung }) {
  const qc = useQueryClient();
  const alsText = (w: Einstellung["wert"]) => (typeof w === "number" ? String(ANTEILE.has(e.schluessel) ? Math.round(w * 1000) / 10 : w).replace(".", ",") : String(w));
  const [text, setText] = useState(alsText(e.wert));
  const m = useMutation({ mutationFn: (w: number | string) => Api.einstellungenSpeichern({ [e.schluessel]: w }), onSuccess: () => qc.invalidateQueries() });
  const speichern = () => {
    if (text === alsText(e.wert)) return;
    if (typeof e.wert === "string") return m.mutate(text.trim());
    const n = parseZahl(text);
    if (n === null) return setText(alsText(e.wert));
    m.mutate(ANTEILE.has(e.schluessel) ? n / 100 : n);
  };
  return (
    <Feld
      label={e.beschreibung + (ANTEILE.has(e.schluessel) ? " (%)" : "")}
      inputMode={typeof e.wert === "number" ? "decimal" : "text"}
      value={text}
      onChange={(ev) => setText(ev.target.value)}
      onBlur={speichern}
      fehler={m.error?.message}
      hinweis={e.wert !== e.vorgabe ? `Vorgabe: ${alsText(e.vorgabe)}` : undefined}
    />
  );
}

function Watchlist() {
  const qc = useQueryClient();
  const liste = useQuery({ queryKey: ["watchlist"], queryFn: Api.watchlist });
  const [f, setF] = useState({ symbol: "", name: "", branche: "" });
  const neu = useMutation({ mutationFn: () => Api.watchlistNeu({ symbol: f.symbol.trim(), name: f.name.trim(), branche: f.branche.trim() || null }), onSuccess: () => { setF({ symbol: "", name: "", branche: "" }); void qc.invalidateQueries({ queryKey: ["watchlist"] }); } });
  const weg = useMutation({ mutationFn: Api.watchlistLoeschen, onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }) });
  return (
    <Karte titel="Watchlist">
      <ul className="divide-y divide-linie">
        {(liste.data ?? []).map((w) => (
          <li key={w.id} className="flex items-center justify-between gap-2 py-2">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{w.name} <span className="text-xs font-normal text-text2">{w.symbol}{w.branche ? ` · ${w.branche}` : ""}</span></div>
              <LiveKurs symbol={w.symbol} />
            </div>
            <button type="button" className="min-h-9 px-2 text-gedimmt" aria-label={`${w.name} entfernen`} onClick={() => { if (window.confirm(`${w.name} von der Watchlist entfernen?`)) weg.mutate(w.id); }}>✕</button>
          </li>
        ))}
      </ul>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Feld label="Symbol" value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value })} placeholder="BMW.DE" />
        <Feld label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <Feld label="Branche" value={f.branche} onChange={(e) => setF({ ...f, branche: e.target.value })} />
      </div>
      <p className="mt-1 text-[11px] text-gedimmt">Xetra-Werte mit Endung .DE (IFX.DE), US-Werte ohne Endung (NVDA).</p>
      {neu.isError && <div className="mt-2"><Meldung art="fehler">{neu.error.message}</Meldung></div>}
      <Knopf klein className="mt-2" disabled={!f.symbol.trim() || !f.name.trim() || neu.isPending} onClick={() => neu.mutate()}>Hinzufügen</Knopf>
    </Karte>
  );
}

function Termine() {
  const qc = useQueryClient();
  const liste = useQuery({ queryKey: ["termine"], queryFn: Api.termine });
  const [f, setF] = useState({ datum: heuteIso(), symbol: "", art: "Quartalszahlen", notiz: "" });
  const neu = useMutation({ mutationFn: () => Api.terminNeu({ datum: f.datum, symbol: f.symbol.trim().toUpperCase() || null, art: f.art.trim(), notiz: f.notiz.trim() || null }), onSuccess: () => { setF({ ...f, symbol: "", notiz: "" }); void qc.invalidateQueries(); } });
  const weg = useMutation({ mutationFn: Api.terminLoeschen, onSuccess: () => qc.invalidateQueries() });
  return (
    <Karte titel="Termine und Notizen (manuell)">
      {liste.data?.length ? (
        <ul className="divide-y divide-linie">
          {liste.data.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <span className="min-w-0"><span className="zahl text-text2">{datum(t.datum)}</span> · {t.symbol ? `${t.symbol} · ` : ""}{t.art}{t.notiz ? <span className="block text-xs text-text2">{t.notiz}</span> : null}</span>
              <button type="button" className="min-h-9 px-2 text-gedimmt" aria-label="Termin löschen" onClick={() => weg.mutate(t.id)}>✕</button>
            </li>
          ))}
        </ul>
      ) : <Leer>Noch keine Termine.</Leer>}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Feld label="Datum" type="date" value={f.datum} onChange={(e) => setF({ ...f, datum: e.target.value })} />
        <Feld label="Symbol (optional)" value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value })} list="sd-symbole" />
        <Feld label="Art" value={f.art} onChange={(e) => setF({ ...f, art: e.target.value })} hinweis="„Quartalszahlen“ wird im Rechner erkannt" />
        <Feld label="Notiz" value={f.notiz} onChange={(e) => setF({ ...f, notiz: e.target.value })} />
      </div>
      <Knopf klein className="mt-2" disabled={!f.datum || !f.art.trim() || neu.isPending} onClick={() => neu.mutate()}>Termin speichern</Knopf>
    </Karte>
  );
}

function Anbieter() {
  const a = useQuery({ queryKey: ["anbieter"], queryFn: Api.anbieter, refetchInterval: 10000 });
  const verbindung = useVerbindung();
  if (!a.data) return <Karte titel="Anbieter-Status"><Laden /></Karte>;
  return (
    <Karte titel="Anbieter-Status">
      <p className="mb-2 text-xs text-text2">
        Reihenfolge: {a.data.reihenfolge.join(" → ")} · Live-Dienst {a.data.live_dienst ? "läuft" : "aus"} · Browser-Verbindung: {verbindung}
      </p>
      <ul className="divide-y divide-linie">
        {a.data.aktiv.map((p) => (
          <li key={p.name} className="py-2 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{p.name}{p.name === "demo" ? " (simulierte Kurse!)" : ""}</span>
              <span className="flex items-center gap-1.5 text-xs">
                <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${p.verbunden ? "bg-gut" : p.pausiert ? "bg-kritisch" : "bg-gedimmt"}`} />
                {p.verbunden ? "verbunden" : p.pausiert ? "pausiert nach Fehlern" : "getrennt"}
              </span>
            </div>
            <div className="zahl text-xs text-text2">
              {p.nur_schlusskurs ? "nur Tagesverläufe" : p.stream ? "Stream + Abfrage" : "Abfrage"} · heute {p.abfragen_heute} Abfragen
              {p.limit_tag !== null ? ` · verbleibend ${p.verbleibend_heute} von ${p.limit_tag}` : " · kein Tageslimit"}
              {p.letzter_erfolg ? ` · zuletzt ${datumZeit(p.letzter_erfolg)}` : ""}
            </div>
            {p.letzter_fehler && <div className="break-words text-xs text-warn">{p.letzter_fehler}</div>}
          </li>
        ))}
        {a.data.nicht_konfiguriert.map((p) => (
          <li key={p.name} className="py-2 text-sm text-gedimmt">{p.name}: nicht aktiv ({p.grund})</li>
        ))}
      </ul>
    </Karte>
  );
}

export default function Einstellungen({ abmelden }: { abmelden?: () => void }) {
  const qc = useQueryClient();
  const e = useQuery({ queryKey: ["einstellungen"], queryFn: Api.einstellungen });
  const [meldung, setMeldung] = useState(benachrichtigungsStatus());
  const riskOff = useMutation({ mutationFn: (an: boolean) => Api.einstellungenSpeichern({ risk_off: an }), onSuccess: () => qc.invalidateQueries() });
  if (e.isLoading || !e.data) return <Laden />;
  const wert = (k: string) => e.data.find((x) => x.schluessel === k)?.wert;
  return (
    <div className="space-y-4">
      <Seitentitel>Einstellungen</Seitentitel>
      <Karte titel="Risiko">
        <Schalter label="Risk-off" hinweis={`Halbiert alle Positionsgrößen. Automatisch aktiv, wenn der Index am Vortag unter ${String(wert("risk_off_index_schwelle_pct")).replace(".", ",")} % lag (zuletzt ${String(wert("index_vortag_pct")).replace(".", ",")} %).`} an={wert("risk_off") === true} onChange={(an) => riskOff.mutate(an)} />
      </Karte>
      <Karte titel="Benachrichtigungen">
        <p className="mb-2 text-sm text-text2">Warnungen zu offenen Positionen erscheinen als Browser-Benachrichtigung, solange die App geöffnet ist (auch im Hintergrund-Tab). Status: {meldung}.</p>
        {meldung !== "erlaubt" && meldung !== "nicht unterstützt" && <Knopf klein onClick={() => void benachrichtigungenErlauben().then(setMeldung)}>Benachrichtigungen erlauben</Knopf>}
      </Karte>
      <Karte titel="Grenzwerte">
        <div className="space-y-3">{e.data.filter((x) => typeof x.wert !== "boolean" && !VERSTECKT.has(x.schluessel)).map((x) => <Grenzwert key={x.schluessel} e={x} />)}</div>
        <p className="mt-3 text-[11px] text-gedimmt">Änderungen werden beim Verlassen des Feldes gespeichert.</p>
      </Karte>
      <Watchlist />
      <Termine />
      <Anbieter />
      {abmelden && <Knopf className="w-full" onClick={abmelden}>Abmelden</Knopf>}
    </div>
  );
}
