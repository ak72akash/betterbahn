import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Api } from "../api/client";
import { Karte, Kennzahl, Kennzeichnung, Knopf, Laden, Leer, Meldung, Seitentitel } from "../components/ui";
import { anteil, datum, datumZeit, eur, eurVz, vzFarbe, zahl } from "../lib/format";

const ACHSE = { fill: "var(--color-gedimmt)", fontSize: 11 };
const TIP = { backgroundColor: "var(--color-erhoben)", border: "1px solid var(--color-linie)", borderRadius: 8, fontSize: 12 };

export default function Auswertung() {
  const st = useQuery({ queryKey: ["statistik"], queryFn: Api.statistik });
  const woche = useQuery({ queryKey: ["woche"], queryFn: () => Api.woche(), retry: false });
  const morgen = useQuery({ queryKey: ["morgen"], queryFn: () => Api.morgen(), retry: false });
  if (st.isLoading) return <Laden />;
  if (!st.data) return <Meldung art="fehler">Auswertung konnte nicht geladen werden.</Meldung>;
  const s = st.data;
  const verlauf = s.depotverlauf.map((p) => ({ ...p, tag: datum(p.datum).slice(0, 6) }));
  const kal = s.kalibrierung.map((k) => ({ gruppe: `${k.gruppe} (${k.anzahl})`, Prognose: k.prognose_mittel !== null ? k.prognose_mittel * 100 : null, Tatsächlich: k.trefferquote !== null ? k.trefferquote * 100 : null, anzahl: k.anzahl }));
  return (
    <div className="space-y-4">
      <Seitentitel>Auswertung</Seitentitel>
      <Karte titel="Kennzahlen" rechts={<Kennzeichnung art="Fakt" titel="Aus den geschlossenen Trades im Journal berechnet" />}>
        <div className="grid grid-cols-2 gap-x-3 gap-y-4">
          <Kennzahl label="Trefferquote" wert={anteil(s.trefferquote, 0)} />
          <Kennzahl label="Gewinnfaktor" wert={s.gewinnfaktor === null ? "–" : zahl(s.gewinnfaktor)} />
          <Kennzahl label="Ergebnis gesamt" wert={eurVz(s.ergebnis_gesamt)} farbe={vzFarbe(s.ergebnis_gesamt)} />
          <Kennzahl label="Trades (zu / offen)" wert={`${s.anzahl_geschlossen} / ${s.anzahl_offen}`} />
          <Kennzahl klein label="Ø Gewinn" wert={eur(s.durchschnitt_gewinn)} />
          <Kennzahl klein label="Ø Verlust" wert={eur(s.durchschnitt_verlust)} />
        </div>
        <p className="mt-3 text-[11px] text-gedimmt">Gewinnfaktor = Summe der Gewinne ÷ Summe der Verluste. {s.gewinner} Gewinner, {s.verlierer} Verlierer.</p>
      </Karte>

      <Karte titel="Depotverlauf (realisiert)">
        {verlauf.length < 2 ? <Leer>Erscheint nach dem ersten geschlossenen Trade.</Leer> : (
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={verlauf} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                <CartesianGrid vertical={false} stroke="var(--color-linie)" strokeOpacity={0.6} />
                <XAxis dataKey="tag" tick={ACHSE} tickLine={false} axisLine={{ stroke: "var(--color-linie)" }} minTickGap={24} />
                <YAxis domain={["auto", "auto"]} tick={ACHSE} tickLine={false} axisLine={false} width={48} tickFormatter={(v: number) => zahl(v, 0)} />
                <Tooltip contentStyle={TIP} labelStyle={{ color: "var(--color-text2)" }} formatter={(v) => [eur(Number(v)), "Depotwert"]} />
                <ReferenceLine y={verlauf[0].depotwert} stroke="var(--color-gedimmt)" strokeDasharray="3 3" label={{ value: "Start", position: "insideTopLeft", fill: "var(--color-gedimmt)", fontSize: 11 }} />
                <Line type="linear" dataKey="depotwert" stroke="var(--color-akzent)" strokeWidth={2} dot={{ r: 3, fill: "var(--color-akzent)", strokeWidth: 0 }} activeDot={{ r: 5 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Karte>

      <Karte titel="Kalibrierung: Prognose gegen Wirklichkeit">
        {kal.every((k) => k.anzahl === 0) ? <Leer>Erscheint, sobald geschlossene Trades eine Prognose P(Gewinn) haben.</Leer> : (
          <>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={kal} margin={{ top: 8, right: 8, bottom: 0, left: -8 }} barGap={2} barCategoryGap="24%">
                  <CartesianGrid vertical={false} stroke="var(--color-linie)" strokeOpacity={0.6} />
                  <XAxis dataKey="gruppe" tick={ACHSE} tickLine={false} axisLine={{ stroke: "var(--color-linie)" }} />
                  <YAxis domain={[0, 100]} tick={ACHSE} tickLine={false} axisLine={false} width={48} tickFormatter={(v: number) => `${v} %`} />
                  <Tooltip contentStyle={TIP} labelStyle={{ color: "var(--color-text2)" }} cursor={{ fill: "var(--color-text)", fillOpacity: 0.06 }} formatter={(v, name) => [`${zahl(Number(v), 0)} %`, name]} />
                  <Legend iconType="square" wrapperStyle={{ fontSize: 11 }} formatter={(name) => <span style={{ color: "var(--color-text2)" }}>{name}</span>} />
                  <Bar name="Prognose (Mittel)" dataKey="Prognose" fill="var(--color-akzent)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  <Bar name="Tatsächliche Trefferquote" dataKey="Tatsächlich" fill="var(--color-serie2)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="zahl mt-3 w-full text-xs">
              <thead className="text-text2"><tr><th className="py-1 text-left font-normal">Gruppe</th><th className="text-right font-normal">Trades</th><th className="text-right font-normal">Prognose</th><th className="text-right font-normal">Tatsächlich</th></tr></thead>
              <tbody>
                {s.kalibrierung.map((k) => (
                  <tr key={k.gruppe} className="border-t border-linie"><td className="py-1">{k.gruppe}</td><td className="text-right">{k.anzahl}</td><td className="text-right">{anteil(k.prognose_mittel, 0)}</td><td className="text-right">{anteil(k.trefferquote, 0)}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-gedimmt">Liegt die tatsächliche Trefferquote dauerhaft unter der Prognose, sind die Modellannahmen zu optimistisch. In Klammern: Anzahl Trades – wenige Trades sagen wenig aus.</p>
          </>
        )}
      </Karte>

      <Karte titel={`Regelverstöße (${s.regelverstoesse.length})`}>
        {s.regelverstoesse.length === 0 ? <Leer>Keine Regelverstöße im Journal.</Leer> : (
          <ul className="divide-y divide-linie">
            {s.regelverstoesse.map((v, i) => (
              <li key={i} className="py-2 text-sm"><span className="font-medium">{v.wertpapier}</span> <span className="text-xs text-gedimmt">{datum(v.datum)}</span><div className="text-text2">{v.text}</div></li>
            ))}
          </ul>
        )}
      </Karte>

      <Karte titel="Morgenbericht" rechts={<Knopf klein art="leise" onClick={() => void Api.morgen(true).then(() => morgen.refetch())}>Neu erzeugen</Knopf>}>
        {morgen.data ? (
          <>
            <ul className="space-y-1 text-sm">{morgen.data.zusammenfassung.map((z, i) => <li key={i}>{z}</li>)}</ul>
            <p className="mt-2 text-[11px] text-gedimmt">Erzeugt {datumZeit(morgen.data.gespeichert_am)} · automatisch werktags 07:45</p>
          </>
        ) : <Leer>{morgen.isLoading ? "Lädt …" : "Noch kein Bericht."}</Leer>}
      </Karte>

      <Karte titel={`Wochenbilanz ${woche.data?.woche ?? ""}`} rechts={<Knopf klein art="leise" onClick={() => void Api.woche(true).then(() => woche.refetch())}>Neu erzeugen</Knopf>}>
        {woche.data ? (
          <>
            <div className="grid grid-cols-3 gap-2">
              <Kennzahl klein label="Ergebnis" wert={eurVz(woche.data.ergebnis_woche)} farbe={vzFarbe(woche.data.ergebnis_woche)} />
              <Kennzahl klein label="Gekauft" wert={woche.data.gekauft.length} />
              <Kennzahl klein label="Verkauft" wert={woche.data.verkauft.length} />
            </div>
            {woche.data.lehren.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-text2">{woche.data.lehren.map((l, i) => <li key={i}>{l}</li>)}</ul>}
            <p className="mt-2 text-[11px] text-gedimmt">{datum(woche.data.von)} bis {datum(woche.data.bis)} · erzeugt {datumZeit(woche.data.gespeichert_am)} · automatisch freitags 19:15</p>
          </>
        ) : <Leer>{woche.isLoading ? "Lädt …" : "Noch keine Wochenbilanz."}</Leer>}
      </Karte>
    </div>
  );
}
