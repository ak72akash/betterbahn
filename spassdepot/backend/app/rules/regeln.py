"""Filter- und Risikoregeln als reine Funktionen. Jede Regel liefert ein
`Regelergebnis` mit deutscher Begründung."""
from dataclasses import asdict, dataclass
from datetime import date

import numpy as np

from app.models.knockout import max_hebel
from app.rules.grenzen import STANDARD


@dataclass(frozen=True)
class Regelergebnis:
    regel: str
    ok: bool
    begruendung: str
    wert: float | None = None

    def dict(self) -> dict:
        return asdict(self)


def eur(x: float) -> str:
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def pct(x: float, stellen: int = 1) -> str:
    return f"{x:.{stellen}f}".replace(".", ",") + " %"


def ist_hebelprodukt(typ: str) -> bool:
    return typ in ("ko_long", "ko_short", "optionsschein")


def handelstage(von: date, bis: date) -> int:
    """Handelstage zwischen zwei Daten (Mo–Fr, ohne Feiertagskalender)."""
    return int(np.busday_count(von, bis))


def risk_off_aktiv(schalter: bool, index_vortag_pct: float | None = None, g: dict = STANDARD) -> Regelergebnis:
    schwelle = float(g["risk_off_index_schwelle_pct"])
    if schalter:
        return Regelergebnis("risk_off", False, "Risk-off ist manuell eingeschaltet: Positionsgrößen halbieren.")
    if index_vortag_pct is not None and index_vortag_pct < schwelle:
        return Regelergebnis("risk_off", False,
                             f"Index am Vortag {pct(index_vortag_pct)} (unter {pct(schwelle)}): "
                             "Risk-off, Positionsgrößen halbieren.", index_vortag_pct)
    return Regelergebnis("risk_off", True, "Kein Risk-off: normale Positionsgrößen.", index_vortag_pct)


def verlustbremse(depotwert: float, g: dict = STANDARD) -> Regelergebnis:
    grenze = float(g["verlustbremse_depotwert"])
    if depotwert < grenze:
        return Regelergebnis("verlustbremse", False,
                             f"Depotwert {eur(depotwert)} liegt unter {eur(grenze)}: nur halbe Positionsgrößen.",
                             depotwert)
    return Regelergebnis("verlustbremse", True,
                         f"Depotwert {eur(depotwert)} liegt über der Verlustbremse von {eur(grenze)}.", depotwert)


def max_positionsgroesse(typ: str, depotwert: float, risk_off: bool = False, g: dict = STANDARD) -> Regelergebnis:
    """Höchster Einsatz für eine neue Position. Verlustbremse und Risk-off halbieren
    jeweils (zusammen also ein Viertel)."""
    basis = float(g["max_ko_einsatz"] if ist_hebelprodukt(typ) else g["max_aktie_einsatz"])
    faktor, gruende = 1.0, []
    if not verlustbremse(depotwert, g).ok:
        faktor *= 0.5
        gruende.append("Verlustbremse aktiv")
    if risk_off:
        faktor *= 0.5
        gruende.append("Risk-off aktiv")
    art = "Hebelprodukt" if ist_hebelprodukt(typ) else "Aktie"
    zusatz = f" ({', '.join(gruende)}: Faktor {str(faktor).replace('.', ',')})" if gruende else ""
    return Regelergebnis("max_positionsgroesse", True,
                         f"Maximaler Einsatz für {art}: {eur(basis * faktor)}{zusatz}.", basis * faktor)


