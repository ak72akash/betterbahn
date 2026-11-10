// Browser-Benachrichtigungen (Notification API). Auf dem Handy über den Service
// Worker, weil dort `new Notification()` nicht erlaubt ist.
import type { Alarm } from "../api/types";

export type MeldeStatus = "erlaubt" | "abgelehnt" | "noch nicht gefragt" | "nicht unterstützt";

export function benachrichtigungsStatus(): MeldeStatus {
  if (typeof Notification === "undefined") return "nicht unterstützt";
  return Notification.permission === "granted" ? "erlaubt" : Notification.permission === "denied" ? "abgelehnt" : "noch nicht gefragt";
}

export async function benachrichtigungenErlauben(): Promise<MeldeStatus> {
  if (typeof Notification === "undefined") return "nicht unterstützt";
  await Notification.requestPermission();
  return benachrichtigungsStatus();
}

export async function registriereServiceWorker() {
  if ("serviceWorker" in navigator) {
    try {
      await navigator.serviceWorker.register("/sw.js");
    } catch {
      /* ohne Service Worker gibt es Benachrichtigungen nur am Desktop */
    }
  }
}

export async function melde(a: Alarm) {
  if (benachrichtigungsStatus() !== "erlaubt") return;
  const titel = `Spaßdepot: ${a.position}`;
  const optionen: NotificationOptions = { body: a.text, tag: `sd-${a.trade_id}-${a.regel}`, icon: "/icon.svg" };
  try {
    const reg = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration() : undefined;
    if (reg) await reg.showNotification(titel, optionen);
    else new Notification(titel, optionen);
  } catch {
    /* Benachrichtigung nicht möglich – die Warnung steht trotzdem in der Übersicht */
  }
}
