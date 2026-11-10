// Erzeugt die Bildschirmfotos für das README (Handy-Format). Voraussetzung: App läuft
// auf :5173 mit Beispieldaten (PROVIDER_ORDER=demo, scripts/demo_daten.py).
// Playwright muss installiert sein (global mit NODE_PATH oder im Projekt).
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");

const ziel = process.argv[2] ?? "docs/screenshots";
const skala = Number(process.argv[3] ?? 2);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: skala, locale: "de-DE" });
const page = await ctx.newPage();
const fehler = [];
page.on("console", (m) => m.type() === "error" && fehler.push(m.text()));
page.on("pageerror", (e) => fehler.push(String(e)));

async function foto(seite, name, vorher) {
  await page.goto(`http://localhost:5173/#/${seite}`);
  await page.waitForTimeout(1800);
  if (vorher) await vorher();
  // Fenster auf Seitenhöhe bringen, damit die feste Tab-Leiste unten sitzt
  const hoehe = await page.evaluate(() => document.documentElement.scrollHeight);
  await page.setViewportSize({ width: 390, height: Math.max(844, hoehe) });
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${ziel}/${name}.png` });
  await page.setViewportSize({ width: 390, height: 844 });
}

await foto("uebersicht", "1-uebersicht");
await foto("rechner", "2-rechner", async () => {
  await page.getByRole("button", { name: "Simulation starten" }).click();
  await page.getByText("P(KO)").waitFor();
  await page.waitForTimeout(600);
});
await foto("plan", "3-plan");
await foto("journal", "4-journal", async () => {
  await page.getByRole("button", { name: "Geschlossen" }).click();
  await page.waitForTimeout(500);
});
await foto("picks", "5-picks");
await foto("auswertung", "6-auswertung");
await foto("einstellungen", "7-einstellungen");
await browser.close();
console.log(fehler.length ? `Konsolenfehler:\n${fehler.join("\n")}` : "ohne Konsolenfehler");
