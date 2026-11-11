"""Ratenbegrenzung je Anbieter: Mindestabstand, Minutenfenster und Tageszähler."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from datetime import date


class LimitErreicht(Exception):
    """Minuten- oder Tageslimit ausgeschöpft – nächster Anbieter ist dran."""


class RateLimiter:
    def __init__(self, min_abstand: float = 0.0, pro_minute: int | None = None,
                 pro_tag: int | None = None, clock: Callable[[], float] = time.monotonic,
                 heute: Callable[[], date] = date.today,
                 sleep: Callable[[float], object] = asyncio.sleep,
                 laden: Callable[[date], int] | None = None,
                 speichern: Callable[[date, int], None] | None = None):
        self.min_abstand, self.pro_minute, self.pro_tag = min_abstand, pro_minute, pro_tag
        self._clock, self._heute, self._sleep = clock, heute, sleep
        self._laden, self._speichern = laden, speichern
        self._fenster: deque[float] = deque()
        self._naechster = 0.0
        self._tag: date | None = None
        self._heute_anzahl = 0
        self._lock = asyncio.Lock()

    def _tag_pruefen(self) -> None:
        tag = self._heute()
        if tag != self._tag:
            self._tag = tag
            self._heute_anzahl = self._laden(tag) if self._laden else 0

    @property
    def heute_anzahl(self) -> int:
        self._tag_pruefen()
        return self._heute_anzahl

    @property
    def verbleibend_heute(self) -> int | None:
        return None if self.pro_tag is None else max(0, self.pro_tag - self.heute_anzahl)

    async def acquire(self) -> None:
        async with self._lock:
            self._tag_pruefen()
            if self.pro_tag is not None and self._heute_anzahl >= self.pro_tag:
                raise LimitErreicht(f"Tageslimit von {self.pro_tag} Abfragen erreicht")
            now = self._clock()
            while self._fenster and now - self._fenster[0] >= 60:
                self._fenster.popleft()
            if self.pro_minute is not None and len(self._fenster) >= self.pro_minute:
                raise LimitErreicht(f"Minutenlimit von {self.pro_minute} Abfragen erreicht")
            warte = self._naechster - now
            if warte > 0:
                r = self._sleep(warte)
                if asyncio.iscoroutine(r):
                    await r
                now = max(self._clock(), self._naechster)
            self._naechster = now + self.min_abstand
            self._fenster.append(now)
            self._heute_anzahl += 1
            if self._speichern and self._tag:
                self._speichern(self._tag, self._heute_anzahl)
