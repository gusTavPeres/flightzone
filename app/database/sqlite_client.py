"""
Armazenamento local em SQLite — substitui o cliente BigQuery do projeto original.

- Deduplicação automática via coluna UNIQUE(dedupe_key) + INSERT OR IGNORE
  (equivalente local ao MERGE do BigQuery).
- Tabela de logs de execução, como no original.
- Zero dependências externas / zero nuvem / zero custo.
"""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple

from app.config import Config
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

FLIGHTS_DDL = """
CREATE TABLE IF NOT EXISTS flights (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source           TEXT,
    trip_type        TEXT,
    origin           TEXT,
    destination      TEXT,
    departure_date   TEXT,
    airline          TEXT,
    price            REAL,
    currency         TEXT,
    departure_time   TEXT,
    arrival_time     TEXT,
    duration_minutes INTEGER,
    stops            INTEGER,
    cabin_class      TEXT,
    plane_type       TEXT,
    dedupe_key       TEXT UNIQUE,
    execution_id     TEXT,
    collected_at     TEXT,
    inserted_at      TEXT
);
"""

LOGS_DDL = """
CREATE TABLE IF NOT EXISTS execution_logs (
    execution_id        TEXT PRIMARY KEY,
    start_time          TEXT,
    end_time            TEXT,
    items_collected     INTEGER,
    items_inserted      INTEGER,
    items_deduplicated  INTEGER,
    status              TEXT,
    error_message       TEXT,
    origin              TEXT,
    destination         TEXT,
    departure_date      TEXT
);
"""

