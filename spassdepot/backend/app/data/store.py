"""Kursspeicher im Arbeitsspeicher: je Symbol der letzte Kurs jeder Quelle."""
from __future__ import annotations

from datetime import UTC, datetime

from app.data.base import Kurs
from app.data.maerkte import kurs_status, waehrung


class KursSpeicher:
    def __init__(self) -> None:
        self._kurse: dict[str, dict[str, Kurs]] = {}

    def aktualisiere(self, k: Kurs) -> bool:
        """Speichert den Kurs; True, wenn sich der beste Kurs des Symbols geändert hat."""
        vorher = self.bester(k.symbol)
        self._kurse.setdefault(k.symbol, {})[k.quelle] = k
        nachher = self.bester(k.symbol)
        return vorher is None or nachher is None or (nachher.kurs, nachher.quelle) != (vorher.kurs, vorher.quelle)

    def bester(self, symbol: str) -> Kurs | None:
        """Jüngster empfangener Live-Kurs; Schlusskurse nur, wenn es nichts anderes gibt."""
        alle = list(self._kurse.get(symbol, {}).values())
        live = [k for k in alle if not k.schlusskurs]
        kandidaten = live or alle
        return max(kandidaten, key=lambda k: k.empfangen) if kandidaten else None

    def quellen(self, symbol: str) -> list[Kurs]:
        return list(self._kurse.get(symbol, {}).values())

    def symbole(self) -> list[str]:
        return list(self._kurse)

    def abweichungen(self, symbol: str, schwelle_pct: float = 3.0, max_alter_sek: float = 900,
                     now: datetime | None = None) -> list[Kurs]:
        """Andere Quellen, deren aktueller Kurs um mehr als die Schwelle abweicht."""
        b = self.bester(symbol)
        if b is None or b.kurs <= 0:
            return []
        now = now or datetime.now(UTC)
        return [k for k in self.quellen(symbol)
                if k.quelle != b.quelle and not k.schlusskurs
                and (now - k.empfangen).total_seconds() <= max_alter_sek
                and abs(k.kurs / b.kurs - 1) * 100 > schwelle_pct]

    def nachricht(self, symbol: str, now: datetime | None = None, schwelle_pct: float = 3.0,
                  nach_sek: float = 60) -> dict | None:
        b = self.bester(symbol)
        if b is None:
            return None
        return {**kurs_dict(b, now, nach_sek),
                "weitere_quellen": [kurs_dict(k, now, nach_sek) for k in self.abweichungen(symbol, schwelle_pct, now=now)]}


def kurs_dict(k: Kurs, now: datetime | None = None, nach_sek: float = 60) -> dict:
    return {"symbol": k.symbol, "kurs": k.kurs, "waehrung": waehrung(k.symbol),
            "zeitstempel": k.zeitstempel.isoformat(), "empfangen": k.empfangen.isoformat(),
            "quelle": k.quelle, "verzoegerung_sek": k.verzoegerung_sek, "schlusskurs": k.schlusskurs,
            "kennzeichnung": "Fakt", **kurs_status(k, now, nach_sek)}
