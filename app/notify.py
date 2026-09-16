"""
Envio de alertas (sem dependências externas — usa urllib).

  telegram_send() -> avisos operacionais, só pro dono.
  discord_send()  -> webhook de um canal (o pessoal do Pequi vê os preços bons).
  broadcast()     -> os dois (use nos alertas de PREÇO).

A config (token + chat_id) vem de:
  1) variáveis de ambiente TELEGRAM_TOKEN / TELEGRAM_CHAT_ID, ou
  2) o arquivo telegram.json (criado por telegram_setup.py).
O Discord vem de DISCORD_WEBHOOK/DISCORD_ROLE_ID ou de discord.json:
  {"webhook": "https://...", "role_id": "123456789"}   <- role_id é opcional
Se nada estiver configurado, as funções viram no-op (não quebram o monitor).
"""
import json
import os
import re
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


def _discord_cfg():
    """(webhook, role_id) — env vence o arquivo; role_id opcional (None = não marca ninguém)."""
    hook, role = os.getenv("DISCORD_WEBHOOK"), os.getenv("DISCORD_ROLE_ID")
    if not hook and os.path.exists(Config.DISCORD_PATH):
        try:
            with open(Config.DISCORD_PATH, encoding="utf-8") as f:
                d = json.load(f)
            hook = d.get("webhook") or None
            role = role or d.get("role_id") or None
        except Exception:
            pass
    return hook, (str(role) if role else None)


def discord_configured() -> bool:
    return bool(_discord_cfg()[0])


def _md(text: str) -> str:
    """HTML do Telegram -> markdown do Discord (usamos só <b> e <a href>)."""
    text = re.sub(r'<a href="([^"]+)">([^<]*)</a>',
                  lambda m: f"[{m.group(2)}](<{m.group(1).replace('&amp;', '&')}>)", text)
    return re.sub(r"</?b>", "**", text)


def _payload(text: str, role=None) -> dict:
    """Corpo do POST. Com role_id, marca o cargo e restringe allowed_mentions a ele
    (sem isso o @everyone/@here de um texto qualquer poderia vazar)."""
    body = {"content": ((f"<@&{role}> " if role else "") + _md(text))[:1900]}  # limite: 2000
    body["allowed_mentions"] = {"parse": [], "roles": [role]} if role else {"parse": []}
    return body


def discord_send(text: str) -> bool:
    """Posta o alerta no canal via webhook. No-op silencioso se não configurado."""
    hook, role = _discord_cfg()
    if not hook:
        return False
    data = json.dumps(_payload(text, role)).encode()
    # UA obrigatório: o Cloudflare do Discord devolve 403 pro "Python-urllib" padrão
    req = urllib.request.Request(hook, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "FlightZone (https://github.com/gusTavPeres/flightzone, 1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return getattr(r, "status", 200) in (200, 204)
    except Exception as e:
        logger.warning(f"discord_send falhou (alerta perdido): {e}")
        return False


def broadcast(text: str) -> bool:
    """Alerta de PREÇO: vai pro Telegram (dono) e pro Discord (grupo)."""
    tg = telegram_send(text)
    return discord_send(text) or tg
