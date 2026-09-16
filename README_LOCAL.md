# FlightZone Local ✈️

Coletor de passagens aéreas das **principais companhias** (Gol, LATAM, Azul,
Avianca, American, COPA, TAP…) rodando **100% no seu PC**, **de graça** e
**sem chave de API**.

É uma adaptação do desafio técnico `JoaoGChv/Desafio_T-cnico-Promozone`, de
**João Guilherme Chaveiro** (`JoaoGChv`), colega de Pequi — o bot original
(Docker + BigQuery, raspando a Decolar) parou de funcionar quando o antibot
DataDome passou a bloquear a coleta.
Mantivemos a arquitetura (API Flask → Scraper → Normalizador → Banco → Logs),
mas trocamos as duas peças que impediam rodar localmente:

| Peça | Projeto original | Esta versão local |
|---|---|---|
| Coleta | `httpx` → **Decolar** (bloqueada por antibot DataDome ❌) | **Google Flights** via `fast-flights` ✅ |
| Banco | **Google BigQuery** (nuvem, paga ☁️) | **SQLite** local (`data/flights.db`) ✅ |
| Servidor | Flask (Cloud Run) | Flask (no seu PC, `localhost:8080`) ✅ |

> **Por que não a Decolar?** Ela usa o antibot **DataDome**: um `GET` simples
> recebe `HTTP 403`, e mesmo um Chrome real cai num captcha "deslize para
> verificar". O Google Flights agrega os preços das mesmas companhias e pode
> ser consultado de forma estável, sem cadastro.

---

## 1. Pré-requisitos (já instalados)

Ambiente virtual em `.venv` com `fast-flights` e `Flask`. Se precisar recriar:

```bash
cd ~/flightzone
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

## 2. Uso A — Linha de comando (mais rápido)

```bash
cd ~/flightzone

# Só ida, São Paulo (GRU) -> Rio (GIG)
./.venv/bin/python cli.py --from GRU --to GIG --date 2026-07-15

# Apenas voos diretos
./.venv/bin/python cli.py --from GRU --to REC --date 2026-08-01 --max-stops 0

# Ida e volta, classe executiva
./.venv/bin/python cli.py --from GRU --to LIS --date 2026-09-10 \
    --return 2026-09-25 --trip roundtrip --seat business
```

Cada busca imprime uma tabela e **salva no banco** (`data/flights.db`),
ignorando duplicados.

## 3. Uso B — Servidor web local (como o original)

```bash
cd ~/flightzone
./.venv/bin/python -m app.main    # dev; em produção o install.sh sobe via systemd
```

Em outro terminal (ou no navegador):

```bash
# Coletar (pode usar o navegador, é GET também):
#   http://127.0.0.1:8080/collect?origin=GRU&destination=GIG&date=2026-07-15
curl "http://127.0.0.1:8080/collect?origin=GRU&destination=GIG&date=2026-07-15"

# Coletar via POST (JSON):
curl -X POST http://127.0.0.1:8080/collect \
  -H "Content-Type: application/json" \
  -d '{"origin":"GRU","destination":"GIG","date":"2026-07-15","max_stops":0}'

# Estatísticas (preço mínimo/médio por rota nas últimas 24h):
curl "http://127.0.0.1:8080/stats"

# Listar voos guardados (mais baratos primeiro):
curl "http://127.0.0.1:8080/flights?origin=GRU&destination=GIG&limit=20"

# Baixar tudo em CSV:
curl -o flights.csv "http://127.0.0.1:8080/export.csv"
```

### Endpoints

| Método | Rota | O que faz |
|---|---|---|
| GET | `/health` | Verifica se está no ar |
| GET/POST | `/collect` | Coleta voos de uma rota/data e grava no banco |
| GET | `/stats` | Resumo por rota (mín., média, nº de companhias) |
| GET | `/flights` | Lista voos guardados (ordenados por preço) |
| GET | `/export.csv` | Exporta o banco em CSV |

Parâmetros do `/collect`: `origin`, `destination`, `date` (YYYY-MM-DD),
`trip_type` (`oneway`/`roundtrip`), `return_date`, `seat`
(`economy`/`premium-economy`/`business`/`first`), `max_stops`.

## 4. Onde ficam os dados

Tudo em **`data/flights.db`** (SQLite). Para inspecionar:

```bash
./.venv/bin/python -c "import sqlite3,os; c=sqlite3.connect('data/flights.db'); \
print(c.execute('SELECT origin,destination,airline,price FROM flights ORDER BY price LIMIT 10').fetchall())"
```

## 5. Avisos honestos

- **Fonte:** os preços vêm do Google Flights (são uma ótima referência, mas a
  compra final é feita no site da companhia/agência — pequenas diferenças podem
  ocorrer).
- **Uso pessoal e moderado.** Evite milhares de requisições; é raspagem de dados
  e deve respeitar os Termos de Uso. Para volume/uso comercial, prefira uma API
  oficial (ex.: **Amadeus Self-Service**, gratuita para testes).
- Se um dia o `fast-flights` parar (o Google muda o site às vezes), basta
  atualizar: `./.venv/bin/python -m pip install -U fast-flights`.

## 6. Sistema em produção (o que roda de verdade) 🔔

O monitor contínuo é o **`realprice_monitor.py`**: 1 Chrome headless persistente
lê o **menor preço real** ("a partir de R$ X") de cada rota do `routes.json`,
grava em `price_history` e alerta **preço bom** (mais barato que 97% das leituras
de 30 dias da própria rota — não toda queda) no **Telegram** e, se configurado,
no **Discord**. Painel web com histórico e matriz ida-e-volta em
**http://gustavopc:8090**.

**Avisar no Discord (canal do Pequi):** no servidor →
*Editar canal → Integrações → Webhooks → Novo webhook → Copiar URL*, e então:
```bash
cd ~/flightzone && echo '{"webhook": "<URL_COPIADA>"}' > discord.json && chmod 600 discord.json
systemctl --user restart flightzone-realprice
```
Vão pro canal só os alertas de preço (preço bom, abaixo do alvo, tarifa-erro);
heartbeat, bloqueio e resumo diário continuam só no Telegram. Ajuste o rigor com
`--deal-pct` (0.97 = só o top 3% mais barato do mês) e `--renotify` na unit do
monitor. Ao reiniciar, o monitor lê o último preço de cada rota no banco e não
re-anuncia o que já estava barato — só dips novos viram mensagem.

**Instalar/atualizar tudo (serviços systemd de usuário + timers):**
```bash
cd ~/flightzone && ./install.sh
```
Sobe: `flightzone-realprice` (monitor), `flightzone-web` (painel), e os timers
`heartbeat` (10 min), `backup` (03h), `dailysummary` (22h) e `selftest` (dom).
As rotas são editáveis pelo próprio painel (alterações pedem a senha de
`data/web_secret`; usuário em branco).

**Testes:**
```bash
./.venv/bin/python selftest.py          # parsers + queries do banco (offline)
./.venv/bin/python selftest.py --live   # canário: raspa um preço de verdade
```

**Série temporal** em `price_history` (1 linha por checagem). Últimas 20:
```bash
./.venv/bin/python -c "import sqlite3;[print(r) for r in sqlite3.connect('data/flights.db').execute('SELECT checked_at,origin,destination,cheapest_price FROM price_history ORDER BY id DESC LIMIT 20')]"
```
