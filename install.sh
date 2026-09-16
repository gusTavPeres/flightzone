#!/usr/bin/env bash
# Instalador portátil do FlightZone — roda NA máquina de destino (ex.: gustavopc).
# Cria o venv, instala dependências e sobe TODOS os serviços/timers via systemd
# de usuário, com restart automático e linger (sobrevive a reboot).
#
# Uso:   cd ~/flightzone && ./install.sh
# Opcional: HOST=0.0.0.0 PORT=8090 ./install.sh   (expõe a web na VPN)
# Sem HOST/PORT no ambiente, PRESERVA o que já está na unit instalada
# (reinstalar não regride a configuração de produção).
set -e
cd "$(dirname "$0")"
PROJ="$PWD"
PY="$PROJ/.venv/bin/python"
U="$(id -u)"
UNITDIR="$HOME/.config/systemd/user"
WEBUNIT="$UNITDIR/flightzone-web.service"
HOSTBIND="${HOST:-$(grep -oP '(?<=^Environment=HOST=).*' "$WEBUNIT" 2>/dev/null || true)}"
PORTBIND="${PORT:-$(grep -oP '(?<=^Environment=PORT=).*' "$WEBUNIT" 2>/dev/null || true)}"
HOSTBIND="${HOSTBIND:-127.0.0.1}"
PORTBIND="${PORTBIND:-8080}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$U}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

echo "▶ Instalando FlightZone em: $PROJ (web em $HOSTBIND:$PORTBIND)"

# 1) virtualenv + dependências
if [ ! -x "$PY" ]; then
  echo "  criando virtualenv…"
  python3 -m venv .venv 2>/dev/null || {
    echo "❌ Falha ao criar o venv. Instale o pacote de venv do Python e rode de novo:"
    echo "   sudo apt install python3-venv     (Debian/Ubuntu)"
    exit 1
  }
fi
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt
echo "  ✓ dependências instaladas"
[ -f telegram.json ] && chmod 600 telegram.json   # segredo: só o dono lê
[ -f discord.json ]  && chmod 600 discord.json    # webhook do canal: idem

# 2) serviços systemd (modo usuário)
mkdir -p "$UNITDIR"

cat > "$UNITDIR/flightzone-realprice.service" <<UNIT
[Unit]
Description=FlightZone - monitor de PRECO REAL (Chrome headless)
After=network-online.target
Wants=network-online.target
OnFailure=flightzone-alert@%n.service
[Service]
Type=simple
WorkingDirectory=$PROJ
Environment=PYTHONUNBUFFERED=1
ExecStart=$PY $PROJ/realprice_monitor.py --routes-file $PROJ/routes.json --gap 16 --jitter 0.3
Restart=on-failure
RestartSec=120
[Install]
WantedBy=default.target
UNIT

cat > "$UNITDIR/flightzone-web.service" <<UNIT
[Unit]
Description=FlightZone - servidor web
After=network-online.target
OnFailure=flightzone-alert@%n.service
[Service]
Type=simple
WorkingDirectory=$PROJ
Environment=PYTHONUNBUFFERED=1
Environment=HOST=$HOSTBIND
Environment=PORT=$PORTBIND
ExecStart=$PY -m app.main
Restart=on-failure
RestartSec=10
[Install]
WantedBy=default.target
UNIT

cat > "$UNITDIR/flightzone-alert@.service" <<UNIT
[Unit]
Description=FlightZone - alerta de falha (%i)
[Service]
Type=oneshot
WorkingDirectory=$PROJ
ExecStart=$PY $PROJ/service_alert.py %i
UNIT

# oneshots + timers (heartbeat, backup, resumo diario, canario)
mkunit() {  # $1=nome $2=descricao $3=script(+args)
  cat > "$UNITDIR/flightzone-$1.service" <<UNIT
[Unit]
Description=FlightZone - $2
[Service]
Type=oneshot
WorkingDirectory=$PROJ
ExecStart=$PY $PROJ/$3
UNIT
}
mkunit heartbeat    "heartbeat"                heartbeat.py
mkunit backup       "backup do banco"          backup_db.py
mkunit dailysummary "resumo diario no Telegram" daily_summary.py
mkunit selftest     "canario (selftest ao vivo)" "selftest.py --live"

cat > "$UNITDIR/flightzone-heartbeat.timer" <<UNIT
[Unit]
Description=FlightZone - heartbeat a cada 10 min
[Timer]
OnBootSec=5min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
UNIT

cat > "$UNITDIR/flightzone-backup.timer" <<UNIT
[Unit]
Description=FlightZone - backup diario do banco
[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT

cat > "$UNITDIR/flightzone-dailysummary.timer" <<UNIT
[Unit]
Description=FlightZone - dispara o resumo as 22h
[Timer]
OnCalendar=*-*-* 22:00:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT

cat > "$UNITDIR/flightzone-selftest.timer" <<UNIT
[Unit]
Description=FlightZone - canario semanal
[Timer]
OnCalendar=Sun *-*-* 12:00:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable flightzone-realprice flightzone-web \
  flightzone-heartbeat.timer flightzone-backup.timer \
  flightzone-dailysummary.timer flightzone-selftest.timer
systemctl --user restart flightzone-realprice flightzone-web   # recarrega código novo
systemctl --user start flightzone-heartbeat.timer flightzone-backup.timer \
  flightzone-dailysummary.timer flightzone-selftest.timer
loginctl enable-linger "$(whoami)" 2>/dev/null || true

echo "  ✓ serviços:"
systemctl --user is-active flightzone-realprice flightzone-web | sed 's/^/    /'
echo
echo "✅ Pronto. Web em http://$HOSTBIND:$PORTBIND"
echo "   Alertas no Telegram:  $PY telegram_setup.py <SEU_TOKEN>"
echo "   Alertas no Discord:   echo '{\"webhook\": \"<URL_DO_WEBHOOK>\"}' > discord.json"
