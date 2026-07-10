"""
Configurações do FlightZone Local.

Diferente do projeto original (que dependia de Google Cloud / BigQuery),
esta versão roda 100% no seu PC: armazenamento em SQLite e coleta via
Google Flights (sem chave de API). Tudo pode ser ajustado por variáveis
de ambiente, mas os defaults já funcionam.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    # ---- Armazenamento local (substitui o BigQuery) ----
    DB_PATH = os.getenv("FLIGHTZONE_DB", os.path.join(BASE_DIR, "data", "flights.db"))

    # ---- Lista de rotas monitoradas (editável pela web) ----
    ROUTES_PATH = os.getenv("ROUTES_FILE", os.path.join(BASE_DIR, "routes.json"))

    # ---- Telegram (alertas opcionais; gerado por telegram_setup.py) ----
    TELEGRAM_PATH = os.getenv("TELEGRAM_FILE", os.path.join(BASE_DIR, "telegram.json"))

    # ---- Amadeus (preço real opcional; gerado por amadeus_setup.py) ----
    AMADEUS_PATH = os.getenv("AMADEUS_FILE", os.path.join(BASE_DIR, "amadeus.json"))

    # ---- Coleta (Google Flights) ----
    CURRENCY = os.getenv("CURRENCY", "BRL")
    LANGUAGE = os.getenv("LANGUAGE", "pt-BR")

    # ---- Defaults de busca ----
    DEFAULT_ORIGIN = os.getenv("DEFAULT_ORIGIN", "GRU")
    DEFAULT_DESTINATION = os.getenv("DEFAULT_DESTINATION", "GIG")
    DEFAULT_TRIP_TYPE = os.getenv("DEFAULT_TRIP_TYPE", "oneway")  # oneway | roundtrip
    DEFAULT_SEAT = os.getenv("DEFAULT_SEAT", "economy")           # economy|premium-economy|business|first

    # ---- Servidor Flask ----
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "8080"))
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