def pruefe_position(typ: str, einsatz: float, depotwert: float, bargeld: float,
                    hebel_bestand: float = 0.0, positionen_in_branche: int = 0,
                    risk_off: bool = False, g: dict = STANDARD) -> list[Regelergebnis]:
    """Prüft eine geplante Position gegen alle Größenregeln.

    ``bargeld``: freie Mittel vor dem Kauf; ``hebel_bestand``: bereits in
    Hebelprodukten gebundener Einsatz; ``positionen_in_branche``: offene Positionen
    derselben Branche vor dem Kauf."""
    erg: list[Regelergebnis] = []
    grenze = max_positionsgroesse(typ, depotwert, risk_off, g)
    assert grenze.wert is not None
    ok = einsatz <= grenze.wert + 1e-9
    erg.append(Regelergebnis("positionsgroesse", ok,
                             f"Einsatz {eur(einsatz)} {'hält' if ok else 'überschreitet'} das Limit. "
                             + grenze.begruendung, einsatz))
    if ist_hebelprodukt(typ):
        anteil = float(g["max_hebel_anteil"])
        neu = hebel_bestand + einsatz
        ok = neu <= anteil * depotwert + 1e-9
        erg.append(Regelergebnis("hebel_anteil", ok,
                                 f"Hebelprodukte nach Kauf: {eur(neu)} = {pct(neu / depotwert * 100 if depotwert else 0)} "
                                 f"des Depots (erlaubt max. {pct(anteil * 100, 0)}).", neu))
    res = float(g["min_reserve_anteil"])
    rest = bargeld - einsatz
    ok = rest >= res * depotwert - 1e-9
    erg.append(Regelergebnis("reserve", ok,
                             f"Reserve nach Kauf: {eur(rest)} (Minimum {pct(res * 100, 0)} des Depots = "
                             f"{eur(res * depotwert)}).", rest))
    mb = int(g["max_pro_branche"])
    ok = positionen_in_branche + 1 <= mb
    erg.append(Regelergebnis("branche", ok,
                             f"Mit diesem Kauf {positionen_in_branche + 1} Position(en) in der Branche "
                             f"(erlaubt max. {mb}).", positionen_in_branche + 1))
    return erg


def hebel_obergrenze(hebel: float, sigma: float, earnings_in_haltedauer: bool = False,
                     g: dict = STANDARD) -> Regelergebnis:
    grenze = max_hebel(sigma, earnings_in_haltedauer, float(g["earnings_gap_sd"]))
    ok = hebel <= grenze
    zusatz = " (Quartalszahlen in der Haltedauer berücksichtigt)" if earnings_in_haltedauer else ""
    return Regelergebnis("hebel_obergrenze", ok,
                         f"Hebel {hebel:g} {'liegt innerhalb' if ok else 'liegt über'} der Obergrenze {grenze} "
                         f"bei Volatilität {pct(sigma * 100, 0)}{zusatz}: Der KO-Abstand soll mindestens "
                         "drei Tagesschwankungen betragen.", float(grenze))


def earnings_regel(ko_abstand_pct: float, erwartete_bewegung_pct: float,
                   earnings_in_haltedauer: bool) -> Regelergebnis:
    """Knock-out nicht über Quartalszahlen halten, wenn KO-Abstand < 2 × erwartete Bewegung."""
    if not earnings_in_haltedauer:
        return Regelergebnis("earnings", True, "Keine Quartalszahlen in der Haltedauer.", ko_abstand_pct)
    noetig = 2 * erwartete_bewegung_pct
    ok = ko_abstand_pct >= noetig
    return Regelergebnis("earnings", ok,
                         f"Quartalszahlen in der Haltedauer: KO-Abstand {pct(ko_abstand_pct)} "
                         f"{'reicht' if ok else 'ist kleiner als'} 2 × erwartete Bewegung ({pct(noetig)})"
                         f"{'.' if ok else ' – nicht über die Zahlen halten.'}", ko_abstand_pct)


def chance_risiko(kurs: float, ziel: float, stop: float, richtung: str = "long") -> float:
    chance = ziel - kurs if richtung == "long" else kurs - ziel
    risiko = kurs - stop if richtung == "long" else stop - kurs
    if chance <= 0 or risiko <= 0:
        raise ValueError("Ziel und Stop passen nicht zur Richtung (Long: Stop < Kurs < Ziel; Short umgekehrt).")
    return chance / risiko


