"""
Coletor de passagens via Google Flights — SEM chave de API e SEM antibot.

Por que Google Flights e não Decolar?
  O scraper original (httpx -> Decolar) é bloqueado pelo antibot DataDome
  (HTTP 403 / captcha "deslize para verificar"). O Google Flights, por outro
  lado, expõe um endpoint de dados que a biblioteca `fast-flights` consulta
  diretamente, devolvendo preços JÁ AGREGADOS das principais companhias
  (Gol, LATAM, Azul, Avianca, American, COPA, TAP, etc.).
"""
from datetime import datetime, timezone
from typing import List, Dict, Optional

from fast_flights import create_query, FlightQuery, Passengers, get_flights

from app.config import Config
from app.utils.logger import setup_logger
from app.utils.normalizers import normalize_text, calculate_dedupe_key

logger = setup_logger(__name__)

# nomenclatura interna -> nomenclatura da fast-flights
_TRIP_MAP = {"oneway": "one-way", "roundtrip": "round-trip"}


def _to_datetime(sdt) -> Optional[datetime]:
    """Converte SimpleDatetime(date=[Y,M,D], time=[H(,M)]) em datetime."""
    try:
        d = list(getattr(sdt, "date", []) or [])
        t = list(getattr(sdt, "time", []) or [])
        if len(d) < 3:
            return None
        hour = t[0] if len(t) >= 1 else 0
        minute = t[1] if len(t) >= 2 else 0
        return datetime(d[0], d[1], d[2], hour, minute)
    except Exception:
        return None


def _fmt_time(sdt) -> Optional[str]:
    dt = _to_datetime(sdt)
    return dt.strftime("%H:%M") if dt else None


class GoogleFlightsScraper:
    """Coleta voos do Google Flights para uma rota/data."""

    SOURCE = "google_flights"

    def scrape(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        trip_type: str = "oneway",
        return_date: Optional[str] = None,
        seat: str = "economy",
        max_stops: Optional[int] = None,
        adults: int = 1,
    ) -> List[Dict]:
        origin = origin.upper().strip()
        destination = destination.upper().strip()
        trip = _TRIP_MAP.get(trip_type, "one-way")

        legs_query = [
            FlightQuery(date=departure_date, from_airport=origin,
                        to_airport=destination, max_stops=max_stops)
        ]
        if trip == "round-trip":
            if not return_date:
                raise ValueError("return_date é obrigatório para viagens roundtrip")
            legs_query.append(
                FlightQuery(date=return_date, from_airport=destination,
                            to_airport=origin, max_stops=max_stops)
            )

        query = create_query(
            flights=legs_query,
            seat=seat,
            trip=trip,
            passengers=Passengers(adults=adults),
            currency=Config.CURRENCY,
            language=Config.LANGUAGE,
        )

        logger.info(
            f"Consultando Google Flights {origin}->{destination} "
            f"{departure_date} ({trip}, {seat})"
        )
        try:
            results = get_flights(query)
        except Exception as e:
            logger.error(f"Falha na consulta ao Google Flights: {e}")
            return []

        collected_at = datetime.now(timezone.utc).isoformat()
        flights: List[Dict] = []
        for item in results:
            row = self._map_item(item, origin, destination,
                                 departure_date, trip_type, seat, collected_at)
            if row:
                flights.append(row)

        logger.info(f"Coletados {len(flights)} voos")
        return sorted(flights, key=lambda x: x.get("price") or float("inf"))

    def _map_item(self, item, origin, destination, departure_date,
                  trip_type, seat, collected_at) -> Optional[Dict]:
        try:
            price = getattr(item, "price", None)
            if not isinstance(price, (int, float)):
                return None  # "Price unavailable"

            legs = list(getattr(item, "flights", []) or [])
            if not legs:
                return None
            first, last = legs[0], legs[-1]

            airlines = getattr(item, "airlines", None) or [getattr(item, "type", "")]
            airline = normalize_text(" / ".join([a for a in airlines if a])) or "?"

            if trip_type == "roundtrip":
                # ida+volta concatenadas: só o preço total e a partida fazem sentido
                departure_time = _fmt_time(first.departure)
                arrival_time = None
                duration_minutes = None
                stops = None
            else:
                departure_time = _fmt_time(first.departure)
                arrival_time = _fmt_time(last.arrival)
                dep_dt, arr_dt = _to_datetime(first.departure), _to_datetime(last.arrival)
                if dep_dt and arr_dt and arr_dt > dep_dt:
                    duration_minutes = int((arr_dt - dep_dt).total_seconds() // 60)
                else:
                    duration_minutes = sum(
                        int(getattr(l, "duration", 0) or 0) for l in legs
                    ) or None
                stops = max(len(legs) - 1, 0)

            plane = normalize_text(getattr(first, "plane_type", "") or "")
            dedupe_key = calculate_dedupe_key(
                origin, destination, departure_date, airline, float(price),
                trip_type, departure_time or "",
            )

            return {
                "source": self.SOURCE,
                "trip_type": trip_type,
                "origin": origin,
                "destination": destination,
                "departure_date": departure_date,
                "airline": airline,
                "price": float(price),
                "currency": Config.CURRENCY,
                "departure_time": departure_time,
                "arrival_time": arrival_time,
                "duration_minutes": duration_minutes,
                "stops": stops,
                "cabin_class": seat,
                "plane_type": plane,
                "dedupe_key": dedupe_key,
                "collected_at": collected_at,
            }
        except Exception as e:
            logger.debug(f"Erro ao mapear voo: {e}")
            return None
