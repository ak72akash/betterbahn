import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setzeKurs } from "../api/live";
import type { Kurs, KnockoutErgebnis } from "../api/types";
import Rechner, { filterText } from "./Rechner";

const kurs = (wert: number): Kurs => ({
  symbol: "IFX.DE", kurs: wert, waehrung: "EUR", zeitstempel: "2026-11-09T11:00:00Z", empfangen: new Date().toISOString(),
  quelle: "testquelle", verzoegerung_sek: 0, schlusskurs: false, etikett: "Echtzeit", veraltet: false, markt: "Xetra",
  markt_offen: true, gettex_offen: true, hinweis: null, weitere_quellen: [],
});

const ergebnis: KnockoutErgebnis = {
  ko_schwelle: 35, p_ko: 0.344, p_gewinn: 0.445, p_verdopplung: 0.1715, median: 82, top25: 166.18, top10: 1242.58, erwartung: 99.3,
  histogramm: [{ von: 0, bis: 0, anteil: 0.344, ko: true }, { von: 0, bis: 100, anteil: 0.3, ko: false }, { von: 100, bis: 200, anteil: 0.356, ko: false }],
  max_hebel: 7, hebel_regel: { regel: "hebel_obergrenze", ok: false, begruendung: "Hebel 8 liegt über der Obergrenze 7.", wert: 7 },
  filter: { typ: "Knock-out / Turbo", richtung: "Long", laufzeit: "Open End", hebel_von: 7, hebel_bis: 9, ko_schwelle: 35, bezugsverhaeltnis: 0.1, max_spread_pct: 1, kurs: 40, symbol: "IFX.DE", hinweis: "Die App nennt keine WKN." },
  verwendeter_kurs: 40, gap_sd: 0, n: 40000, seed: 1, dauer_ms: 500,
};

let simAnfragen: Record<string, unknown>[] = [];

function antwort(daten: unknown) {
  return Promise.resolve(new Response(JSON.stringify(daten), { status: 200, headers: { "Content-Type": "application/json" } }));
}

beforeEach(() => {
  simAnfragen = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/watchlist")) return antwort([{ id: 1, symbol: "IFX.DE", name: "Infineon", branche: "Halbleiter" }]);
    if (url.includes("/api/quote/")) return antwort(kurs(40));
    if (url.includes("/api/vol/")) return antwort({ symbol: "IFX.DE", vol20: 0.5, vol60: 0.57, sigma_vorschlag: 0.57, letzter_schluss: 39.5, stand: "2026-11-06", quelle: "testquelle", tage: 120, naechste_quartalszahlen: null });
    if (url.endsWith("/api/sim/knockout")) {
      simAnfragen.push(JSON.parse(String(init?.body)));
      return antwort(ergebnis);
    }
    return Promise.resolve(new Response("{}", { status: 404 }));
  }));
});

function zeige() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><Rechner /></QueryClientProvider>);
}

describe("Rechner", () => {
  it("lädt Kurs und Volatilität, friert den Kurs ein und zeigt das Ergebnis im deutschen Format", async () => {
    const user = userEvent.setup();
    zeige();
    expect(await screen.findByText("40,00 €")).toBeInTheDocument();
    expect(await screen.findByText("57 %")).toBeInTheDocument();
    expect(screen.getByText("Echtzeit")).toBeInTheDocument();
    expect(screen.getByText(/testquelle · /)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Short (fällt)" }));
    await user.click(screen.getByRole("switch", { name: /Zahlen über Nacht/ }));
    await user.click(screen.getByRole("button", { name: "Simulation starten" }));

    expect(await screen.findByText("34,4 %")).toBeInTheDocument();          // P(KO)
    expect(screen.getByText("44,5 %")).toBeInTheDocument();                 // P(Gewinn)
    expect(screen.getByText("17,2 %")).toBeInTheDocument();                 // P(Verdopplung)
    expect(screen.getByText("1.242,58 €")).toBeInTheDocument();             // bestes Zehntel, Tausenderpunkt
    expect(screen.getByText(/Empfohlener Maximalhebel: 7/)).toBeInTheDocument();
    expect(screen.getByText(/eingefroren um/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /KO-Schwelle \(ca\.\) 35,00 € kopieren/ })).toBeInTheDocument();
    expect(simAnfragen).toEqual([{ symbol: "IFX.DE", kurs: 40, sigma: 0.57, hebel: 8, tage: 10, einsatz: 100, richtung: "short", zahlen_ueber_nacht: true }]);

    // Der Live-Kurs läuft weiter, der eingefrorene Wert der Simulation bleibt stehen.
    setzeKurs(kurs(41.5));
    expect(await screen.findByText("41,50 €")).toBeInTheDocument();
    expect(screen.getByText(/Verwendeter Kurs:/).textContent).toContain("40,00 €");
  });

  it("nimmt einen überschriebenen Kurs als Annahme", async () => {
    const user = userEvent.setup();
    zeige();
    await screen.findByText("57 %");
    await user.type(screen.getByLabelText(/Kurs überschreiben/), "38,5");
    await user.click(screen.getByRole("button", { name: "Simulation starten" }));
    await waitFor(() => expect(simAnfragen).toHaveLength(1));
    expect(simAnfragen[0].kurs).toBe(38.5);
    expect(await screen.findByText(/eigene Eingabe \(Annahme\)/)).toBeInTheDocument();
  });

  it("zeigt den Optionsschein-Check im zweiten Reiter", async () => {
    const user = userEvent.setup();
    zeige();
    await user.click(screen.getByRole("button", { name: "Optionsschein-Check" }));
    expect(screen.getByRole("button", { name: "Optionsschein prüfen" })).toBeDisabled();
  });

  it("baut den Filtertext ohne WKN", () => {
    const t = filterText(ergebnis.filter);
    expect(t).toBe("Knock-out / Turbo, Long, Open End, Hebel 7–9, KO-Schwelle ca. 35,00, Bezugsverhältnis 0,1, Spread < 1 %");
  });
});
