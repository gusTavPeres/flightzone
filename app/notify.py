"""
Envio de alertas para o Telegram (sem dependências externas — usa urllib).

A config (token + chat_id) vem de:
  1) variáveis de ambiente TELEGRAM_TOKEN / TELEGRAM_CHAT_ID, ou
  2) o arquivo telegram.json (criado por telegram_setup.py).
Se nada estiver configurado, as funções viram no-op (não quebram o monitor).
"""
import json
import os
import urllib.parse
import urllib.request

from app.config import Config
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _config():
    tok = os.getenv("TELEGRAM_TOKEN")
    cid = os.getenv("TELEGRAM_CHAT_ID")
    if tok and cid:
        return tok, str(cid)
    path = Config.TELEGRAM_PATH
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("token") and d.get("chat_id") is not None:
                return d["token"], str(d["chat_id"])
        except Exception:
            pass
    return None, None


def telegram_configured() -> bool:
    return all(_config())


def telegram_send(text: str) -> bool:
    """Envia uma mensagem ao Telegram. Retorna False (silencioso) se não configurado/falhar."""
    tok, cid = _config()
    if not tok or not cid:
        return False
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": cid,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as r:
            return getattr(r, "status", 200) == 200
    except Exception as e:
        logger.warning(f"telegram_send falhou (alerta perdido): {e}")
        return False
