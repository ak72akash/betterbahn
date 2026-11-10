"""Konfiguration ausschließlich über Umgebungsvariablen bzw. `.env`."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

WURZEL = Path(__file__).resolve().parents[2]          # Ordner spassdepot/
load_dotenv(WURZEL / ".env")


@dataclass
class Konfig:
    database_url: str = field(default_factory=lambda: os.getenv(
        "DATABASE_URL", f"sqlite:///{WURZEL / 'data' / 'app.db'}"))
    provider_order: list[str] = field(default_factory=lambda: [
        p.strip().lower() for p in os.getenv(
            "PROVIDER_ORDER", "finnhub,twelvedata,yfinance,alphavantage").split(",") if p.strip()])
    app_password: str = field(default_factory=lambda: os.getenv("APP_PASSWORD", ""))
    session_secret: str = field(default_factory=lambda: os.getenv("SESSION_SECRET", ""))
    cookie_secure: bool = field(default_factory=lambda: os.getenv("COOKIE_SECURE", "0") == "1")
    live_aktiv: bool = field(default_factory=lambda: os.getenv("LIVE_AKTIV", "1") == "1")
    jobs_aktiv: bool = field(default_factory=lambda: os.getenv("JOBS_AKTIV", "1") == "1")
    cors_origins: list[str] = field(default_factory=lambda: [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()])

    def schluessel(self, name: str) -> str:
        return os.getenv(name, "")


def konfig() -> Konfig:
    return Konfig()
