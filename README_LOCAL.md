# FlightZone Local ✈️

Coletor de passagens aéreas das **principais companhias** (Gol, LATAM, Azul,
Avianca, American, COPA, TAP…) rodando **100% no seu PC**, **de graça** e
**sem chave de API**.

É uma adaptação do desafio técnico `JoaoGChv/Desafio_T-cnico-Promozone`.
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
./run.sh        # sobe em http://127.0.0.1:8080
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

## 6. Monitor de preços (1..N rotas, anti-bloqueio) 🔔

Vigia uma **ou várias** rotas e avisa quando o preço **cai** (terminal + bipe +
notificação na área de trabalho).

**Uma rota:**
```bash
./monitor.sh --from GRU --to GIG --date 2026-07-23 --interval 30 --threshold 600
# opcionais: --return 2026-08-05 --trip roundtrip --max-stops 0
```

**Várias rotas** (arquivo JSON — veja `routes.example.json`):
```bash
cp routes.example.json routes.json    # edite com as suas rotas
./monitor.sh --routes-file routes.json
```

### Calibração anti-bloqueio (geral, vale para qualquer N)
O que se limita é a **taxa de requisições**, não o nº de rotas. Com **T** =
intervalo por rota (default 30 min), **N** = nº de rotas, **s_min** = gap mínimo
global (default 15s):
```
espaçamento entre requests  = max(T / N, s_min)
intervalo efetivo por rota  = max(T, N * s_min)
teto de requests por minuto = 60 / s_min     (fixo ~4/min, independe de N)
```
- Poucas rotas → cada uma recheca a cada T; requests bem espaçados.
- Muitas rotas → o gap encosta em `s_min` e o ciclo **se estica sozinho**; a taxa
  nunca passa do teto.
- Bloqueio é por **IP** → o **backoff é global** (todas desaceleram juntas) e
  decai sozinho. Ajuste com `--interval` (T), `--min-gap` (s_min), `--jitter`.

### Outros
- Série temporal em `price_history` (1 linha por checagem). Últimas 20:
  ```bash
  ./.venv/bin/python -c "import sqlite3;[print(r) for r in sqlite3.connect('data/flights.db').execute('SELECT checked_at,origin,destination,cheapest_price,airline FROM price_history ORDER BY id DESC LIMIT 20')]"
  ```
- Parar: `Ctrl+C`.

**Deixar rodando sozinho (reinicia e sobe no boot):** veja as instruções no
arquivo `flightzone-monitor.service` (serviço systemd em modo usuário).
