"""
Configura os alertas do Telegram — descobre seu chat_id e salva telegram.json.

PASSO A PASSO:
  1) No Telegram, fale com  @BotFather  → mande  /newbot  → siga as instruções
     e COPIE o token (algo como 123456789:AAExxxxxxxxxxxxxxxxxxxxxxxx).
  2) No Telegram, abra o seu novo bot e mande QUALQUER mensagem pra ele (ex.: "oi").
  3) Rode:
        cd ~/flightzone
        ./.venv/bin/python telegram_setup.py <SEU_TOKEN>

  Pronto: ele salva telegram.json e manda uma mensagem de teste. O monitor passa
  a enviar alertas automaticamente (não precisa reiniciar).
"""
import json
import sys
import urllib.parse
import urllib.request

from app.config import Config


def _get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    token = sys.argv[1].strip()

    try:
        data = _get(f"https://api.telegram.org/bot{token}/getUpdates")
    except Exception as e:
        print(f"❌ Erro ao falar com a API do Telegram: {e}")
        sys.exit(1)
    if not data.get("ok"):
        print(f"❌ Token inválido? Resposta: {data}")
        sys.exit(1)

    chat_id, name = None, ""
    for upd in reversed(data.get("result", [])):
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            chat_id = chat["id"]
            name = chat.get("first_name") or chat.get("title") or chat.get("username") or ""
            break

    if chat_id is None:
        print("❌ Nenhuma mensagem encontrada.\n"
              "   Abra o seu bot no Telegram, mande uma mensagem qualquer e rode de novo.")
        sys.exit(1)

    with open(Config.TELEGRAM_PATH, "w", encoding="utf-8") as f:
        json.dump({"token": token, "chat_id": chat_id}, f, indent=2)
    print(f"✅ Configuração salva em {Config.TELEGRAM_PATH}")
    print(f"   chat_id = {chat_id}  ({name})")

    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": "✅ FlightZone conectado! Você vai receber aqui os alertas de queda de preço. ✈️",
    }).encode()
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body),
            timeout=10)
        print("📨 Mensagem de teste enviada — confira o seu Telegram!")
    except Exception as e:
        print(f"⚠️ Salvou, mas falhou ao enviar a mensagem de teste: {e}")


if __name__ == "__main__":
    main()
