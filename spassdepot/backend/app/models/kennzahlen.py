"""Volatilität, Ziel-vor-Stop-Wahrscheinlichkeit, Black-Scholes, Scalable-Filter."""
from math import erf, exp, log, sqrt

import numpy as np
import pandas as pd


def realized_vol(history, fenster: int = 20) -> float:
    """Annualisierte Volatilität aus Log-Renditen der letzten `fenster` Handelstage.

    `history`: DataFrame mit Spalte ``close`` oder eine Reihe von Schlusskursen
    (älteste zuerst)."""
    kurse = history["close"] if isinstance(history, pd.DataFrame) else pd.Series(list(history))
    kurse = kurse.astype(float).dropna()
    if len(kurse) < fenster + 1:
        raise ValueError(f"Zu wenig Kursdaten: {len(kurse)} Schlusskurse, benötigt {fenster + 1}")
    r = np.log(kurse / kurse.shift(1)).dropna().iloc[-fenster:]
    return float(r.std(ddof=1) * np.sqrt(252))


def p_target_before_stop(S, sigma, ziel_pct, stop_pct, tage, n=20000, steps=26, df=4,
                         seed=1, richtung="long"):
    """Monte-Carlo mit Student-t (df=4): Was wird zuerst erreicht?

    ``ziel_pct``/``stop_pct`` sind positive Abstände vom Kurs (0.08 = 8 %). Long:
    Ziel oben, Stop unten; Short umgekehrt. Trifft ein Schritt beides, zählt der Stop."""
    if ziel_pct <= 0 or stop_pct <= 0:
        raise ValueError("ziel_pct und stop_pct müssen positiv sein")
    rng = np.random.default_rng(seed)
    t = rng.standard_t(df, (n, tage * steps)) / np.sqrt(df / (df - 2))
    dt = 1 / 252 / steps
    P = S * np.exp(np.cumsum(-sigma**2 / 2 * dt + t * sigma * np.sqrt(dt), axis=1))
    if richtung == "long":
        ziel, stop = P >= S * (1 + ziel_pct), P <= S * (1 - stop_pct)
    else:
        ziel, stop = P <= S * (1 - ziel_pct), P >= S * (1 + stop_pct)
    nie = P.shape[1] + 1
    t_ziel = np.where(ziel.any(1), ziel.argmax(1), nie)
    t_stop = np.where(stop.any(1), stop.argmax(1), nie)
    p_ziel = float((t_ziel < t_stop).mean())
    p_stop = float(((t_stop <= t_ziel) & (t_stop < nie)).mean())
    return {"p_ziel": p_ziel, "p_stop": p_stop, "p_offen": max(0.0, 1.0 - p_ziel - p_stop)}


def _N(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _bs_preis(S, K, T, sigma, r, typ):
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if typ == "call" else max(0.0, K - S)
    d1 = (log(S / K) + (r + sigma**2 / 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    if typ == "call":
        return S * _N(d1) - K * exp(-r * T) * _N(d2)
    return K * exp(-r * T) * _N(-d2) - S * _N(-d1)


def black_scholes(S, K, tage, sigma, typ="call", r=0.025, bezugsverhaeltnis=0.1,
                  preis=None, wechselkurs=1.0):
    """Kennzahlen eines Optionsscheins (europäisch, ohne Dividenden).

    ``tage``: Kalendertage Restlaufzeit. ``preis``: Briefkurs des Scheins in € (optional;
    ohne Angabe wird der faire Preis verwendet). ``wechselkurs``: EUR/USD bei
    US-Basiswerten, sonst 1. Wahrscheinlichkeiten sind risikoneutral (Drift = r)."""
    if typ not in ("call", "put"):
        raise ValueError("typ muss 'call' oder 'put' sein")
    if min(S, K, sigma, tage, bezugsverhaeltnis, wechselkurs) <= 0:
        raise ValueError("S, K, sigma, tage, Bezugsverhältnis und Wechselkurs müssen positiv sein")
    T = tage / 365
    faktor = bezugsverhaeltnis / wechselkurs
    fair = _bs_preis(S, K, T, sigma, r, typ) * faktor
    d1 = (log(S / K) + (r + sigma**2 / 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    delta = _N(d1) if typ == "call" else _N(d1) - 1
    p = preis if preis else fair
    praemie = p / faktor                      # Preis je Aktie in Währung des Basiswerts
    be = K + praemie if typ == "call" else K - praemie
    def p_ueber(grenze: float) -> float:      # P(S_T jenseits der Grenze), lognormal
        if grenze <= 0:
            return 0.0 if typ == "put" else 1.0
        d = (log(S / grenze) + (r - sigma**2 / 2) * T) / (sigma * sqrt(T))
        return _N(d) if typ == "call" else _N(-d)
    T7 = max(T - 7 / 365, 0.0)
    woche = (_bs_preis(S, K, T7, sigma, r, typ) - _bs_preis(S, K, T, sigma, r, typ)) * faktor
    innerer = (max(0.0, S - K) if typ == "call" else max(0.0, K - S)) * faktor
    return {
        "fairer_preis": fair,
        "delta": delta,
        "omega": abs(delta) * S * faktor / p if p > 0 else 0.0,
        "break_even": be,
        "p_im_geld": _N(d2) if typ == "call" else _N(-d2),
        "p_ueber_break_even": p_ueber(be),
        "zeitwertverlust_woche": woche,
        "innerer_wert": innerer,
        "zeitwert": p - innerer,
        "aufgeld_zum_fairen_preis_pct": (p / fair - 1) * 100 if fair > 0 else None,
    }


def scalable_filter(kurs, hebel, richtung="long"):
    """Suchwerte für die Derivate-Suche des Brokers. Liefert bewusst keine WKN."""
    if richtung not in ("long", "short"):
        raise ValueError("richtung muss 'long' oder 'short' sein")
    if hebel <= 1:
        raise ValueError("hebel muss größer als 1 sein")
    ko = kurs * (1 - 1 / hebel) if richtung == "long" else kurs * (1 + 1 / hebel)
    return {
        "typ": "Knock-out / Turbo",
        "richtung": "Long" if richtung == "long" else "Short",
        "laufzeit": "Open End",
        "hebel_von": round(max(1.1, hebel - 1), 1),
        "hebel_bis": round(hebel + 1, 1),
        "ko_schwelle": round(ko, 2),
        "bezugsverhaeltnis": 0.1,
        "max_spread_pct": 1.0,
    }