PRICE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS price_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at      TEXT,
    origin          TEXT,
    destination     TEXT,
    departure_date  TEXT,
    return_date     TEXT,
    trip_type       TEXT,
    cheapest_price  REAL,
    airline         TEXT,
    total_results   INTEGER
);
"""


class SQLiteClient:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        # timeout=15 -> espera o lock em vez de estourar "database is locked"
        # (a web LÊ enquanto o monitor ESCREVE no mesmo arquivo)
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with closing(self._conn()) as c, c:
            # WAL: leitores não bloqueiam o escritor (e vice-versa); é persistente no arquivo
            c.execute("PRAGMA journal_mode=WAL")
            c.execute(FLIGHTS_DDL)
            c.execute(LOGS_DDL)
            c.execute(PRICE_HISTORY_DDL)
            c.execute("CREATE INDEX IF NOT EXISTS idx_route ON flights(origin,destination,departure_date)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_collected ON flights(collected_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_ph_route ON price_history(origin,destination,departure_date)")
            # cobre as subqueries "última leitura" (ORDER BY checked_at DESC LIMIT 1)
            c.execute("CREATE INDEX IF NOT EXISTS idx_ph_route_time ON "
                      "price_history(origin,destination,departure_date,checked_at)")
            cols = [r[1] for r in c.execute("PRAGMA table_info(price_history)").fetchall()]
            if "return_date" not in cols:  # migração p/ bancos antigos
                c.execute("ALTER TABLE price_history ADD COLUMN return_date TEXT")

    def ensure_tables_exist(self) -> bool:
        self._init_db()
        return True

    def merge_flights(self, rows: List[Dict], execution_id: str) -> Tuple[int, int]:
        """Insere voos, ignorando duplicados (mesmo dedupe_key).
        Retorna (novos_inseridos, duplicados_ignorados)."""
        if not rows:
            return 0, 0
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        with closing(self._conn()) as c, c:
            for r in rows:
                cur = c.execute(
                    """
                    INSERT OR IGNORE INTO flights
                    (source, trip_type, origin, destination, departure_date, airline,
                     price, currency, departure_time, arrival_time, duration_minutes,
                     stops, cabin_class, plane_type, dedupe_key, execution_id,
                     collected_at, inserted_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        r.get("source", "google_flights"), r.get("trip_type", "oneway"),
                        r.get("origin", ""), r.get("destination", ""), r.get("departure_date", ""),
                        r.get("airline", ""), float(r["price"]), r.get("currency", "BRL"),
                        r.get("departure_time"), r.get("arrival_time"),
                        r.get("duration_minutes"), r.get("stops"),
                        r.get("cabin_class", "economy"), r.get("plane_type"),
                        r["dedupe_key"], execution_id,
                        r.get("collected_at") or now, now,
                    ),
                )
                inserted += cur.rowcount  # 1 = inserido, 0 = duplicado ignorado
        return inserted, len(rows) - inserted

    def log_execution(self, **kw):
        with closing(self._conn()) as c, c:
            c.execute(
                """
                INSERT OR REPLACE INTO execution_logs
                (execution_id, start_time, end_time, items_collected, items_inserted,
                 items_deduplicated, status, error_message, origin, destination, departure_date)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    kw.get("execution_id"), kw.get("start_time"), kw.get("end_time"),
                    kw.get("items_collected", 0), kw.get("items_inserted", 0),
                    kw.get("items_deduplicated", 0), kw.get("status", "success"),
                    kw.get("error_message"), kw.get("origin"),
                    kw.get("destination"), kw.get("departure_date"),
                ),
            )

    def stats(self, origin: str = "", destination: str = "", hours: int = 24) -> List[Dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        where, params = ["collected_at >= ?"], [since]
        if origin:
            where.append("origin = ?"); params.append(origin.upper())
        if destination:
            where.append("destination = ?"); params.append(destination.upper())
        sql = f"""
            SELECT origin, destination,
                   COUNT(*)               AS total_flights,
                   MIN(price)             AS cheapest_price,
                   ROUND(AVG(price), 2)   AS avg_price,
                   COUNT(DISTINCT airline) AS airlines_count,
                   MIN(stops)             AS min_stops
            FROM flights
            WHERE {' AND '.join(where)}
            GROUP BY origin, destination
            ORDER BY cheapest_price ASC
        """
        with closing(self._conn()) as c:
            return [dict(row) for row in c.execute(sql, params).fetchall()]

    def recent_flights(self, origin: str = "", destination: str = "", limit: int = 50) -> List[Dict]:
        where, params = [], []
        if origin:
            where.append("origin = ?"); params.append(origin.upper())
        if destination:
            where.append("destination = ?"); params.append(destination.upper())
        wsql = ("WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        sql = f"SELECT * FROM flights {wsql} ORDER BY price ASC LIMIT ?"
        with closing(self._conn()) as c:
            return [dict(row) for row in c.execute(sql, params).fetchall()]

    # ---- usados pelo monitor de preços (monitor.py) ----

    def record_price_point(self, origin, destination, departure_date, trip_type,
                           cheapest_price, airline, total_results, checked_at=None,
                           return_date=None):
        """Registra um ponto na série temporal de preços (1 linha por verificação)."""
        checked_at = checked_at or datetime.now(timezone.utc).isoformat()
        with closing(self._conn()) as c, c:
            c.execute(
                """INSERT INTO price_history
                   (checked_at, origin, destination, departure_date, return_date, trip_type,
                    cheapest_price, airline, total_results)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (checked_at, origin.upper(), destination.upper(), departure_date, return_date,
                 trip_type, float(cheapest_price), airline, int(total_results)),
            )

    def roundtrip_matrix(self, origin, destination):
        """Cada combo casado: preço ATUAL (última leitura) + menor já visto."""
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute(
                """SELECT departure_date, return_date,
                          (SELECT cheapest_price FROM price_history p2
                           WHERE p2.origin=p1.origin AND p2.destination=p1.destination
                                 AND p2.departure_date=p1.departure_date
                                 AND p2.return_date=p1.return_date AND p2.trip_type='roundtrip'
                           ORDER BY checked_at DESC LIMIT 1) AS price,
                          MIN(cheapest_price) AS min_price,
                          COUNT(*) AS checks, MAX(checked_at) AS last_checked
                   FROM price_history p1
                   WHERE origin=? AND destination=? AND trip_type='roundtrip'
                         AND return_date IS NOT NULL
                   GROUP BY departure_date, return_date
                   ORDER BY departure_date, return_date""",
                (origin.upper(), destination.upper())).fetchall()]

    def historical_min(self, origin, destination, departure_date, trip_type):
        """Menor preço já observado para a rota/data (para 'lembrar' entre reinícios)."""
        with closing(self._conn()) as c:
            row = c.execute(
                """SELECT MIN(price) FROM flights
                   WHERE origin=? AND destination=? AND departure_date=? AND trip_type=?""",
                (origin.upper(), destination.upper(), departure_date, trip_type),
            ).fetchone()
        return row[0] if row and row[0] is not None else None

    def price_history_min(self, origin, destination, date, trip, return_date=None):
        """Menor preço REAL já registrado para o combo exato (inclui return_date)."""
        with closing(self._conn()) as c:
            if return_date:
                row = c.execute(
                    """SELECT MIN(cheapest_price) FROM price_history
                       WHERE origin=? AND destination=? AND departure_date=?
                             AND trip_type=? AND return_date=?""",
                    (origin.upper(), destination.upper(), str(date), trip, str(return_date))).fetchone()
            else:
                row = c.execute(
                    """SELECT MIN(cheapest_price) FROM price_history
                       WHERE origin=? AND destination=? AND departure_date=? AND trip_type=?
                             AND (return_date IS NULL OR return_date='')""",
                    (origin.upper(), destination.upper(), str(date), trip)).fetchone()
        return row[0] if row and row[0] is not None else None

    def summary_rows(self):
        """Resumo enxuto p/ o CSV: 1 linha por combo, menor preço, ordenado."""
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute(
                """SELECT origin, destination, departure_date, return_date, trip_type,
                          MIN(cheapest_price) AS menor, MAX(checked_at) AS ultima
                   FROM price_history
                   GROUP BY origin, destination, departure_date, return_date, trip_type
                   ORDER BY menor ASC""").fetchall()]

    def recent_stats(self, origin, destination, date, trip, return_date=None, days=7):
        """(média, nº de leituras) das últimas `days` dias — p/ detectar tarifa-erro."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with closing(self._conn()) as c:
            if return_date:
                row = c.execute(
                    """SELECT AVG(cheapest_price), COUNT(*) FROM price_history
                       WHERE origin=? AND destination=? AND departure_date=?
                             AND trip_type=? AND return_date=? AND checked_at>=?""",
                    (origin.upper(), destination.upper(), str(date), trip,
                     str(return_date), since)).fetchone()
            else:
                row = c.execute(
                    """SELECT AVG(cheapest_price), COUNT(*) FROM price_history
                       WHERE origin=? AND destination=? AND departure_date=? AND trip_type=?
                             AND (return_date IS NULL OR return_date='') AND checked_at>=?""",
                    (origin.upper(), destination.upper(), str(date), trip, since)).fetchone()
        return (row[0], row[1]) if row and row[0] is not None else (None, 0)

    def deal_score(self, origin, destination, date, trip, price, return_date=None, days=30):
        """Fração das leituras dos últimos `days` dias MAIS CARAS que `price`
        (quanto maior, melhor o negócio agora). Retorna (frac, n_leituras)."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        expr = "AVG(CASE WHEN cheapest_price > ? THEN 1.0 ELSE 0.0 END), COUNT(*)"
        with closing(self._conn()) as c:
            if return_date:
                row = c.execute(
                    f"""SELECT {expr} FROM price_history
                        WHERE origin=? AND destination=? AND departure_date=?
                              AND trip_type=? AND return_date=? AND checked_at>=?""",
                    (price, origin.upper(), destination.upper(), str(date),
                     trip, str(return_date), since)).fetchone()
            else:
                row = c.execute(
                    f"""SELECT {expr} FROM price_history
                        WHERE origin=? AND destination=? AND departure_date=? AND trip_type=?
                              AND (return_date IS NULL OR return_date='') AND checked_at>=?""",
                    (price, origin.upper(), destination.upper(), str(date), trip, since)).fetchone()
        return (row[0], row[1]) if row and row[1] else (None, 0)

    def health(self):
        """Saúde do sistema: última raspagem, leituras nas 24h, total."""
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        with closing(self._conn()) as c:
            last = c.execute("SELECT MAX(checked_at) FROM price_history").fetchone()[0]
            n24 = c.execute("SELECT COUNT(*) FROM price_history WHERE checked_at>=?",
                            (since,)).fetchone()[0]
            total = c.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        return {"last": last, "n24": n24, "total": total}

    # ---- usados pelo dashboard (app/dashboard.py) ----

    def price_by_date(self, origin, destination) -> list:
        """Por data: preço ATUAL (última leitura) + menor já visto + nº de checagens."""
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute(
                """SELECT departure_date AS date,
                          (SELECT cheapest_price FROM price_history p2
                           WHERE p2.origin=p1.origin AND p2.destination=p1.destination
                                 AND p2.departure_date=p1.departure_date AND p2.trip_type='oneway'
                           ORDER BY checked_at DESC LIMIT 1) AS price,
                          MIN(cheapest_price) AS min_price,
                          COUNT(*) AS checks, MAX(checked_at) AS last_checked
                   FROM price_history p1
                   WHERE origin=? AND destination=? AND trip_type='oneway'
                   GROUP BY departure_date ORDER BY departure_date""",
                (origin.upper(), destination.upper())).fetchall()]

    def price_series(self, origin, destination, date) -> list:
        """Série temporal (checked_at, preço) de uma data — para o mini-gráfico."""
        with closing(self._conn()) as c:
            return [(r[0], r[1]) for r in c.execute(
                """SELECT checked_at, cheapest_price FROM price_history
                   WHERE origin=? AND destination=? AND departure_date=?
                   ORDER BY checked_at""",
                (origin.upper(), destination.upper(), str(date))).fetchall()]

    def detected_trip(self):
        """Detecta o par ida/volta com mais dados (para abrir o dashboard nele)."""
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT origin, destination, COUNT(*) n FROM price_history "
                "GROUP BY origin, destination").fetchall()
        counts = {(r[0], r[1]): r[2] for r in rows}
        best, best_n = None, -1
        for (o, d), n in counts.items():
            if (d, o) in counts:
                tot = n + counts[(d, o)]
                if tot > best_n:
                    best_n, best = tot, (o, d)
        return best

    def history_points(self, origin, destination, date, hours=24):
        """Série (checked_at, preço) de uma data nas últimas `hours` horas."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with closing(self._conn()) as c:
            return [(r[0], r[1]) for r in c.execute(
                """SELECT checked_at, cheapest_price FROM price_history
                   WHERE origin=? AND destination=? AND departure_date=? AND checked_at>=?
                         AND trip_type='oneway'
                   ORDER BY checked_at""",
                (origin.upper(), destination.upper(), str(date), since)).fetchall()]
