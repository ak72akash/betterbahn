import type * as T from "./types";

export class ApiFehler extends Error {
  constructor(
    public status: number,
    text: string,
  ) {
    super(text);
  }
}

function fehlertext(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { msg?: string; loc?: string[] }) => {
        const feld = d.loc?.filter((l) => l !== "body").join(".");
        const msg = (d.msg ?? "").replace(/^Value error, /, "");
        return feld ? `${feld}: ${msg}` : msg;
      })
      .join(" · ");
  }
  return `Fehler ${status}`;
}

export async function api<A>(pfad: string, init?: RequestInit & { json?: unknown }): Promise<A> {
  const { json, ...rest } = init ?? {};
  const r = await fetch(`/api${pfad}`, {
    credentials: "same-origin",
    ...rest,
    headers: json !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (r.status === 401 && !pfad.startsWith("/login")) window.dispatchEvent(new Event("sd-abgemeldet"));
  if (!r.ok) {
    let detail: unknown = null;
    try {
      detail = (await r.json()).detail;
    } catch {
      /* keine JSON-Antwort */
    }
    throw new ApiFehler(r.status, fehlertext(detail, r.status));
  }
  return r.status === 204 ? (undefined as A) : ((await r.json()) as A);
}

const post = <A>(pfad: string, json?: unknown) => api<A>(pfad, { method: "POST", json: json ?? {} });
const patch = <A>(pfad: string, json: unknown) => api<A>(pfad, { method: "PATCH", json });
const del = (pfad: string) => api<void>(pfad, { method: "DELETE" });

export const Api = {
  authStatus: () => api<{ passwort_noetig: boolean; angemeldet: boolean }>("/auth/status"),
  login: (passwort: string) => post<{ angemeldet: boolean }>("/login", { passwort }),
  logout: () => post("/logout"),

  quote: (symbol: string) => api<T.Kurs>(`/quote/${encodeURIComponent(symbol)}`),
  vol: (symbol: string) => api<T.Vol>(`/vol/${encodeURIComponent(symbol)}`),
  anbieter: () => api<T.AnbieterUebersicht>("/providers"),

  simKnockout: (e: T.KnockoutEingabe) => post<T.KnockoutErgebnis>("/sim/knockout", e),
  simOptionsschein: (e: Record<string, unknown>) => post<T.OptionsscheinErgebnis>("/sim/warrant", e),
  regelCheck: (e: { typ: T.TradeTyp; einsatz: number; symbol?: string | null }) => post<T.RegelCheck>("/rules/check", e),

  positionen: () => api<T.PositionsCheck>("/positions/check"),
  statistik: () => api<T.Statistik>("/stats"),
  morgen: (neu = false) => api<T.Morgenbericht>(`/reports/morning${neu ? "?neu=true" : ""}`),
  woche: (neu = false) => api<T.Wochenbilanz>(`/reports/week${neu ? "?neu=true" : ""}`),

  trades: (status: "alle" | "offen" | "geschlossen") => api<T.Trade[]>(`/trades?status=${status}`),
  tradeNeu: (t: Partial<T.TradeNeu>) => post<T.Trade>("/trades", t),
  tradeSchliessen: (id: number, d: Record<string, unknown>) => post<T.Trade>(`/trades/${id}/schliessen`, d),
  tradeLoeschen: (id: number) => del(`/trades/${id}`),

  plan: () => api<T.PlanEintrag[]>("/plan"),
  planNeu: (p: Partial<T.PlanEintrag>) => post<T.PlanEintrag>("/plan", p),
  planAendern: (id: number, p: Partial<T.PlanEintrag>) => patch<T.PlanEintrag>(`/plan/${id}`, p),
  planLoeschen: (id: number) => del(`/plan/${id}`),
  planUebernehmen: (id: number, t: Partial<T.TradeNeu>) => post<T.Trade>(`/plan/${id}/uebernehmen`, t),

  picks: () => api<T.Pick[]>("/picks"),
  pickNeu: (p: Record<string, unknown>) => post<T.PickPruefung>("/picks", p),
  pickLoeschen: (id: number) => del(`/picks/${id}`),
  picksBewerten: () => post<{ aktualisiert: number }>("/picks/bewerten"),

  watchlist: () => api<T.WatchlistEintrag[]>("/watchlist"),
  watchlistNeu: (w: Omit<T.WatchlistEintrag, "id">) => post<T.WatchlistEintrag>("/watchlist", w),
  watchlistLoeschen: (id: number) => del(`/watchlist/${id}`),

  termine: () => api<T.Termin[]>("/events"),
  terminNeu: (e: Omit<T.Termin, "id">) => post<T.Termin>("/events", e),
  terminLoeschen: (id: number) => del(`/events/${id}`),

  einstellungen: () => api<T.Einstellung[]>("/settings"),
  einstellungenSpeichern: (w: Record<string, number | boolean | string>) =>
    api<T.Einstellung[]>("/settings", { method: "PUT", json: w }),

  alarme: (nurUngelesen = false) => api<T.Alarm[]>(`/alerts?nur_ungelesen=${nurUngelesen}`),
  alarmGelesen: (id: number) => post<T.Alarm>(`/alerts/${id}/gelesen`),
  alleGelesen: () => post<{ gelesen: number }>("/alerts/gelesen"),
};
