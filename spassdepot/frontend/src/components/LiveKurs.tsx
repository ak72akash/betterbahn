import { useEffect, useRef, useState } from "react";
import { istVeraltet, useJetzt, useKurs } from "../api/live";
import type { Kurs } from "../api/types";
import { kursText, uhrzeit } from "../lib/format";
import { Kennzeichnung } from "./ui";

/** Kurzes Aufblinken, wenn sich der Kurs ändert (grün = höher, rot = tiefer). */
function useBlink(wert: number | undefined): string {
  const alt = useRef(wert);
  const [klasse, setKlasse] = useState("");
  useEffect(() => {
    if (wert === undefined || alt.current === undefined || wert === alt.current) {
      alt.current = wert;
      return;
    }
    setKlasse(wert > alt.current ? "blink-auf" : "blink-ab");
    alt.current = wert;
    const t = setTimeout(() => setKlasse(""), 900);
    return () => clearTimeout(t);
  }, [wert]);
  return klasse;
}

export function kursEtikett(k: Kurs, veraltet: boolean): string {
  if (!k.markt_offen && !k.schlusskurs) return "Markt geschlossen";
  if (veraltet) return "veraltet";
  return k.etikett;
}

/** Live-Kurs mit Quelle, Uhrzeit und Etikett (Echtzeit / verzögert / Schlusskurs / veraltet). */
export function LiveKurs({ symbol, start, gross }: { symbol: string; start?: Kurs | null; gross?: boolean }) {
  const live = useKurs(symbol);
  const k = live ?? start ?? undefined;
  const jetzt = useJetzt();
  const blink = useBlink(k?.kurs);
  if (!k) return <span className="text-sm text-gedimmt">kein Kurs</span>;
  const veraltet = istVeraltet(k, jetzt);
  const etikett = kursEtikett(k, veraltet);
  const stil = veraltet
    ? "border-gedimmt/50 text-gedimmt"
    : etikett === "Echtzeit"
      ? "border-gut/50 text-gut-text"
      : etikett === "Markt geschlossen"
        ? "border-linie text-text2"
        : "border-warn/50 text-warn";
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span className={`zahl rounded px-1 -mx-1 font-semibold ${gross ? "text-2xl" : "text-base"} ${veraltet ? "text-gedimmt" : "text-text"} ${blink}`}>
          {kursText(k.kurs, symbol === "EURUSD" ? "FX" : k.waehrung)}
        </span>
        <span className={`rounded border px-1 text-[10px] font-medium leading-4 ${stil}`}>{etikett}</span>
        <Kennzeichnung art="Fakt" titel="Kurs laut Quelle" />
      </div>
      <div className="text-[11px] text-gedimmt">
        {k.quelle} · {uhrzeit(k.zeitstempel)}
        {!k.markt_offen && k.verzoegerung_sek > 0 && !k.schlusskurs ? ` · ${k.etikett}` : ""}
      </div>
      {k.weitere_quellen.map((w) => (
        <div key={w.quelle} className="text-[11px] text-warn">
          ⚠ Abweichung: {w.quelle} meldet {kursText(w.kurs, k.waehrung)} ({uhrzeit(w.zeitstempel)})
        </div>
      ))}
    </div>
  );
}
