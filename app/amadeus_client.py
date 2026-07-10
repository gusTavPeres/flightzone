"""
Cliente Amadeus Self-Service (Flight Offers Search) — preço REAL ordenado por preço.
Sem dependências externas (urllib). Credenciais vêm de amadeus.json (ou env
AMADEUS_KEY / AMADEUS_SECRET / AMADEUS_ENV). No-op se não configurado.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from app.config import Config

_token = {"value": None, "exp": 0.0, "base": None}


def _creds():
    key = os.getenv("AMADEUS_KEY")
    sec = os.getenv("AMADEUS_SECRET")
    env = os.getenv("AMADEUS_ENV")
    if not (key and sec) and os.path.exists(Config.AMADEUS_PATH):
        try:
            with open(Config.AMADEUS_PATH, encoding="utf-8") as f:
                d = json.load(f)
            key = key or d.get("key")
            sec = sec or d.get("secret")
            env = env or d.get("env")
        except Exception:
            pass
    return key, sec, (env or "test")


def configured() -> bool:
    k, s, _ = _creds()
    return bool(k and s)


def _base(env):
    return "https://api.amadeus.com" if env == "production" else "https://test.api.amadeus.com"


def _http(req, timeout=25):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}") from None


def _get_token(key, sec, base):
    now = time.time()
    if _token["value"] and _token["exp"] > now and _token["base"] == base:
        return _token["value"]
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": key, "client_secret": sec,
    }).encode()
    req = urllib.request.Request(
        base + "/v1/security/oauth2/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    j = _http(req, timeout=15)
    _token.update(value=j["access_token"], exp=now + j.get("expires_in", 1799) - 60, base=base)
    return _token["value"]


def search_cheapest(origin, dest, date, return_date=None, adults=1,
                    currency="BRL", max_offers=20):
    """Retorna (preço_mais_barato, companhia) ou None. Lança erro com detalhe se falhar."""
    key, sec, env = _creds()
    if not (key and sec):
        return None
    base = _base(env)
    token = _get_token(key, sec, base)
    params = {
        "originLocationCode": origin.upper(),
        "destinationLocationCode": dest.upper(),
        "departureDate": str(date),
        "adults": int(adults),
        "currencyCode": currency,
        "max": int(max_offers),
    }
    if return_date:
        params["returnDate"] = str(return_date)
    url = base + "/v2/shopping/flight-offers?" + urllib.parse.urlencode(params)
    j = _http(urllib.request.Request(url, headers={"Authorization": "Bearer " + token}))

    offers = j.get("data", [])
    carriers = (j.get("dictionaries") or {}).get("carriers", {})
    best = None
    for o in offers:
        try:
            price = float(o["price"]["grandTotal"])
        except (KeyError, TypeError, ValueError):
            continue
        code = ""
        try:
            code = o["validatingAirlineCodes"][0]
        except (KeyError, IndexError):
            pass
        airline = carriers.get(code, code)
        if best is None or price < best[0]:
            best = (price, airline)
    return best
