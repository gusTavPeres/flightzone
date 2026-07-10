"""
Utilitários de normalização — reaproveitados do projeto original.
"""
import re
from typing import Optional


def normalize_text(text: str) -> str:
    """Remove espaços extras e normaliza."""
    if not text:
        return ""
    return " ".join(str(text).split()).strip()


def calculate_dedupe_key(
    origin: str,
    destination: str,
    departure_date: str,
    airline: str,
    price: float,
    trip_type: str,
    departure_time: str = "",
) -> str:
    """
    Chave de deduplicação:
        origin#destination#date#airline#departure_time#price#trip_type

    Voos distintos (horários diferentes) viram registros distintos. O mesmo
    voo coletado de novo com o MESMO preço é ignorado; uma mudança de preço
    gera um novo registro — útil para acompanhar o histórico de preços.
    """
    parts = [
        str(origin).upper(),
        str(destination).upper(),
        str(departure_date),
        normalize_text(airline).upper(),
        normalize_text(departure_time or ""),
        f"{float(price):.2f}",
        str(trip_type).lower(),
    ]
    return "#".join(parts)


def normalize_price(price_str: str) -> Optional[float]:
    """Normaliza 'R$ 1.250,90' ou '1250.90' para float."""
    if price_str is None:
        return None
    clean = re.sub(r"[R$\s]", "", str(price_str).strip())
    if re.search(r"\d\.\d{3}", clean) or ("," in clean and "." in clean):
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        clean = clean.replace(",", ".")
    try:
        v = float(clean)
        return v if v > 0 else None
    except ValueError:
        return None
