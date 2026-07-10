"""
Backup consistente do banco (SQLite online backup — seguro mesmo com o monitor
escrevendo). Mantém os últimos 7 backups em data/backups/.
Rodar via systemd timer (diário).
"""
import glob
import os
import sqlite3
from datetime import datetime

from app.config import Config

bdir = os.path.join(os.path.dirname(Config.DB_PATH), "backups")
os.makedirs(bdir, exist_ok=True)
dest = os.path.join(bdir, f"flights_{datetime.now():%Y-%m-%d}.db")

src = sqlite3.connect(Config.DB_PATH)
dst = sqlite3.connect(dest)
with dst:
    src.backup(dst)
src.close()
dst.close()

files = sorted(glob.glob(os.path.join(bdir, "flights_*.db")))
for f in files[:-7]:          # mantém só os 7 mais recentes
    os.remove(f)
print(f"✅ backup: {dest} ({os.path.getsize(dest) // 1024} KB) · "
      f"{min(len(files), 7)} backup(s) guardado(s)")
