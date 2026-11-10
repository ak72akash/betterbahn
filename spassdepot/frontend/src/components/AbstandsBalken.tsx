import { kursText } from "../lib/format";

interface Marke {
  wert: number;
  name: string;
  farbe: string;
}

/** Zeigt auf einer Skala, wo der Kurs zwischen KO-Schwelle, Stop und Ziel steht. */
export function AbstandsBalken({ kurs, ko, stop, ziel, waehrung }: { kurs: number; ko?: number | null; stop?: number | null; ziel?: number | null; waehrung: string }) {
  const marken: Marke[] = [];
  if (ko != null) marken.push({ wert: ko, name: "KO", farbe: "bg-kritisch" });
  if (stop != null) marken.push({ wert: stop, name: "Stop", farbe: "bg-ernst" });
  if (ziel != null) marken.push({ wert: ziel, name: "Ziel", farbe: "bg-gut" });
  if (marken.length === 0) return null;
  const alle = [...marken.map((m) => m.wert), kurs];
  const spanne = Math.max(...alle) - Math.min(...alle) || kurs * 0.01;
  const min = Math.min(...alle) - spanne * 0.08;
  const max = Math.max(...alle) + spanne * 0.08;
  const pos = (w: number) => `${((w - min) / (max - min)) * 100}%`;
  return (
    <div>
      <div className="relative mt-2 h-6" role="img" aria-label={`Kurs ${kursText(kurs, waehrung)}; ${marken.map((m) => `${m.name} ${kursText(m.wert, waehrung)}`).join("; ")}`}>
        <div className="absolute inset-x-0 top-[11px] h-0.5 rounded bg-linie" />
        {marken.map((m) => (
          <span key={m.name} className={`absolute top-1 h-4 w-1 -translate-x-1/2 rounded ${m.farbe}`} style={{ left: pos(m.wert) }} />
        ))}
        <span className="absolute top-[5px] h-3.5 w-3.5 -translate-x-1/2 rounded-full border-2 border-karte bg-text transition-[left] duration-500" style={{ left: pos(kurs) }} />
      </div>
      <dl className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-text2">
        {marken.map((m) => (
          <div key={m.name} className="flex items-center gap-1">
            <span aria-hidden className={`h-2 w-2 rounded-sm ${m.farbe}`} />
            <dt>{m.name}</dt>
            <dd className="zahl">{kursText(m.wert, waehrung)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
