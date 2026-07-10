"""
Resumo diário (rodar 22h via systemd timer): manda no Telegram o menor preço do
dia (últimas 24h), o horário em que foi visto, e os detalhes do voo mais barato
(companhia, escalas, duração, horários — via fast-flights).

Teste (imprime, não envia):  ./.venv/bin/python daily_summary.py --dry
"""
import argparse
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta

from app.config import Config
from app.notify import telegram_send
from app.scrapers.google_flights import GoogleFlightsScraper
from app.normalizers.flight_normalizer import FlightNormalizer


def money(v):
    return ("R$ " + f"{int(v):,}".replace(",", ".")) if v is not None else "—"


def hm(iso):
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%H:%M")
    except Exception:
        return "?"


def d_(s):
    try:
        dt = datetime.strptime(str(s), "%Y-%m-%d")
        return dt.strftime("%d/%m") + " (" + ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"][dt.weekday()] + ")"
    except Exception:
        return str(s)


def flight_details(low):
    """Busca detalhes do voo mais barato do trecho (via fast-flights)."""
    try:
        rd = low["return_date"] or None
        raw = GoogleFlightsScraper().scrape(low["origin"], low["destination"],
                                            low["departure_date"], low["trip_type"], rd)
        fl = FlightNormalizer.normalize_items(raw)
        if not fl:
            return ""
        f = min(fl, key=lambda x: x["price"])
        dur = f.get("duration_minutes")
        dur_s = f"{dur // 60}h{dur % 60:02d}" if dur else None
        stops = f.get("stops")
        stops_s = "direto" if stops == 0 else (f"{stops} parada(s)" if stops else None)
        parts = [f.get("airline") or "?"]
        if stops_s:
            parts.append(stops_s)
        if dur_s:
            parts.append(dur_s)
        if f.get("departure_time"):
            parts.append(f"{f['departure_time']}→{f.get('arrival_time') or '?'}")
        if f.get("plane_type"):
            parts.append(f['plane_type'])
        return "\n✈️ <b>Voo mais barato agora nesse trecho:</b>\n   " + " · ".join(parts)
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--dry", action="store_true", help="imprime em vez de enviar")
    args = ap.parse_args()
    since = (datetime.now(timezone.utc) - timedelta(hours=args.hours)).isoformat()

    with closing(sqlite3.connect(Config.DB_PATH)) as c:
        c.row_factory = sqlite3.Row
        low = c.execute("SELECT * FROM price_history WHERE checked_at>=? "
                        "ORDER BY cheapest_price ASC LIMIT 1", (since,)).fetchone()

        def cheapest(cond, *params):
            r = c.execute(f"""SELECT origin,destination,departure_date,return_date,
                                     MIN(cheapest_price) AS p
                              FROM price_history WHERE checked_at>=? AND {cond}""",
                          (since, *params)).fetchone()
            return r if r and r["p"] is not None else None

        # par ida/volta com mais leituras (antes era GYN/JPA fixo no código)
        from app.database.sqlite_client import SQLiteClient
        det = SQLiteClient().detected_trip() or (None, None)
        o, d = det
        ida = cheapest("trip_type='oneway' AND destination=?", d) if d else None
        volta = cheapest("trip_type='oneway' AND destination=?", o) if o else None
        casada = cheapest("trip_type='roundtrip'")

    if not low:
        out = f"🌙 Resumo do dia — sem leituras nas últimas {args.hours}h. 🤔"
        print(out) if args.dry else telegram_send(out)
        return

    rd = low["return_date"]
    rota = (f"🔁 {low['origin']}→{low['destination']}  {d_(low['departure_date'])} → {d_(rd)} (ida-e-volta)"
            if rd else f"✈️ {low['origin']}→{low['destination']}  {d_(low['departure_date'])} (só-ida)")

    lines = [
        f"🌙 <b>Resumo do dia</b> — {o or '?'}↔{d or '?'} (últimas {args.hours}h)",
        "",
        f"💰 <b>Menor preço do dia: {money(low['cheapest_price'])}</b>",
        f"   {rota}",
        f"   ⏰ visto às {hm(low['checked_at'])}",
        flight_details(low),
        "",
        "📊 <b>Mais baratos hoje por tipo:</b>",
    ]
    if ida:
        lines.append(f"   🛫 Ida: {money(ida['p'])} ({d_(ida['departure_date'])})")
    if volta:
        lines.append(f"   🛬 Volta: {money(volta['p'])} ({d_(volta['departure_date'])})")
    if casada:
        lines.append(f"   🔁 Casada: {money(casada['p'])} "
                     f"({d_(casada['departure_date'])}→{d_(casada['return_date'])})")

    out = "\n".join(x for x in lines if x)
    if args.dry:
        print(out)
    else:
        telegram_send(out)


if __name__ == "__main__":
    main()
