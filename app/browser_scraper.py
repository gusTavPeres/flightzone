"""
Coletor do PREÇO REAL mais barato via navegador (Playwright + Chrome de verdade).

O endpoint de dados do Google só devolve "Melhores voos". A tarifa mais barata
real ("Menores preços · a partir de R$ X") só aparece na página renderizada por
JS. Headless é bloqueado; usamos Chrome HEADED sob um display (xvfb = invisível).

Insight: NÃO precisa clicar na aba — o "a partir de R$ X" já está na página
inicial. Só esperamos ele parar de cair (ele decresce conforme os voos carregam).

`read_cheapest_on_page(pg, url)` é reutilizável: o monitor contínuo usa 1
navegador persistente; `scrape_cheapest()` abre/fecha um navegador pontual.
"""
import re
import time

from app.links import gflights_url
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")


def _apartir(txt):
    """O 'a partir de R$ X' é o MENOR preço calculado pelo próprio Google."""
    m = re.search(r"a partir de\s*R\$[\s\xa0]*([\d.]+)", txt)
    if m:
        d = m.group(1).replace(".", "")
        if d.isdigit():
            return int(d)
    return None


def _extract_min(txt):
    vals = []
    for x in re.findall(r"R\$[\s\xa0]*([\d][\d.]{1,7})", txt):
        d = x.replace(".", "")
        if d.isdigit() and 150 < int(d) < 50000:
            vals.append(int(d))
    return min(vals) if vals else None


_BLOCK_SIGNS = ("unusual traffic", "not a robot", "sou um humano", "sou humano",
                "tráfego incomum", "trafego incomum", "recaptcha", "captcha",
                "detectamos", "verificar que você", "unusual activity",
                "nossos sistemas detectaram", "robô", "com um robo",
                "deslize para", "proteger seu acesso")


def looks_blocked(pg):
    """Detecta captcha/bloqueio (DataDome/reCAPTCHA/'tráfego incomum') na página."""
    try:
        t = pg.inner_text("body").lower()
    except Exception:
        return False
    return any(s in t for s in _BLOCK_SIGNS)


def _parse_flight_label(al):
    """Extrai preço + detalhes de um aria-label de card de voo do Google Flights."""
    low = al.lower()
    mp = re.search(r"a partir de\s*([\d.]+)\s*reai", low) or re.search(r"(\d[\d.]{2,6})\s*reai", low)
    price = int(mp.group(1).replace(".", "")) if mp else None
    m_air = re.search(r"voo (?:da|do|de) ([\w\s\-\.&]+?)\s+(?:com|sem)\s", low) \
        or re.search(r"operado por ([\w\s\-]+?)[,.]", low)
    airline = m_air.group(1).strip().title() if m_air else None
    if re.search(r"sem escala|direto|nonstop|sem parada", low):
        stops = 0
    else:
        ms = re.search(r"com\s+(\d+)\s+parada", low)
        stops = int(ms.group(1)) if ms else None
    mt = re.search(r"às\s+(\d{1,2}:\d{2})", low)
    dep = mt.group(1) if mt else None
    md = re.search(r"(\d+)\s*h(?:\s*(\d+)\s*min)?", low)
    dur = (int(md.group(1)) * 60 + int(md.group(2) or 0)) if md else None
    return {"price": price, "airline": airline, "stops": stops, "duration": dur, "dep_time": dep}


def extract_top_details(pg, target=None):
    """Detalhes do voo mais barato. Se `target` (preço) for dado, prefere o card que
    casa com ele (assim os detalhes batem com o preço lido). Retorna {} se nada casar."""
    for s in ("text=Menores preços", "text=Mais baratos"):
        try:
            pg.click(s, timeout=5000)
            pg.wait_for_timeout(4000)
            break
        except Exception:
            pass
    try:
        labels = pg.eval_on_selector_all(
            "[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))")
    except Exception:
        return {}
    cands = []
    for al in labels or []:
        if not al or "reai" not in al.lower():
            continue
        d = _parse_flight_label(al)
        if d["price"] and (d["airline"] or d["stops"] is not None):
            cands.append(d)
    if not cands:
        return {}
    if target:
        tol = max(5, target * 0.02)
        match = [d for d in cands if abs(d["price"] - target) <= tol]
        if match:
            return min(match, key=lambda d: d["price"])
        return {}  # nenhum card casou com o preço-alvo -> deixa o chamador usar fallback
    return min(cands, key=lambda d: d["price"])


def new_browser(p):
    """Abre um Chrome HEADLESS (sem janela, sem display). Retorna (browser, context)."""
    b = p.chromium.launch(channel="chrome", headless=True, args=[
        "--no-sandbox", "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(locale="pt-BR", timezone_id="America/Sao_Paulo",
                        user_agent=_UA, viewport={"width": 1280, "height": 900})
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return b, ctx


def read_cheapest_on_page(pg, url, settle_secs=6, max_secs=30):
    """Navega `url` numa page existente e lê o menor preço real. Retorna int ou None."""
    pg.goto(url, wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4500)
    if "Algo deu errado" in pg.inner_text("body"):       # bloqueio suave -> recarrega
        for s in ["text=Atualizar", "button:has-text('Atualizar')"]:
            try:
                pg.click(s, timeout=4000)
                break
            except Exception:
                pass
        pg.wait_for_timeout(8000)
    try:                                                 # espera os resultados renderizarem
        pg.wait_for_selector("text=Menores preços", timeout=18000)
    except Exception:
        pass
    best, no_improve, t0 = None, 0, time.time()          # espera o menor parar de cair
    while time.time() - t0 < max_secs:
        pg.wait_for_timeout(1500)
        cur = _apartir(pg.inner_text("body"))
        if cur is not None:
            if best is None or cur < best:
                best, no_improve = cur, 0
            else:
                no_improve += 1
            if no_improve >= 3 and (time.time() - t0) >= settle_secs:
                break
    return best


def scrape_cheapest(origin, dest, date, return_date=None, seat="economy",
                    settle_secs=6, max_secs=30):
    """Versão pontual (abre e fecha um navegador). Retorna int em BRL ou None."""
    trip = "roundtrip" if return_date else "oneway"
    url = gflights_url(origin, dest, date, trip, return_date, seat)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        logger.error(f"playwright indisponível: {e}")
        return None
    with sync_playwright() as p:
        try:
            b, ctx = new_browser(p)
        except Exception as e:
            logger.error(f"falha ao abrir o Chrome (tem display/xvfb?): {e}")
            return None
        try:
            pg = ctx.new_page()
            best = None
            for _ in range(2):                            # tenta até 2x a carga completa
                best = read_cheapest_on_page(pg, url, settle_secs, max_secs)
                if best is not None:
                    break
            if best is None:
                best = _extract_min(pg.inner_text("body"))
            logger.info(f"preço real {origin}->{dest} {date}"
                        f"{('/'+return_date) if return_date else ''}: {best}")
            return best
        finally:
            b.close()
