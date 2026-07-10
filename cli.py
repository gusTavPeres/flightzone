"""
FlightZone — busca rápida pela linha de comando (grava no mesmo banco do servidor).

Exemplos:
    ./.venv/bin/python cli.py --from GRU --to GIG --date 2026-07-15
    ./.venv/bin/python cli.py --from GRU --to REC --date 2026-08-01 --max-stops 0
    ./.venv/bin/python cli.py --from GRU --to LIS --date 2026-09-10 \\
        --return 2026-09-25 --trip roundtrip --seat business
"""
import argparse
import uuid
from datetime import datetime, timezone

from app.scrapers.google_flights import GoogleFlightsScraper
from app.normalizers.flight_normalizer import FlightNormalizer
from app.database.sqlite_client import SQLiteClient


def main():
    ap = argparse.ArgumentParser(description="Busca passagens via Google Flights (local)")
    ap.add_argument("--from", dest="origin", required=True, help="IATA de origem (ex: GRU)")
    ap.add_argument("--to", dest="destination", required=True, help="IATA de destino (ex: GIG)")
    ap.add_argument("--date", required=True, help="Data de ida YYYY-MM-DD")
    ap.add_argument("--return", dest="return_date", help="Data de volta (se roundtrip)")
    ap.add_argument("--trip", default="oneway", choices=["oneway", "roundtrip"])
    ap.add_argument("--seat", default="economy",
                    choices=["economy", "premium-economy", "business", "first"])
    ap.add_argument("--max-stops", type=int, default=None, help="0 = só voos diretos")
    ap.add_argument("--no-save", action="store_true", help="Não gravar no banco")
    args = ap.parse_args()

    raw = GoogleFlightsScraper().scrape(
        args.origin, args.destination, args.date, args.trip,
        args.return_date, args.seat, args.max_stops,
    )
    flights = FlightNormalizer.normalize_items(raw)

    if not flights:
        print("Nenhum voo encontrado. Confira os códigos IATA e a data.")
        return

    o, d = args.origin.upper(), args.destination.upper()
    print(f"\n{len(flights)} voos  {o} -> {d}  em {args.date}  ({args.trip}, {args.seat})\n")
    print(f"{'#':>2}  {'Companhia':24} {'Preço':>13}  {'Saída':>6} {'Cheg.':>6}  {'Dur':>6} {'Par':>3}  Avião")
    print("-" * 96)
    for i, f in enumerate(flights, 1):
        dur = f.get("duration_minutes")
        dur_s = f"{dur // 60}h{dur % 60:02d}" if dur else "  -   "
        stops = f.get("stops")
        stops_s = "direto" if stops == 0 else (str(stops) if stops is not None else "-")
        print(f"{i:>2}  {(f['airline'] or '?')[:24]:24} "
              f"{f['currency']} {f['price']:>9.0f}  "
              f"{(f.get('departure_time') or '-'):>6} {(f.get('arrival_time') or '-'):>6}  "
              f"{dur_s:>6} {stops_s:>3}  {f.get('plane_type') or ''}")

    cheapest = flights[0]
    print(f"\n💸 Mais barato: {cheapest['currency']} {cheapest['price']:.0f} "
          f"({cheapest['airline']})")

    if not args.no_save:
        db = SQLiteClient()
        ex = str(uuid.uuid4())
        ins, dup = db.merge_flights(flights, ex)
        now = datetime.now(timezone.utc).isoformat()
        db.log_execution(execution_id=ex, start_time=now, end_time=now,
                         items_collected=len(raw), items_inserted=ins,
                         items_deduplicated=dup, status="success",
                         origin=o, destination=d, departure_date=args.date)
        print(f"💾 {ins} novos salvos ({dup} já existiam) em {db.db_path}")


if __name__ == "__main__":
    main()
