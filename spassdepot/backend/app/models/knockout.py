"""Knock-out-Simulation (Monte-Carlo, Student-t-Renditen).

`knockout` und `max_hebel` sind die Referenzfunktionen aus der Spezifikation und
bleiben unverändert. `simuliere_knockout` ist die allgemeine Variante (Long und
Short, optional mit Histogramm) und liefert für Long exakt dieselben Werte.
"""
import numpy as np


def knockout(S, sigma, hebel, tage=10, einsatz=100, spread=0.01, fin=0.05,
             gap_sd=0.0, n=40000, steps=26, df=4, seed=1):
    rng = np.random.default_rng(seed)
    t = lambda size: rng.standard_t(df, size) / np.sqrt(df / (df - 2))
    dt = 1 / 252 / steps
    start = S * np.exp(t(n) * gap_sd) if gap_sd else np.full(n, float(S))
    P = start[:, None] * np.exp(np.cumsum(
        -sigma**2 / 2 * dt + t((n, tage * steps)) * sigma * np.sqrt(dt), axis=1))
    K = S * (1 - 1 / hebel)                      # Basispreis = KO-Schwelle
    ko = np.minimum(start, P.min(1)) <= K
    kosten = spread + fin * tage / 252 * K / (S - K)
    wert = np.where(ko, 0, (P[:, -1] - K) / (S - K) * (1 - kosten)) * einsatz
    q = lambda p: float(np.percentile(wert, p))
    return {"ko_schwelle": round(K, 2), "p_ko": float(ko.mean()),
            "p_gewinn": float((wert > einsatz).mean()),
            "p_verdopplung": float((wert >= 2 * einsatz).mean()),
            "median": q(50), "top25": q(75), "top10": q(90),
            "erwartung": float(wert.mean())}


def max_hebel(sigma, earnings_in_haltedauer=False, gap_sd=0.06):
    abstand = 3 * sigma / np.sqrt(252)
    if earnings_in_haltedauer:
        abstand = max(abstand, 2 * gap_sd)
    return int(1 / abstand)


def _histogramm(wert: np.ndarray, einsatz: float, bins: int) -> list[dict]:
    """Verteilung der Endwerte. Totalverluste (KO) bekommen eine eigene Klasse,
    der rechte Rand wird beim 99. Perzentil gekappt (letzte Klasse = "und mehr")."""
    n = len(wert)
    ko = wert <= 0
    rest = wert[~ko]
    out = [{"von": 0.0, "bis": 0.0, "anteil": float(ko.mean()), "ko": True}]
    if rest.size == 0:
        return out
    ober = max(float(np.percentile(rest, 99)), 2.0 * einsatz)
    anz, kanten = np.histogram(np.minimum(rest, ober), bins=bins, range=(0.0, ober))
    out += [{"von": float(kanten[i]), "bis": float(kanten[i + 1]),
             "anteil": float(anz[i] / n), "ko": False} for i in range(bins)]
    return out


def simuliere_knockout(S, sigma, hebel, tage=10, einsatz=100, spread=0.01, fin=0.05,
                       gap_sd=0.0, n=40000, steps=26, df=4, seed=1,
                       richtung="long", histogramm=False, bins=24):
    """Knock-out Long oder Short. Short: KO-Schwelle K = S·(1 + 1/Hebel) liegt über
    dem Kurs, der Schein gewinnt bei fallendem Kurs. Gleiche Zufallszahlen und
    Kostenannahmen wie `knockout`."""
    if richtung not in ("long", "short"):
        raise ValueError("richtung muss 'long' oder 'short' sein")
    if hebel <= 1:
        raise ValueError("hebel muss größer als 1 sein")
    rng = np.random.default_rng(seed)
    t = lambda size: rng.standard_t(df, size) / np.sqrt(df / (df - 2))
    dt = 1 / 252 / steps
    start = S * np.exp(t(n) * gap_sd) if gap_sd else np.full(n, float(S))
    P = start[:, None] * np.exp(np.cumsum(
        -sigma**2 / 2 * dt + t((n, tage * steps)) * sigma * np.sqrt(dt), axis=1))
    if richtung == "long":
        K = S * (1 - 1 / hebel)
        ko = np.minimum(start, P.min(1)) <= K
        innerer = (P[:, -1] - K) / (S - K)
    else:
        K = S * (1 + 1 / hebel)
        ko = np.maximum(start, P.max(1)) >= K
        innerer = (K - P[:, -1]) / (K - S)
    kosten = spread + fin * tage / 252 * K / abs(S - K)
    wert = np.where(ko, 0, innerer * (1 - kosten)) * einsatz
    q = lambda p: float(np.percentile(wert, p))
    erg = {"ko_schwelle": round(K, 2), "p_ko": float(ko.mean()),
           "p_gewinn": float((wert > einsatz).mean()),
           "p_verdopplung": float((wert >= 2 * einsatz).mean()),
           "median": q(50), "top25": q(75), "top10": q(90),
           "erwartung": float(wert.mean())}
    if histogramm:
        erg["histogramm"] = _histogramm(wert, einsatz, bins)
    return erg


def knockout_short(S, sigma, hebel, **kw):
    return simuliere_knockout(S, sigma, hebel, richtung="short", **kw)


def sichere_pfadzahl(tage: int, steps: int = 26, n: int = 40000, budget: int = 10_400_000) -> int:
    """Begrenzt n so, dass n·tage·steps im Budget bleibt (Antwortzeit < 2 s)."""
    return int(max(2000, min(n, budget // max(1, tage * steps))))
