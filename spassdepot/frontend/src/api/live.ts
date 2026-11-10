// Live-Kurse: WebSocket mit automatischem Wiederaufbau (wachsende Wartezeit),
// Rückfall auf Server-Sent Events. Kurse liegen in einem kleinen Speicher, den
// Komponenten über useKurs(symbol) abonnieren.
import { useEffect, useState, useSyncExternalStore } from "react";
import type { Alarm, Kurs } from "./types";

type Zuhoerer = () => void;
type Verbindung = "verbunden" | "verbindet" | "getrennt";

const kurse = new Map<string, Kurs>();
const zuhoerer = new Map<string, Set<Zuhoerer>>();
const statusZuhoerer = new Set<Zuhoerer>();
const alarmZuhoerer = new Set<(a: Alarm) => void>();
let verbindung: Verbindung = "getrennt";
let ws: WebSocket | null = null;
let sse: EventSource | null = null;
let versuch = 0;
let wsFehlstarts = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
let gestartet = false;

export const wartezeitMs = (n: number) => Math.min(30000, 1000 * 2 ** n);

function setzeStatus(s: Verbindung) {
  if (verbindung !== s) {
    verbindung = s;
    statusZuhoerer.forEach((f) => f());
  }
}

export function setzeKurs(k: Kurs) {
  kurse.set(k.symbol, k);
  zuhoerer.get(k.symbol)?.forEach((f) => f());
  zuhoerer.get("*")?.forEach((f) => f());
}

function verarbeite(roh: string) {
  try {
    const n = JSON.parse(roh) as { typ: string; daten?: unknown };
    if (n.typ === "kurs") setzeKurs(n.daten as Kurs);
    else if (n.typ === "alert") alarmZuhoerer.forEach((f) => f(n.daten as Alarm));
  } catch {
    /* unlesbare Nachricht ignorieren */
  }
}

function neuVerbinden() {
  if (!gestartet || timer) return;
  timer = setTimeout(() => {
    timer = null;
    verbinde();
  }, wartezeitMs(versuch++));
}

function verbindeSse() {
  sse = new EventSource("/api/sse/prices");
  sse.onopen = () => {
    versuch = 0;
    setzeStatus("verbunden");
  };
  sse.onmessage = (e) => verarbeite(e.data);
  sse.onerror = () => {
    sse?.close();
    sse = null;
    setzeStatus("getrennt");
    neuVerbinden();
  };
}

function verbinde() {
  if (!gestartet) return;
  setzeStatus("verbindet");
  if (wsFehlstarts >= 3 || typeof WebSocket === "undefined") return verbindeSse();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let offen = false;
  ws = new WebSocket(`${proto}://${location.host}/api/ws/prices`);
  ws.onopen = () => {
    offen = true;
    versuch = 0;
    wsFehlstarts = 0;
    setzeStatus("verbunden");
  };
  ws.onmessage = (e) => verarbeite(String(e.data));
  ws.onclose = () => {
    ws = null;
    if (!offen) wsFehlstarts++; // kam nie zustande: nach 3 Versuchen auf SSE wechseln
    setzeStatus("getrennt");
    neuVerbinden();
  };
}

export function starteLive() {
  if (gestartet) return;
  gestartet = true;
  verbinde();
}

export function stoppeLive() {
  gestartet = false;
  if (timer) clearTimeout(timer);
  timer = null;
  ws?.close();
  sse?.close();
  ws = sse = null;
}

function abonniere(symbol: string, f: Zuhoerer) {
  if (!zuhoerer.has(symbol)) zuhoerer.set(symbol, new Set());
  zuhoerer.get(symbol)!.add(f);
  return () => {
    zuhoerer.get(symbol)?.delete(f);
  };
}

export function useKurs(symbol: string | null | undefined): Kurs | undefined {
  const s = symbol ?? "";
  return useSyncExternalStore(
    (f) => abonniere(s, f),
    () => kurse.get(s),
  );
}

export function useVerbindung(): Verbindung {
  return useSyncExternalStore(
    (f) => {
      statusZuhoerer.add(f);
      return () => statusZuhoerer.delete(f);
    },
    () => verbindung,
  );
}

export function beiAlarm(f: (a: Alarm) => void) {
  alarmZuhoerer.add(f);
  return () => {
    alarmZuhoerer.delete(f);
  };
}

/** Sekundentakt, damit "veraltet" auch ohne neues Update sichtbar wird. */
export function useJetzt(intervallMs = 1000): number {
  const [jetzt, setJetzt] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setJetzt(Date.now()), intervallMs);
    return () => clearInterval(t);
  }, [intervallMs]);
  return jetzt;
}

/** Veraltet = während der Handelszeit seit mehr als 60 s kein Update empfangen. */
export function istVeraltet(k: Kurs, jetztMs: number, nachSek = 60): boolean {
  if (k.schlusskurs || !k.markt_offen) return false;
  return k.veraltet || jetztMs - new Date(k.empfangen).getTime() > nachSek * 1000;
}