def qualitaetsschwelle(p_ziel_vor_stop: float, kurs: float, ziel: float, stop: float,
                       richtung: str = "long", g: dict = STANDARD) -> list[Regelergebnis]:
    min_p, min_crv = float(g["pick_min_p_ziel"]), float(g["pick_min_crv"])
    crv = chance_risiko(kurs, ziel, stop, richtung)
    ok_p, ok_c = p_ziel_vor_stop >= min_p, crv >= min_crv - 1e-9
    return [
        Regelergebnis("pick_wahrscheinlichkeit", ok_p,
                      f"P(Ziel vor Stop) = {pct(p_ziel_vor_stop * 100)} "
                      f"({'mindestens' if ok_p else 'unter'} {pct(min_p * 100, 0)}).", p_ziel_vor_stop),
        Regelergebnis("pick_crv", ok_c,
                      f"Chance-Risiko-Verhältnis {crv:.2f}".replace(".", ",")
                      + f" ({'mindestens' if ok_c else 'unter'} {str(min_crv).replace('.', ',')}).", crv),
    ]


def ausstieg_knockout(perf_pct: float, handelstage_gehalten: int, ko_abstand_pct: float,
                      g: dict = STANDARD) -> list[Regelergebnis]:
    """Ausstiegssignale für einen offenen Knock-out. ``ok=False`` heißt: Signal ausgelöst."""
    out = []
    gewinn, verlust = float(g["ko_gewinn_teilverkauf_pct"]), float(g["ko_verlust_stop_pct"])
    zeit, abst = int(g["ko_zeitstop_tage"]), float(g["ko_abstand_warnung_pct"])
    if perf_pct >= gewinn:
        out.append(Regelergebnis("ko_verdopplung", False,
                                 f"Schein steht bei {pct(perf_pct, 0)} (Schwelle +{pct(gewinn, 0)}): Hälfte verkaufen.",
                                 perf_pct))
    if perf_pct <= verlust:
        out.append(Regelergebnis("ko_verlust", False,
                                 f"Schein steht bei {pct(perf_pct, 0)} (Schwelle {pct(verlust, 0)}): Position schließen.",
                                 perf_pct))
    if handelstage_gehalten >= zeit:
        out.append(Regelergebnis("ko_zeitstop", False,
                                 f"Seit {handelstage_gehalten} Handelstagen gehalten (Zeit-Stop nach {zeit}): "
                                 "Position schließen.", float(handelstage_gehalten)))
    if ko_abstand_pct < abst:
        out.append(Regelergebnis("ko_abstand", False,
                                 f"Abstand zur KO-Schwelle nur noch {pct(ko_abstand_pct)} (Warnung unter {pct(abst, 0)}).",
                                 ko_abstand_pct))
    return out


def ausstieg_aktie(kurs: float, ziel: float | None, stop: float | None) -> list[Regelergebnis]:
    out = []
    if ziel is not None and kurs >= ziel:
        out.append(Regelergebnis("aktie_ziel", False,
                                 f"Kurs {kurs:.2f} hat das Ziel {ziel:.2f} erreicht: Gewinn mitnehmen.".replace(".", ",", 2), kurs))
    if stop is not None and kurs <= stop:
        out.append(Regelergebnis("aktie_stop", False,
                                 f"Kurs {kurs:.2f} hat den Stop {stop:.2f} erreicht: verkaufen.".replace(".", ",", 2), kurs))
    return out


def ampel(signale: list[Regelergebnis]) -> str:
    """rot = Ausstieg fällig, gelb = Warnung/Gewinnmitnahme, grün = nichts zu tun."""
    regeln = {s.regel for s in signale}
    if regeln & {"ko_verlust", "ko_zeitstop", "aktie_stop"}:
        return "rot"
    if regeln:
        return "gelb"
    return "gruen"
