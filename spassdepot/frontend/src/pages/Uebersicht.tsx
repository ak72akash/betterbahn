import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Api } from "../api/client";
import { useKurs } from "../api/live";
import type { Position } from "../api/types";
import { AbstandsBalken } from "../components/AbstandsBalken";
import { LiveKurs } from "../components/LiveKurs";
import { Ampel, Karte, Kennzahl, Kennzeichnung, Knopf, Laden, Leer, Meldung, Seitentitel } from "../components/ui";
import { anteil, datum, datumZeit, eur, eurVz, pct, TYP_NAME, vzFarbe } from "../lib/format";
import { liveStand } from "../lib/bewertung";

function PositionsKarte({ p }: { p: Position }) {
  const live = useKurs(p.symbol);
  const fx = useKurs("EURUSD");
  const kurs = live && !live.schlusskurs ? live.kurs : (p.kurs ?? undefined);
  const stand = liveStand(p, kurs, fx?.kurs ?? p.eurusd ?? undefined);
  const waehrung = p.symbol.endsWith(".DE") ? "EUR" : "USD";
  return (
    <article className="rounded-2xl border border-linie bg-karte p-4">
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-semibold">{p.wertpapier}</h3>
          <p className="text-xs text-text2">
            {TYP_NAME[p.typ]} · {p.symbol} · Tag {p.handelstage}
          </p>
        </div>
        <Ampel stand={kurs === undefined ? "grau" : p.ampel} />
      </header>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <div className="text-xs text-text2">Kurs Basiswert</div>
          <LiveKurs symbol={p.symbol} start={p.kurs_info} />
        </div>
        <div>
          <div className="flex items-center gap-1.5 text-xs text-text2">
            Wert {p.geschaetzt && "(geschätzt)"} <Kennzeichnung art={p.geschaetzt ? "Modellwert" : "Fakt"} titel={p.hinweis ?? undefined} />
          </div>
          <div className="zahl text-base font-semibold">{eur(stand.wert)}</div>
          <div className={`zahl text-xs ${vzFarbe(stand.perfPct)}`}>
            {pct(stand.perfPct, 1, true)} · Einsatz {eur(p.einsatz)}
          </div>
        </div>
      </div>
      {kurs !== undefined && <AbstandsBalken kurs={kurs} ko={p.ko_schwelle} stop={p.stop} ziel={p.ziel} waehrung={waehrung} />}
      {stand.koAbstandPct !== null && (
        <p className="mt-2 text-xs text-text2">
          Abstand zur KO-Schwelle: <span className={`zahl font-semibold ${stand.koAbstandPct < 4 ? "text-kritisch-text" : "text-text"}`}>{pct(stand.koAbstandPct)}</span>
        </p>
      )}
      {p.signale.length > 0 && (
        <ul className="mt-2 space-y-1">
          {p.signale.map((s) => (
            <li key={s.regel} className="text-sm text-warn">⚠ {s.begruendung}</li>
          ))}
        </ul>
      )}
      {p.hinweis && <p className="mt-2 text-[11px] text-gedimmt">{p.hinweis}</p>}
    </article>
  );
}

export default function Uebersicht() {
  const qc = useQueryClient();
  const check = useQuery({ queryKey: ["positionen"], queryFn: Api.positionen, refetchInterval: 15000 });
  const alarme = useQuery({ queryKey: ["alarme"], queryFn: () => Api.alarme(true), refetchInterval: 30000 });
  const termine = useQuery({ queryKey: ["termine"], queryFn: Api.termine });
  const gelesen = useMutation({ mutationFn: Api.alleGelesen, onSuccess: () => qc.invalidateQueries({ queryKey: ["alarme"] }) });

  if (check.isLoading) return <Laden />;
  if (check.error || !check.data) return <Meldung art="fehler">Übersicht konnte nicht geladen werden: {String(check.error?.message ?? "")}</Meldung>;
  const { depot: d, risiko, positionen } = check.data;
  const heute = new Date().toISOString().slice(0, 10);
  const kommende = (termine.data ?? []).filter((t) => t.datum >= heute).slice(0, 5);

  return (
    <div className="space-y-4">
      <Seitentitel>Übersicht</Seitentitel>
      <Karte>
        <div className="flex items-end justify-between gap-3">
          <Kennzahl label="Depotwert" wert={eur(d.depotwert)} art={positionen.some((p) => p.geschaetzt) ? "Modellwert" : "Fakt"} />
          <div className={`zahl text-right text-sm font-semibold ${vzFarbe(d.veraenderung_eur)}`}>
            {eurVz(d.veraenderung_eur)}
            <div className="text-xs font-normal">{pct(d.veraenderung_pct, 1, true)} seit Start ({eur(d.startkapital)})</div>
          </div>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-erhoben" role="img" aria-label={`Depotwert ${eur(d.depotwert)} gegenüber Start ${eur(d.startkapital)}`}>
          <div className={`h-full rounded-full ${d.depotwert >= d.startkapital ? "bg-gut" : "bg-kritisch"}`} style={{ width: `${Math.min(100, (d.depotwert / (d.startkapital * 1.5)) * 100)}%` }} />
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2">
          <Kennzahl klein label="Freie Reserve" wert={eur(d.bargeld)} />
          <Kennzahl klein label="Reserve-Anteil" wert={anteil(d.reserve_anteil, 0)} farbe={d.bargeld < d.reserve_minimum ? "text-kritisch-text" : ""} />
          <Kennzahl klein label="Hebelprodukte" wert={eur(d.hebel_einsatz)} />
        </div>
      </Karte>

      {risiko.risk_off && <Meldung art="warn">{risiko.risk_off_text}</Meldung>}
      {risiko.verlustbremse && <Meldung art="warn">{risiko.verlustbremse_text}</Meldung>}

      {(alarme.data?.length ?? 0) > 0 && (
        <Karte titel={`Ungelesene Warnungen (${alarme.data!.length})`} rechts={<Knopf klein art="leise" onClick={() => gelesen.mutate()}>Alle gelesen</Knopf>}>
          <ul className="space-y-2">
            {alarme.data!.map((a) => (
              <li key={a.id} className="text-sm">
                <span className="font-medium">{a.position}</span> <span className="text-xs text-gedimmt">{datumZeit(a.zeit)}</span>
                <div className="text-text2">{a.text}</div>
              </li>
            ))}
          </ul>
        </Karte>
      )}

      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-text2">Offene Positionen ({positionen.length})</h2>
        {positionen.length === 0 ? <Leer>Keine offenen Positionen. Trades erfasst du im Journal.</Leer> : positionen.map((p) => <PositionsKarte key={p.trade_id} p={p} />)}
      </div>

      <Karte titel="Nächste Termine">
        {kommende.length === 0 ? (
          <Leer>Keine Termine eingetragen (Einstellungen → Termine).</Leer>
        ) : (
          <ul className="divide-y divide-linie">
            {kommende.map((t) => (
              <li key={t.id} className="flex items-baseline gap-3 py-2 text-sm">
                <span className="zahl w-20 shrink-0 text-text2">{datum(t.datum)}</span>
                <span className="min-w-0">
                  <span className="font-medium">{t.symbol ? `${t.symbol} · ` : ""}{t.art}</span>
                  {t.notiz && <span className="block text-xs text-text2">{t.notiz}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Karte>
    </div>
  );
}
