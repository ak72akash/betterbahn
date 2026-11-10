// Zahlen im deutschen Format (1.234,56 €)
const nf = (min: number, max: number) =>
  new Intl.NumberFormat("de-DE", { minimumFractionDigits: min, maximumFractionDigits: max });
const NF2 = nf(2, 2);

const leer = (x: number | null | undefined): x is null | undefined => x == null || Number.isNaN(x);

export const eur = (x: number | null | undefined) => (leer(x) ? "–" : `${NF2.format(x)} €`);

export const zahl = (x: number | null | undefined, stellen = 2) =>
  leer(x) ? "–" : nf(stellen, stellen).format(x);

/** Kurs in der Währung des Basiswerts, z. B. "188,42 $" oder "38,50 €". */
export const kursText = (x: number | null | undefined, waehrung = "EUR") => {
  if (leer(x)) return "–";
  const stellen = waehrung === "FX" || x < 5 ? 4 : 2;
  const einheit = waehrung === "USD" ? " $" : waehrung === "EUR" ? " €" : "";
  return nf(stellen, stellen).format(x) + einheit;
};

/** Prozent aus einem Prozentwert (12.3 -> "12,3 %"). */
export const pct = (x: number | null | undefined, stellen = 1, vorzeichen = false) =>
  leer(x) ? "–" : `${vorzeichen && x > 0 ? "+" : ""}${nf(stellen, stellen).format(x)} %`;

/** Prozent aus einem Anteil (0.123 -> "12,3 %"). */
export const anteil = (x: number | null | undefined, stellen = 1) => (leer(x) ? "–" : pct(x * 100, stellen));

export const eurVz = (x: number | null | undefined) =>
  leer(x) ? "–" : `${x > 0 ? "+" : ""}${NF2.format(x)} €`;

export const uhrzeit = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "–";

export const datum = (iso: string | null | undefined) =>
  iso ? new Date(iso.length === 10 ? `${iso}T12:00:00` : iso).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" }) : "–";

export const datumZeit = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "–";

export const heuteIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

/** Eingabe mit Komma oder Punkt in eine Zahl wandeln ("1.234,5" -> 1234.5). */
export const parseZahl = (s: string): number | null => {
  const t = s.trim();
  if (!t) return null;
  const norm = t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t;
  const n = Number(norm);
  return Number.isFinite(n) ? n : null;
};

export const vzFarbe = (x: number | null | undefined) =>
  leer(x) || x === 0 ? "text-text" : x > 0 ? "text-gut-text" : "text-kritisch-text";

export const TYP_NAME: Record<string, string> = {
  aktie: "Aktie",
  ko_long: "Knock-out Long",
  ko_short: "Knock-out Short",
};
