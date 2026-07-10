"""
Disparado pelo systemd (OnFailure=) quando um serviço do FlightZone falha.
Manda um alerta no Telegram. Uso: service_alert.py <nome-do-servico>
"""
import sys

from app.notify import telegram_send

unit = sys.argv[1] if len(sys.argv) > 1 else "desconhecido"
telegram_send(
    f"🔴 <b>FlightZone</b> — o serviço <code>{unit}</code> FALHOU (gustavopc).\n"
    f"Cheque com:  systemctl --user status {unit}"
)
