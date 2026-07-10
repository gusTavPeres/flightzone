#!/usr/bin/env bash
# Instalador portátil do FlightZone — roda NA máquina de destino (ex.: gustavopc).
# Cria o venv, instala dependências e sobe os serviços (monitor + web) via systemd
# de usuário, com restart automático e linger (sobrevive a reboot).
#
# Uso:   cd ~/flightzone && ./install.sh
# Opcional: HOST=0.0.0.0 ./install.sh   (expõe a web na VPN, p/ acessar de outro PC)
set -e
cd "$(dirname "$0")"
PROJ="$PWD"
PY="$PROJ/.venv/bin/python"
U="$(id -u)"
HOSTBIND="${HOST:-127.0.0.1}"
PORTBIND="${PORT:-8080}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$U}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

echo "▶ Instalando FlightZone em: $PROJ"

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
command -v xvfb-run >/dev/null 2>&1 || \
  echo "  ⚠️  xvfb-run ausente — instale com: sudo apt install -y xvfb  (necessário p/ o 'preço real')"

# 2) serviços systemd (modo usuário)
mkdir -p "$HOME/.config/systemd/user"

cat > "$HOME/.config/systemd/user/flightzone-realprice.service" <<UNIT
[Unit]
Description=FlightZone - monitor de PRECO REAL (navegador sob xvfb)
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

cat > "$HOME/.config/systemd/user/flightzone-web.service" <<UNIT
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

cat > "$HOME/.config/systemd/user/flightzone-alert@.service" <<UNIT
[Unit]
Description=FlightZone - alerta de falha (%i)
[Service]
Type=oneshot
WorkingDirectory=$PROJ
ExecStart=$PY $PROJ/service_alert.py %i
UNIT

systemctl --user disable --now flightzone-monitor 2>/dev/null || true   # aposenta o monitor leve
systemctl --user daemon-reload
systemctl --user enable flightzone-realprice flightzone-web
systemctl --user restart flightzone-realprice flightzone-web   # restart p/ recarregar código novo
loginctl enable-linger "$(whoami)" 2>/dev/null || true

echo "  ✓ serviços:"
systemctl --user is-active flightzone-realprice flightzone-web | sed 's/^/    /'
echo
echo "✅ Pronto. Web em http://$HOSTBIND:$PORTBIND"
echo "   Alertas no Telegram:  $PY telegram_setup.py <SEU_TOKEN>"
