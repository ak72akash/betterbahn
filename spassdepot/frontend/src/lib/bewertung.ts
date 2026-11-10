import type { Position } from "../api/types";

export interface LiveStand {
  wert: number | null;
  perfPct: number | null;
  koAbstandPct: number | null;
}

/** Gleiche Schätzformel wie im Backend, damit sich die Karte mit jedem Tick aktualisiert:
 *  Scheinwert = (Kurs − KO-Schwelle) × Bezugsverhältnis, bei US-Werten ÷ EUR/USD. */
export function liveStand(p: Position, kurs: number | undefined, eurusd: number | undefined): LiveStand {
  if (kurs === undefined) return { wert: p.wert, perfPct: p.perf_pct, koAbstandPct: p.ko_abstand_pct };
  const usd = !p.symbol.endsWith(".DE");
  if (usd && !eurusd) return { wert: null, perfPct: null, koAbstandPct: null };
  const fx = usd ? (eurusd as number) : 1;
  if (p.typ === "aktie") {
    const je = kurs / fx;
    return { wert: je * p.stueck, perfPct: (je / p.kaufkurs - 1) * 100, koAbstandPct: null };
  }
  const ko = p.ko_schwelle ?? 0;
  const bv = p.bezugsverhaeltnis ?? 0;
  const innerer = p.typ === "ko_long" ? kurs - ko : ko - kurs;
  const je = (Math.max(0, innerer) * bv) / fx;
  return { wert: je * p.stueck, perfPct: (je / p.kaufkurs - 1) * 100, koAbstandPct: (innerer / kurs) * 100 };
}
