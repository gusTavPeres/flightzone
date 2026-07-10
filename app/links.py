"""
Gera o link direto do Google Flights para uma busca (mesma URL que o
fast-flights usa internamente — abre exatamente a rota/data pesquisada).
"""
from fast_flights import create_query, FlightQuery, Passengers

_TRIP = {"oneway": "one-way", "roundtrip": "round-trip"}


def gflights_url(origin, dest, date, trip="oneway", return_date=None, seat="economy"):
    o, d = str(origin).upper(), str(dest).upper()
    t = _TRIP.get(trip, "one-way")
    flights = [FlightQuery(date=str(date), from_airport=o, to_airport=d)]
    if t == "round-trip" and return_date:
        flights.append(FlightQuery(date=str(return_date), from_airport=d, to_airport=o))
    try:
        q = create_query(flights=flights, trip=t, seat=seat,
                         passengers=Passengers(adults=1), currency="BRL", language="pt-BR")
        return q.url()
    except Exception:
        # fallback: busca textual no Google Flights
        return f"https://www.google.com/travel/flights?q=voos%20{o}%20{d}%20{date}"
