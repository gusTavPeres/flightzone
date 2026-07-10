"""
Configura a Amadeus: salva as credenciais (amadeus.json) e testa.

Uso:
  cd ~/flightzone
  ./.venv/bin/python amadeus_setup.py <API_KEY> <API_SECRET> [test|production]

  - sem o 3º argumento, assume 'test' (grátis, mas dados sandbox).
  - quando ativar produção no portal Amadeus, rode de novo com 'production'.
"""
import json
import sys

from app.config import Config


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    key, secret = sys.argv[1].strip(), sys.argv[2].strip()
    env = sys.argv[3].strip().lower() if len(sys.argv) > 3 else "test"
    if env not in ("test", "production"):
        env = "test"

    with open(Config.AMADEUS_PATH, "w", encoding="utf-8") as f:
        json.dump({"key": key, "secret": secret, "env": env}, f, indent=2)
    print(f"✅ Credenciais salvas em {Config.AMADEUS_PATH} (ambiente: {env})")
    print("Testando autenticação + uma busca de exemplo (GRU→GIG)...")

    from app import amadeus_client as ac
    try:
        r = ac.search_cheapest("GRU", "GIG", "2026-07-15")
        if r:
            print(f"✅ Funcionou! Exemplo GRU→GIG 15/07: R$ {r[0]:.0f} ({r[1]})")
            print("   Pode me avisar — eu ligo a Amadeus como motor de preço real.")
        else:
            print("⚠️ Autenticou OK, mas a busca voltou vazia.")
            print("   No ambiente 'test' isso é comum (dados sandbox). Para preços reais,")
            print("   ative 'Production' no portal e rode: amadeus_setup.py <KEY> <SECRET> production")
    except Exception as e:
        print(f"❌ Erro: {e}")
        print("   Confira a Key/Secret e se o app está ativo no portal da Amadeus.")


if __name__ == "__main__":
    main()
