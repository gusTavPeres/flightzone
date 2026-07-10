"""
FlightZone Local — API Flask para coletar passagens via Google Flights.

Mantém a mesma ideia do projeto original (endpoints /health, /collect, /stats),
mas roda 100% local: grava em SQLite em vez de BigQuery e coleta do
Google Flights em vez da Decolar (que é bloqueada por antibot).

Subir o servidor:   ./.venv/bin/python -m app.main
                    (ou ./run.sh)
"""
import csv
import io
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from flask import Flask, jsonify, request, Response, redirect

from app.config import Config
from app import routes_store
from app.scrapers.google_flights import GoogleFlightsScraper
from app.normalizers.flight_normalizer import FlightNormalizer
from app.database.sqlite_client import SQLiteClient
from app.dashboard import render_dashboard, render_history, render_roundtrip, render_realprice
from app.browser_scraper import scrape_cheapest
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def create_app():
    app = Flask(__name__)
    db = SQLiteClient()
    db.ensure_tables_exist()
    logger.info(f"Banco local: {Config.DB_PATH}")

    @app.get("/")
    def dashboard():
        origin = (request.args.get("origin") or "").upper()
        dest = (request.args.get("dest") or request.args.get("destination") or "").upper()
        if not origin or not dest:
            det = db.detected_trip()
            origin = origin or (det[0] if det else "GYN")
            dest = dest or (det[1] if det else "JPA")
        routes = routes_store.load(Config.ROUTES_PATH)
        return Response(render_dashboard(db, origin, dest, routes,
                                         request.args.get("msg")), mimetype="text/html")

    @app.get("/history")
    def history():
        origin = (request.args.get("origin") or "").upper()
        dest = (request.args.get("dest") or request.args.get("destination") or "").upper()
        hours = int(request.args.get("hours", 24))
        if not origin or not dest:
            det = db.detected_trip()
            origin = origin or (det[0] if det else "GYN")
            dest = dest or (det[1] if det else "JPA")
        return Response(render_history(db, origin, dest, hours), mimetype="text/html")

    @app.get("/roundtrip")
    def roundtrip():
        origin = (request.args.get("origin") or "").upper()
        dest = (request.args.get("dest") or request.args.get("destination") or "").upper()
        if not origin or not dest:
            det = db.detected_trip()
            origin = origin or (det[0] if det else "GYN")
            dest = dest or (det[1] if det else "JPA")
        return Response(render_roundtrip(db, origin, dest), mimetype="text/html")

    # 1 scrape por vez: cada /realprice abre um Chrome (~500 MB por ~40 s)
    realprice_lock = threading.Lock()

    @app.get("/realprice")
    def realprice():
        import time as _time
        origin = (request.args.get("origin") or "").upper()
        dest = (request.args.get("dest") or "").upper()
        date = request.args.get("date") or ""
        rdate = request.args.get("return_date") or None
        if not (origin and dest and date):
            return redirect("/?msg=" + quote("Faltam parâmetros para o preço real."))
        if not realprice_lock.acquire(blocking=False):
            return redirect("/?msg=" + quote("Já há uma leitura de preço real em andamento — "
                                             "aguarde ~1 min e tente de novo."))
        t0 = _time.time()
        try:
            price = scrape_cheapest(origin, dest, date, rdate)
        except Exception as e:
            logger.error(f"erro no preço real: {e}")
            price = None
        finally:
            realprice_lock.release()
        return Response(render_realprice(origin, dest, date, rdate, price,
                                         round(_time.time() - t0)), mimetype="text/html")

    @app.post("/routes/add")
    def routes_add():
        f = request.form
        origin = (f.get("origin") or "").strip().upper()
        dest = (f.get("dest") or "").strip().upper()
        date = (f.get("date") or "").strip()
        trip = f.get("trip") or "oneway"
        if not (origin and dest and date):
            return redirect("/?msg=" + quote("Preencha origem, destino e data."))
        route = {"from": origin, "to": dest, "date": date, "trip": trip}
        if trip == "roundtrip" and (f.get("return_date") or "").strip():
            route["return_date"] = f.get("return_date").strip()
        if (f.get("max_stops") or "") != "":
            try:
                route["max_stops"] = int(f.get("max_stops"))
            except ValueError:
                pass
        if (f.get("threshold") or "").strip():
            try:
                route["threshold"] = float(f.get("threshold"))
            except ValueError:
                pass
        _, m = routes_store.add(Config.ROUTES_PATH, route)
        return redirect("/?msg=" + quote(m))

    @app.post("/routes/remove")
    def routes_remove():
        try:
            i = int(request.form.get("index"))
        except (TypeError, ValueError):
            return redirect("/?msg=" + quote("Índice inválido."))
        _, m = routes_store.remove_index(Config.ROUTES_PATH, i)
        return redirect("/?msg=" + quote(m))

    @app.get("/health")
    def health():
        return jsonify({"status": "healthy", "db": Config.DB_PATH})

    @app.route("/collect", methods=["POST", "GET"])
    def collect():
        """Coleta voos. Aceita parâmetros via JSON (POST) OU query string (GET),
        o que facilita testar direto no navegador:
            http://127.0.0.1:8080/collect?origin=GRU&destination=GIG&date=2026-07-15
        """
        execution_id = str(uuid.uuid4())
        start = datetime.now(timezone.utc)
        body = request.get_json(silent=True) or {}

        def pick(key, default=None):
            return body.get(key) or request.args.get(key) or default

        origin = (pick("origin") or Config.DEFAULT_ORIGIN).upper()
        destination = (pick("destination") or Config.DEFAULT_DESTINATION).upper()
        date = pick("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        trip_type = pick("trip_type") or Config.DEFAULT_TRIP_TYPE
        return_date = pick("return_date")
        seat = pick("seat") or Config.DEFAULT_SEAT
        max_stops = pick("max_stops")
        max_stops = int(max_stops) if str(max_stops or "").isdigit() else None

        logger.info(f"[{execution_id[:8]}] coleta {origin}->{destination} {date} ({trip_type})")

        try:
            raw = GoogleFlightsScraper().scrape(
                origin, destination, date, trip_type, return_date, seat, max_stops
            )
            normalized = FlightNormalizer.normalize_items(raw)
            inserted, deduped = db.merge_flights(normalized, execution_id)
            end = datetime.now(timezone.utc)

            db.log_execution(
                execution_id=execution_id, start_time=start.isoformat(),
                end_time=end.isoformat(), items_collected=len(raw),
                items_inserted=inserted, items_deduplicated=deduped,
                status="success", origin=origin, destination=destination,
                departure_date=date,
            )
            return jsonify({
                "execution_id": execution_id,
                "status": "success",
                "route": f"{origin}->{destination}",
                "date": date,
                "trip_type": trip_type,
                "items_collected": len(raw),
                "items_inserted": inserted,
                "items_deduplicated": deduped,
                "duration_seconds": round((end - start).total_seconds(), 2),
                "flights": sorted(normalized, key=lambda x: x.get("price") or 1e9),
            })
        except Exception as e:
            end = datetime.now(timezone.utc)
            logger.error(f"Erro na coleta: {e}", exc_info=True)
            db.log_execution(
                execution_id=execution_id, start_time=start.isoformat(),
                end_time=end.isoformat(), items_collected=0, items_inserted=0,
                items_deduplicated=0, status="error", error_message=str(e),
                origin=origin, destination=destination, departure_date=date,
            )
            return jsonify({"execution_id": execution_id, "status": "error", "error": str(e)}), 500

    @app.get("/stats")
    def stats():
        origin = request.args.get("origin", "")
        destination = request.args.get("destination", "")
        hours = int(request.args.get("hours", 24))
        return jsonify({"hours": hours, "routes": db.stats(origin, destination, hours)})

    @app.get("/flights")
    def flights():
        origin = request.args.get("origin", "")
        destination = request.args.get("destination", "")
        limit = int(request.args.get("limit", 50))
        return jsonify({"flights": db.recent_flights(origin, destination, limit)})

    @app.get("/export.csv")
    def export_csv():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["origem", "destino", "ida", "volta", "tipo", "menor_preco_BRL", "atualizado"])
        for r in db.summary_rows():
            tipo = "ida-e-volta" if r["trip_type"] == "roundtrip" else "so-ida"
            atualizado = (r["ultima"] or "")[:16].replace("T", " ")
            w.writerow([r["origin"], r["destination"], r["departure_date"],
                        r["return_date"] or "", tipo, int(r["menor"]), atualizado])
        return Response(
            buf.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=precos.csv"},
        )

    return app


app = create_app()

if __name__ == "__main__":
    logger.info(f"Servidor em http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, threaded=True)
