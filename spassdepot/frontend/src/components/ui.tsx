import { useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import type { Kennzeichnung as KZ, Regel } from "../api/types";

export function Karte({ titel, rechts, children, className = "" }: { titel?: ReactNode; rechts?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-linie bg-karte p-4 ${className}`}>
      {(titel || rechts) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-text2">{titel}</h2>
          {rechts}
        </header>
      )}
      {children}
    </section>
  );
}

const KZ_STIL: Record<KZ, string> = {
  Fakt: "border-akzent/50 text-akzent",
  Annahme: "border-warn/50 text-warn",
  Modellwert: "border-gedimmt/60 text-text2",
};

/** Kennzeichnet jede Zahl als Fakt, Annahme oder Modellwert. */
export function Kennzeichnung({ art, titel }: { art: KZ; titel?: string }) {
  return (
    <span title={titel} className={`inline-block rounded border px-1 text-[10px] font-medium uppercase leading-4 tracking-wide ${KZ_STIL[art]}`}>
      {art}
    </span>
  );
}

type KnopfArt = "primaer" | "neutral" | "gefahr" | "leise";
const KNOPF: Record<KnopfArt, string> = {
  primaer: "bg-akzent text-white active:bg-akzent/80",
  neutral: "bg-erhoben text-text border border-linie active:bg-linie",
  gefahr: "bg-kritisch text-white active:bg-kritisch/80",
  leise: "text-text2 underline-offset-2 hover:underline",
};

export function Knopf({ art = "neutral", klein, className = "", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { art?: KnopfArt; klein?: boolean }) {
  return (
    <button
      type="button"
      {...p}
      className={`rounded-xl font-medium transition-colors disabled:opacity-40 ${klein ? "min-h-9 px-3 text-sm" : "min-h-11 px-4"} ${KNOPF[art]} ${className}`}
    />
  );
}

export function Feld({ label, hinweis, fehler, className = "", ...p }: InputHTMLAttributes<HTMLInputElement> & { label: string; hinweis?: string; fehler?: string }) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block text-xs text-text2">
        {label}
        {p.required && <span className="text-kritisch-text"> *</span>}
      </label>
      <input
        id={id}
        {...p}
        aria-invalid={!!fehler}
        className={`w-full rounded-xl border bg-erhoben px-3 py-2.5 text-text placeholder:text-gedimmt focus:outline-2 focus:outline-akzent ${fehler ? "border-kritisch" : "border-linie"}`}
      />
      {fehler ? <p className="mt-1 text-xs text-kritisch-text">{fehler}</p> : hinweis ? <p className="mt-1 text-xs text-gedimmt">{hinweis}</p> : null}
    </div>
  );
}

export function Auswahl<W extends string>({ label, wert, optionen, onChange, className = "" }: { label: string; wert: W; optionen: { wert: W; text: string }[]; onChange: (w: W) => void; className?: string }) {
  const id = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block text-xs text-text2">{label}</label>
      <select id={id} value={wert} onChange={(e) => onChange(e.target.value as W)} className="w-full rounded-xl border border-linie bg-erhoben px-3 py-2.5 text-text focus:outline-2 focus:outline-akzent">
        {optionen.map((o) => (
          <option key={o.wert} value={o.wert}>{o.text}</option>
        ))}
      </select>
    </div>
  );
}

/** Umschalter zwischen wenigen Optionen (Long/Short, Reiter, Filter). */
export function Segmente<W extends string>({ wert, optionen, onChange, label }: { wert: W; optionen: { wert: W; text: string }[]; onChange: (w: W) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="flex rounded-xl border border-linie bg-erhoben p-1">
      {optionen.map((o) => (
        <button
          key={o.wert}
          type="button"
          aria-pressed={wert === o.wert}
          onClick={() => onChange(o.wert)}
          className={`min-h-9 flex-1 rounded-lg px-2 text-sm font-medium ${wert === o.wert ? "bg-akzent text-white" : "text-text2"}`}
        >
          {o.text}
        </button>
      ))}
    </div>
  );
}

export function Schalter({ label, an, onChange, hinweis }: { label: string; an: boolean; onChange: (an: boolean) => void; hinweis?: string }) {
  return (
    <label className="flex min-h-11 cursor-pointer items-center justify-between gap-3">
      <span>
        <span className="block text-sm">{label}</span>
        {hinweis && <span className="block text-xs text-gedimmt">{hinweis}</span>}
      </span>
      <input type="checkbox" role="switch" checked={an} onChange={(e) => onChange(e.target.checked)} className="peer sr-only" />
      <span aria-hidden className="relative h-7 w-12 shrink-0 rounded-full bg-linie transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-6 after:w-6 after:rounded-full after:bg-text after:transition-transform peer-checked:bg-akzent peer-checked:after:translate-x-5 peer-focus-visible:outline-2 peer-focus-visible:outline-akzent" />
    </label>
  );
}

export function Regler({ label, wert, min, max, schritt = 1, anzeige, onChange }: { label: string; wert: number; min: number; max: number; schritt?: number; anzeige: string; onChange: (w: number) => void }) {
  const id = useId();
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <label htmlFor={id} className="text-xs text-text2">{label}</label>
        <output htmlFor={id} className="zahl text-sm font-semibold">{anzeige}</output>
      </div>
      <input id={id} type="range" min={min} max={max} step={schritt} value={wert} onChange={(e) => onChange(Number(e.target.value))} className="h-8 w-full" />
    </div>
  );
}

export function Kennzahl({ label, wert, art, klein, farbe = "" }: { label: string; wert: ReactNode; art?: KZ; klein?: boolean; farbe?: string }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-x-1.5 text-xs text-text2">
        <span>{label}</span>
        {art && <Kennzeichnung art={art} />}
      </div>
      <div className={`zahl font-semibold ${klein ? "text-base" : "text-xl"} ${farbe}`}>{wert}</div>
    </div>
  );
}

const AMPEL = {
  gruen: { farbe: "bg-gut", text: "Alles im Rahmen" },
  gelb: { farbe: "bg-warn", text: "Hinweis" },
  rot: { farbe: "bg-kritisch", text: "Ausstieg prüfen" },
  grau: { farbe: "bg-gedimmt", text: "Kein Kurs" },
};

export function Ampel({ stand }: { stand: keyof typeof AMPEL }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-text2">
      <span aria-hidden className={`h-2.5 w-2.5 rounded-full ${AMPEL[stand].farbe}`} />
      {AMPEL[stand].text}
    </span>
  );
}

export function Meldung({ art = "info", children }: { art?: "info" | "warn" | "fehler" | "gut"; children: ReactNode }) {
  const stil = {
    info: "border-linie bg-erhoben text-text2",
    warn: "border-warn/40 bg-warn/10 text-text",
    fehler: "border-kritisch/50 bg-kritisch/10 text-text",
    gut: "border-gut/40 bg-gut/10 text-text",
  }[art];
  const zeichen = { info: "ℹ", warn: "⚠", fehler: "✕", gut: "✓" }[art];
  return (
    <div role={art === "fehler" ? "alert" : "status"} className={`flex gap-2 rounded-xl border px-3 py-2 text-sm ${stil}`}>
      <span aria-hidden>{zeichen}</span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Regelliste({ regeln }: { regeln: Regel[] }) {
  return (
    <ul className="space-y-1.5">
      {regeln.map((r) => (
        <li key={r.regel} className="flex gap-2 text-sm">
          <span aria-hidden className={r.ok ? "text-gut-text" : "text-kritisch-text"}>{r.ok ? "✓" : "✕"}</span>
          <span className="sr-only">{r.ok ? "Eingehalten:" : "Verstoß:"}</span>
          <span className={r.ok ? "text-text2" : "text-text"}>{r.begruendung}</span>
        </li>
      ))}
    </ul>
  );
}

export function Leer({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-gedimmt">{children}</p>;
}

export function Laden() {
  return <p className="py-6 text-center text-sm text-gedimmt">Lädt …</p>;
}

export function Seitentitel({ children, rechts }: { children: ReactNode; rechts?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 pt-1">
      <h1 className="text-xl font-bold">{children}</h1>
      {rechts}
    </div>
  );
}
