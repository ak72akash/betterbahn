import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Api } from "./api/client";
import { beiAlarm, starteLive, stoppeLive, useVerbindung } from "./api/live";
import { Feld, Knopf, Laden, Meldung } from "./components/ui";
import { melde, registriereServiceWorker } from "./lib/benachrichtigung";
import Auswertung from "./pages/Auswertung";
import Einstellungen from "./pages/Einstellungen";
import Journal from "./pages/Journal";
import Picks from "./pages/Picks";
import Plan from "./pages/Plan";
import Rechner from "./pages/Rechner";
import Uebersicht from "./pages/Uebersicht";

const ICON: Record<string, ReactNode> = {
  uebersicht: <path d="M3 11.5 12 4l9 7.5M5.5 10v9.5h13V10" />,
  rechner: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M8.5 7.5h7M8.5 12h1M12 12h1M15.5 12h0M8.5 16h1M12 16h1M15.5 16h0" /></>,
  plan: <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M8.5 3v4M15.5 3v4" /></>,
  journal: <><path d="M6 3.5h11a1.5 1.5 0 0 1 1.5 1.5v15.5H7.5A1.5 1.5 0 0 1 6 19V3.5Z" /><path d="M9.5 8h5.5M9.5 12h5.5" /></>,
  picks: <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><circle cx="12" cy="12" r="0.8" /></>,
  auswertung: <path d="M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6" />,
  einstellungen: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></>,
};

const SEITEN = [
  { id: "uebersicht", name: "Übersicht" },
  { id: "rechner", name: "Rechner" },
  { id: "plan", name: "Plan" },
  { id: "journal", name: "Journal" },
  { id: "picks", name: "Picks" },
  { id: "auswertung", name: "Auswertung" },
  { id: "einstellungen", name: "Optionen" },
] as const;
type SeitenId = (typeof SEITEN)[number]["id"];

const ausHash = (): SeitenId => {
  const h = window.location.hash.replace("#/", "").replace("#", "");
  return SEITEN.some((s) => s.id === h) ? (h as SeitenId) : "uebersicht";
};

function Login({ fertig }: { fertig: () => void }) {
  const [pw, setPw] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const anmelden = async () => {
    try {
      await Api.login(pw);
      fertig();
    } catch (e) {
      setFehler(e instanceof Error ? e.message : "Anmeldung fehlgeschlagen");
    }
  };
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-4 p-6">
      <h1 className="text-2xl font-bold">Spaßdepot</h1>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void anmelden(); }}>
        <Feld label="Passwort" type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
        {fehler && <Meldung art="fehler">{fehler}</Meldung>}
        <Knopf art="primaer" type="submit" className="w-full" disabled={!pw}>Anmelden</Knopf>
      </form>
    </main>
  );
}

export default function App() {
  const qc = useQueryClient();
  const auth = useQuery({ queryKey: ["auth"], queryFn: Api.authStatus, retry: 1 });
  const [seite, setSeite] = useState<SeitenId>(ausHash);
  const verbindung = useVerbindung();
  const angemeldet = auth.data?.angemeldet === true;

  useEffect(() => {
    const beiHash = () => setSeite(ausHash());
    const abgemeldet = () => void qc.invalidateQueries({ queryKey: ["auth"] });
    window.addEventListener("hashchange", beiHash);
    window.addEventListener("sd-abgemeldet", abgemeldet);
    return () => {
      window.removeEventListener("hashchange", beiHash);
      window.removeEventListener("sd-abgemeldet", abgemeldet);
    };
  }, [qc]);

  useEffect(() => {
    if (!angemeldet) return;
    starteLive();
    void registriereServiceWorker();
    const ab = beiAlarm((a) => {
      void melde(a);
      void qc.invalidateQueries({ queryKey: ["alarme"] });
      void qc.invalidateQueries({ queryKey: ["positionen"] });
    });
    return () => {
      ab();
      stoppeLive();
    };
  }, [angemeldet, qc]);

  if (auth.isLoading) return <Laden />;
  if (auth.isError) return <main className="p-6"><Meldung art="fehler">Das Backend ist nicht erreichbar. Läuft es auf Port 8000?</Meldung></main>;
  if (!angemeldet) return <Login fertig={() => void auth.refetch()} />;

  const abmelden = auth.data?.passwort_noetig ? () => void Api.logout().then(() => auth.refetch()) : undefined;
  return (
    <div className="mx-auto min-h-dvh max-w-xl">
      {verbindung !== "verbunden" && (
        <div role="status" className="sticky top-0 z-20 bg-warn px-4 py-1 text-center text-xs font-medium text-black">
          Live-Verbindung {verbindung === "verbindet" ? "wird aufgebaut …" : "getrennt – neuer Versuch läuft"}
        </div>
      )}
      <main className="px-4 pt-4 pb-28">
        {seite === "uebersicht" && <Uebersicht />}
        {seite === "rechner" && <Rechner />}
        {seite === "plan" && <Plan />}
        {seite === "journal" && <Journal />}
        {seite === "picks" && <Picks />}
        {seite === "auswertung" && <Auswertung />}
        {seite === "einstellungen" && <Einstellungen abmelden={abmelden} />}
        <footer className="mt-8 text-center text-[11px] text-gedimmt">
          Keine Anlageberatung. Modellwerte sind keine Prognosen.
        </footer>
      </main>
      <nav aria-label="Hauptnavigation" className="fixed inset-x-0 bottom-0 z-10 border-t border-linie bg-karte/95 pb-[env(safe-area-inset-bottom)] backdrop-blur">
        <ul className="mx-auto flex max-w-xl">
          {SEITEN.map((s) => (
            <li key={s.id} className="flex-1">
              <a
                href={`#/${s.id}`}
                aria-current={seite === s.id ? "page" : undefined}
                className={`flex min-h-14 flex-col items-center justify-center gap-0.5 ${seite === s.id ? "text-akzent" : "text-gedimmt"}`}
              >
                <svg aria-hidden viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{ICON[s.id]}</svg>
                <span className="text-[10px] leading-none">{s.name}</span>
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
