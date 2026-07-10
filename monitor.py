"""
FlightZone — monitor de preços de 1..N rotas, seguro contra bloqueio.

A calibração anti-bloqueio é GERAL (limita a TAXA de requisições, não o nº de rotas):
    espaçamento_entre_requests = max(T / N, s_min)
    intervalo_efetivo_por_rota = max(T, N * s_min)
    teto_de_req_por_minuto     = 60 / s_min          (fixo, independe de N)

Hot-reload: se o routes.json mudar (a web adiciona/remove consultas), o monitor
recarrega sozinho no próximo ciclo, sem precisar reiniciar.

Uso:
    ./monitor.sh --from GYN --to JPA --date 2026-11-21          (1 rota)
    ./monitor.sh --routes-file routes.json                     (N rotas)
Parar: Ctrl+C.
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

from app import routes_store
from app.notify import telegram_send, telegram_configured
from app.scrapers.google_flights import GoogleFlightsScraper
from app.normalizers.flight_normalizer import FlightNormalizer
from app.database.sqlite_client import SQLiteClient


def desktop_notify(title: str, msg: str):
    try:
        subprocess.run(["notify-send", "-u", "critical", title, msg],
                       timeout=5, check=False)
    except Exception:
        pass


def hms() -> str:
    return datetime.now().strftime("%H:%M:%S")


def money(v, cur="BRL") -> str:
    return f"{cur} {v:.0f}" if v is not None else "—"


def interruptible_sleep(seconds: float):
    end = time.time() + seconds
    while True:
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(0.5, left))


class Route:
    def __init__(self, spec: dict, defaults: dict):
        origin = spec.get("from") or spec.get("origin")
        destination = spec.get("to") or spec.get("destination")
        if not origin or not destination or not spec.get("date"):
            raise ValueError(f"rota inválida (precisa from/to/date): {spec}")
        self.origin = str(origin).upper()
        self.destination = str(destination).upper()
        self.date = str(spec["date"])
        self.trip = spec.get("trip", defaults["trip"])
        self.return_date = spec.get("return_date") or spec.get("return")
        self.seat = spec.get("seat", defaults["seat"])
        self.max_stops = spec.get("max_stops", defaults["max_stops"])
        self.threshold = spec.get("threshold", defaults["threshold"])
        self.best = None
        self.fails = 0
        self.next_due = 0.0

    @property
    def label(self) -> str:
        rt = f" / volta {self.return_date}" if (self.trip == "roundtrip" and self.return_date) else ""
        return f"{self.origin}->{self.destination} {self.date}{rt}"


def build_routes(specs, defaults) -> list:
    out = []
    for s in specs:
        try:
            out.append(Route(s, defaults))
        except Exception as e:
            print(f"{hms()} ⚠️  {e}")
    return out


def compute_params(N, T, s_min):
    N = max(N, 1)
    target_gap = max(T / N, s_min)
    eff_interval = max(T, N * s_min)
    return target_gap, eff_interval, 60.0 / s_min, N * (86400.0 / eff_interval)


def check_route(r: Route, scraper, db):
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        raw = scraper.scrape(r.origin, r.destination, r.date, r.trip,
                             r.return_date, r.seat, r.max_stops)
        flights = FlightNormalizer.normalize_items(raw)
    except Exception as e:
        print(f"{hms()} ⚠️  {r.label}: erro — {e}")
        return None
    if not flights:
        return None

    db.merge_flights(flights, f"mon-{int(time.time())}")
    cheapest = min(flights, key=lambda x: x["price"])
    price = cheapest["price"]
    db.record_price_point(r.origin, r.destination, r.date, r.trip, price,
                          cheapest.get("airline", ""), len(flights), checked_at,
                          return_date=r.return_date)

    air = cheapest.get("airline", "")
    if r.best is None:
        r.best, tag = price, "  (1º registro)"
        if r.threshold and price <= r.threshold:
            telegram_send(f"🎯 <b>{r.label}</b>\nJá está em <b>{money(price)}</b> ({air}), "
                          f"abaixo do alvo {money(r.threshold)}.")
    elif price < r.best:
        drop = r.best - price
        tag = f"  🔻 CAIU {money(drop)} (era {money(r.best)})"
        desktop_notify(f"✈️ Caiu: {r.label}", f"{money(price)} ({air}) — -{money(drop)}")
        sys.stdout.write("\a")
        hit = (f"\n🎯 <b>Abaixo do alvo {money(r.threshold)}!</b>"
               if (r.threshold and price <= r.threshold) else "")
        telegram_send(f"✈️ <b>{r.label}</b>\nCaiu para <b>{money(price)}</b> ({air}) "
                      f"— economia de {money(drop)}.{hit}")
        r.best = price
    elif price > r.best:
        tag = f"  (subiu; mín {money(r.best)})"
    else:
        tag = f"  (estável no mín {money(r.best)})"

    print(f"{hms()} {r.label:26} 💲 {money(price):>10}  "
          f"{cheapest.get('airline', '')[:16]:16} [{len(flights)} voos]{tag}")

    if r.threshold and price <= r.threshold:
        desktop_notify(f"🎯 Alvo: {r.label}", f"{money(price)} <= {money(r.threshold)}")
        sys.stdout.write("\a")
        print(f"        🎯 alvo atingido: {money(price)} <= {money(r.threshold)}")
    return price


def main():
    ap = argparse.ArgumentParser(description="Monitor de preços 1..N rotas (Google Flights)")
    ap.add_argument("--from", dest="origin", help="IATA origem (ex: GYN)")
    ap.add_argument("--to", dest="destination", help="IATA destino (ex: JPA)")
    ap.add_argument("--date", help="Data de ida YYYY-MM-DD")
    ap.add_argument("--return", dest="return_date", default=None)
    ap.add_argument("--routes-file", default=None, help="JSON com lista de rotas (hot-reload)")
    ap.add_argument("--trip", default="oneway", choices=["oneway", "roundtrip"])
    ap.add_argument("--seat", default="economy",
                    choices=["economy", "premium-economy", "business", "first"])
    ap.add_argument("--max-stops", type=int, default=None)
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--interval", type=float, default=30.0, help="T: min entre checagens da mesma rota")
    ap.add_argument("--min-gap", type=float, default=15.0, help="s_min: seg mínimos entre requests")
    ap.add_argument("--jitter", type=float, default=0.25)
    ap.add_argument("--max-checks", type=int, default=0)
    args = ap.parse_args()

    defaults = {"trip": args.trip, "seat": args.seat,
                "max_stops": args.max_stops, "threshold": args.threshold}

    routes_file = args.routes_file
    if routes_file:
        specs = routes_store.load(routes_file)
        routes_mtime = os.path.getmtime(routes_file) if os.path.exists(routes_file) else None
    elif args.origin and args.destination and args.date:
        specs = [{"from": args.origin, "to": args.destination, "date": args.date,
                  "trip": args.trip, "seat": args.seat, "max_stops": args.max_stops,
                  "return_date": args.return_date, "threshold": args.threshold}]
        routes_mtime = None
    else:
        sys.exit("Defina --routes-file OU --from/--to/--date.")

    T = max(args.interval, 0.05) * 60.0
    s_min = max(args.min_gap, 3.0)
    jitter = min(max(args.jitter, 0.0), 0.9)
    scraper = GoogleFlightsScraper()
    db = SQLiteClient()

    routes = build_routes(specs, defaults)
    target_gap, eff_interval, ceiling, est_day = compute_params(len(routes), T, s_min)
    now = time.time()
    for i, r in enumerate(routes):
        r.best = db.historical_min(r.origin, r.destination, r.date, r.trip)
        r.next_due = now + i * target_gap

    print(f"🛫 Monitorando {len(routes)} rota(s) — T={T/60:.0f}min/rota, s_min={s_min:.0f}s, "
          f"jitter ±{int(jitter*100)}%")
    print(f"   gap=max(T/N,s_min)={target_gap:.0f}s | recheca ~{eff_interval/60:.0f}min | "
          f"teto {ceiling:.1f} req/min | ~{est_day:.0f} req/dia")
    if routes_file:
        print(f"   rotas em {routes_file} (recarrega sozinho se mudar)")
    print("   (Ctrl+C para parar)\n")

    if telegram_configured():
        telegram_send(f"✈️ FlightZone iniciado — monitorando {len(routes)} rota(s).")

    last_req = 0.0
    backoff = 1.0
    backoff_cap = 8.0
    checks = 0

    try:
        while True:
            # hot-reload do routes.json
            if routes_file and os.path.exists(routes_file):
                m = os.path.getmtime(routes_file)
                if m != routes_mtime:
                    routes_mtime = m
                    routes = build_routes(routes_store.load(routes_file), defaults)
                    target_gap, eff_interval, ceiling, est_day = compute_params(len(routes), T, s_min)
                    now = time.time()
                    for i, r in enumerate(routes):
                        r.best = db.historical_min(r.origin, r.destination, r.date, r.trip)
                        r.next_due = now + i * target_gap
                    print(f"{hms()} 🔁 routes.json recarregado: {len(routes)} rota(s), "
                          f"gap {target_gap:.0f}s, recheca ~{eff_interval/60:.0f}min, "
                          f"teto {ceiling:.1f}/min")

            if not routes:
                interruptible_sleep(20)  # nada a monitorar; aguarda rotas
                continue

            r = min(routes, key=lambda x: x.next_due)
            gap = max(target_gap, s_min) * backoff * (1 + random.uniform(-jitter, jitter))
            wake = max(r.next_due, last_req + gap)
            # espera, mas acorda cedo se o routes.json mudar (hot-reload responsivo)
            while time.time() < wake:
                if routes_file and os.path.exists(routes_file) \
                        and os.path.getmtime(routes_file) != routes_mtime:
                    break
                time.sleep(min(1.0, max(wake - time.time(), 0)))
            if routes_file and os.path.exists(routes_file) \
                    and os.path.getmtime(routes_file) != routes_mtime:
                continue  # recarrega no topo do loop

            price = check_route(r, scraper, db)
            last_req = time.time()

            if price is not None:
                r.fails = 0
                r.next_due = last_req + T * (1 + random.uniform(-jitter, jitter))
                backoff = max(1.0, backoff * 0.5)
            else:
                r.fails += 1
                backoff = min(backoff * 2, backoff_cap)
                penalty = min(T * (2 ** r.fails), max(T * 4, 7200))
                r.next_due = last_req + penalty
                print(f"{hms()} 🚧 {r.label}: sem resultado (falha #{r.fails}) — "
                      f"backoff global x{backoff:.0f}, próxima em ~{penalty/60:.0f}min")

            checks += 1
            if args.max_checks and checks >= args.max_checks:
                print(f"\n✔️  {checks} checagens concluídas.")
                break
    except KeyboardInterrupt:
        pass

    print("\n👋 Monitor encerrado. Menores preços registrados:")
    for r in routes:
        print(f"     • {r.label}: {money(r.best)}")


if __name__ == "__main__":
    main()
