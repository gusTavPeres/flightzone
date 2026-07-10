"""
Heartbeat — roda a cada ~10 min (systemd timer). Se o monitor não registra preço
há muito tempo (travou vivo, sem crash), avisa no Telegram. Avisa também quando
volta ao normal. Usa um flag em disco pra não repetir o alerta.

STALL_MIN=50 (> a pausa de bloqueio de 45 min, p/ não dar falso alarme).
"""
import os
import sqlite3
from datetime import datetime, timezone

from app.config import Config
from app.notify import telegram_send

STALL_MIN = float(os.getenv("STALL_MIN", "50"))
FLAG = os.path.join(os.path.dirname(Config.DB_PATH), ".heartbeat_alerted")

c = sqlite3.connect(Config.DB_PATH)
last = c.execute("SELECT MAX(checked_at) FROM price_history").fetchone()[0]
c.close()

if last:
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 60
else:
    age = 1e9
alerted = os.path.exists(FLAG)

if age > STALL_MIN:
    if not alerted:
        telegram_send(f"⚠️ <b>FlightZone</b>: o monitor não registra preço há "
                      f"<b>{age:.0f} min</b> — pode ter travado! Cheque o gustavopc.")
        open(FLAG, "w").close()
    print(f"STALL: {age:.0f} min sem raspagem")
else:
    if alerted:
        telegram_send(f"✅ <b>FlightZone</b>: monitor voltou ao normal (última há {age:.0f} min).")
        os.remove(FLAG)
    print(f"OK: última raspagem há {age:.1f} min")
