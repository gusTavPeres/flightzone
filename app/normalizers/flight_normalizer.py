"""
Valida e normaliza os voos antes de gravar no banco.
(reaproveitado e simplificado do projeto original)
"""
from typing import List, Dict, Optional
from app.utils.normalizers import normalize_text
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

REQUIRED = ("origin", "destination", "departure_date", "airline", "price", "dedupe_key")


def _as_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class FlightNormalizer:
    @staticmethod
    def normalize_items(items: List[Dict]) -> List[Dict]:
        out = []
        for it in items:
            try:
                r = FlightNormalizer.normalize_item(it)
                if r:
                    out.append(r)
            except Exception as e:
                logger.warning(f"Erro ao normalizar voo: {e}")
        logger.info(f"Normalizados {len(out)} de {len(items)} voos")
        return out

    @staticmethod
    def normalize_item(item: Dict) -> Optional[Dict]:
        for f in REQUIRED:
            if item.get(f) in (None, ""):
                return None
        try:
            price = float(item["price"])
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None

        return {
            "source": normalize_text(item.get("source", "google_flights")),
            "trip_type": normalize_text(item.get("trip_type", "oneway")),
            "origin": str(item["origin"]).upper(),
            "destination": str(item["destination"]).upper(),
            "departure_date": str(item["departure_date"]),
            "airline": normalize_text(item["airline"]),
            "price": price,
            "currency": str(item.get("currency", "BRL")),
            "departure_time": item.get("departure_time"),
            "arrival_time": item.get("arrival_time"),
            "duration_minutes": _as_int(item.get("duration_minutes")),
            "stops": _as_int(item.get("stops")),
            "cabin_class": normalize_text(item.get("cabin_class") or "economy"),
            "plane_type": normalize_text(item.get("plane_type") or ""),
            "dedupe_key": str(item["dedupe_key"]),
            "collected_at": item.get("collected_at"),
        }
