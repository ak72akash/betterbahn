import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HistKlasse } from "../api/types";
import { anteil, eur, zahl } from "../lib/format";

interface Zeile {
  name: string;
  mitte: number;
  anteil: number;
  ko: boolean;
  bereich: string;
}

function Hinweis({ active, payload }: { active?: boolean; payload?: { payload: Zeile }[] }) {
  if (!active || !payload?.length) return null;
  const z = payload[0].payload;
  return (
    <div className="rounded-lg border border-linie bg-erhoben px-3 py-2 text-xs shadow-lg">
      <div className="font-semibold text-text">{z.bereich}</div>
      <div className="zahl text-text2">{anteil(z.anteil)} der Simulationen</div>
    </div>
  );
}

/** Verteilung der Endwerte. Eigene Klasse für den Totalverlust (KO), Linie beim Einsatz. */
export function Histogramm({ klassen, einsatz }: { klassen: HistKlasse[]; einsatz: number }) {
  const rest = klassen.filter((k) => !k.ko);
  const letzte = rest[rest.length - 1];
  const daten: Zeile[] = klassen.map((k) => ({
    name: k.ko ? "KO" : zahl((k.von + k.bis) / 2, 0),
    mitte: (k.von + k.bis) / 2,
    anteil: k.anteil,
    ko: k.ko,
    bereich: k.ko ? "Knock-out: Totalverlust (0 €)" : k === letzte ? `ab ${eur(k.von)}` : `${eur(k.von)} bis ${eur(k.bis)}`,
  }));
  const beimEinsatz = daten.find((z) => !z.ko && Math.abs(z.mitte - einsatz) <= (rest[0].bis - rest[0].von) / 2)?.name;
  const ticks = [daten[0].name, ...rest.filter((_, i) => i % 6 === 5).map((k) => zahl((k.von + k.bis) / 2, 0))];
  return (
    <figure>
      <div className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={daten} margin={{ top: 16, right: 4, bottom: 0, left: -18 }} barCategoryGap={2}>
            <CartesianGrid vertical={false} stroke="var(--color-linie)" strokeOpacity={0.6} />
            <XAxis dataKey="name" ticks={ticks} interval={0} tick={{ fill: "var(--color-gedimmt)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--color-linie)" }} />
            <YAxis tickFormatter={(v: number) => `${Math.round(v * 100)} %`} tick={{ fill: "var(--color-gedimmt)", fontSize: 11 }} tickLine={false} axisLine={false} width={52} />
            <Tooltip content={<Hinweis />} cursor={{ fill: "var(--color-text)", fillOpacity: 0.06 }} />
            {beimEinsatz && <ReferenceLine x={beimEinsatz} stroke="var(--color-text2)" strokeDasharray="3 3" label={{ value: "Einsatz", position: "top", fill: "var(--color-text2)", fontSize: 11 }} />}
            <Bar dataKey="anteil" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {daten.map((z) => (
                <Cell key={z.name} fill={z.ko ? "var(--color-kritisch)" : "var(--color-akzent)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 text-[11px] text-text2">
        <span className="flex items-center gap-1"><span aria-hidden className="h-2 w-2 rounded-sm bg-kritisch" /> Knock-out (Totalverlust)</span>
        <span className="flex items-center gap-1"><span aria-hidden className="h-2 w-2 rounded-sm bg-akzent" /> Endwert in € (rechts gekappt)</span>
      </figcaption>
    </figure>
  );
}
