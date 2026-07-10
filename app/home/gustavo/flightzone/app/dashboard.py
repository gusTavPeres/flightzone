"""
Dashboard HTML (sem dependências externas) para visualizar os preços coletados.
Renderizado pelo Flask na rota "/".
"""
from datetime import datetime, timezone

from app.links import gflights_url

STYLE = """
* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
       background:#0f172a; color:#e2e8f0; }
.wrap { max-width:1000px; margin:0 auto; padding:24px 16px 60px; }
header h1 { margin:0 0 4px; font-size:22px; }
header .sub { color:#94a3b8; font-size:13px; }
.combo { background:linear-gradient(135deg,#1e293b,#0b3b2e); border:1px solid #14532d;
         border-radius:16px; padding:20px 24px; margin:20px 0; }
.combo .lab { color:#86efac; font-size:12px; text-transform:uppercase; letter-spacing:.5px; }
.combo .big { font-size:32px; font-weight:700; margin:2px 0; }
.combo .leg1 { font-size:14px; color:#cbd5e1; }
.cols { display:flex; gap:20px; flex-wrap:wrap; }
.leg { background:#1e293b; border:1px solid #334155; border-radius:14px; padding:16px 18px;
       flex:1; min-width:330px; }
.leg h3 { margin:0 0 10px; font-size:16px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; color:#94a3b8; font-weight:600; padding:6px 8px; border-bottom:1px solid #334155;
     font-size:10px; text-transform:uppercase; letter-spacing:.4px; }
td { padding:8px; border-bottom:1px solid #25324a; vertical-align:middle; }
tr.best td { background:#10331f; }
td.price { font-weight:700; white-space:nowrap; }
td.date { white-space:nowrap; }
.barcell { width:110px; }
.bar { height:8px; background:#64748b; border-radius:6px; }
tr.best .bar { background:#22c55e; }
.tag { background:#16a34a; color:#fff; font-size:10px; padding:1px 6px; border-radius:10px; margin-left:6px; }
.muted { color:#94a3b8; } .small { font-size:11px; }
.foot { margin-top:24px; color:#64748b; font-size:12px; line-height:1.6; }
a { color:#7dd3fc; }
.addtitle { margin:14px 0 6px; font-size:13px; color:#cbd5e1; font-weight:600; }
.addform { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.addform input, .addform select { background:#0f172a; color:#e2e8f0; border:1px solid #334155;
   border-radius:8px; padding:7px 9px; font-size:13px; }
.addform input[type=date]{ color-scheme:dark; }
.btn-add { background:#2563eb; color:#fff; border:none; border-radius:8px; padding:8px 14px;
   font-size:13px; cursor:pointer; }
.btn-add:hover { background:#1d4ed8; }
.btn-x { background:#7f1d1d; color:#fecaca; border:none; border-radius:6px; padding:4px 10px;
   font-size:12px; cursor:pointer; }
.btn-x:hover { background:#991b1b; }
.msg { background:#16344a; border:1px solid #1e40af; color:#bfdbfe; padding:10px 14px;
   border-radius:10px; margin:12px 0; font-size:13px; }
.hgrid { display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:16px; }
.hcard { background:#1e293b; border:1px solid #334155; border-radius:14px; padding:14px 16px; }
.hhead { margin-bottom:4px; }
.hstats { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px; }
.hstats .cur { font-size:22px; font-weight:700; }
.chart { width:100%; height:auto; display:block; }
.chartph { padding:28px 0; text-align:center; }
.axlbl { fill:#94a3b8; font-size:9px; }
.nav { display:flex; gap:8px; margin:16px 0 6px; flex-wrap:wrap; }
.navtab { background:#1e293b; border:1px solid #334155; color:#cbd5e1; padding:9px 16px;
   border-radius:10px; text-decoration:none; font-size:13px; font-weight:600; }
.navtab:hover { background:#273449; }
.navtab.active { background:#2563eb; border-color:#2563eb; color:#fff; }
.hstatus { border-radius:10px; padding:8px 14px; margin:10px 0; font-size:13px; }
.hstatus.ok { background:#0b3b2e; border:1px solid #14532d; color:#86efac; }
.hstatus.warn { background:#3b1e1e; border:1px solid #7f1d1d; color:#fca5a5; }
.rtline { background:#1e293b; border:1px solid #334155; border-radius:12px; padding:12px 16px;
   margin:-8px 0 20px; font-size:14px; }
.matrix { border-collapse:collapse; margin-top:8px; }
.matrix th, .matrix td { padding:9px 12px; text-align:center; font-size:13px;
   border:1px solid #0f172a; white-space:nowrap; }
.matrix thead th { background:#1e293b; color:#94a3b8; font-size:11px; }
.matrix .rowh { background:#1e293b; color:#cbd5e1; font-weight:600; text-align:right; }
.matrix .corner { background:#0f172a; color:#64748b; font-size:10px; }
.matrix td.cell { color:#fff; font-weight:600; }
.matrix td.best { outline:2px solid #22c55e; outline-offset:-2px; }
a.dlink { color:inherit; text-decoration:none; border-bottom:1px dotted #64748b; }
a.dlink:hover { border-bottom-color:#7dd3fc; color:#7dd3fc; }
.matrix a.clink { color:#fff; text-decoration:none; display:block; }
.matrix a.clink:hover { text-decoration:underline; }
.combo a { color:#86efac; }
"""


def _nav(active=""):
    tabs = [("/", "🏠 Painel", "home"), ("/roundtrip", "🔁 Ida-e-volta", "rt"),
            ("/history", "📈 Histórico 24h", "hist"), ("/export.csv", "⬇️ Baixar CSV", "csv")]
    out = [f'<a class="navtab{" active" if k == active else ""}" href="{href}">{lbl}</a>'
           for href, lbl, k in tabs]
    return '<div class="nav">' + "".join(out) + '</div>'


def _health_badge(db):
    h = db.health()
    try:
        age = ((datetime.now(timezone.utc) - datetime.fromisoformat(h["last"])).total_seconds() / 60
               if h["last"] else None)
    except Exception:
        age = None
    ok = age is not None and age < 10
    age_s = f"há {age:.0f} min" if age is not None else "—"
    n24 = f"{h['n24']:,}".replace(",", ".")
    tot = f"{h['total']:,}".replace(",", ".")
    return (f'<div class="hstatus {"ok" if ok else "warn"}">'
            f'{"🟢" if ok else "🔴"} monitor · última raspagem {age_s} · '
            f'{n24} leituras/24h · {tot} no total</div>')


def _money(v):
    return ("R$ " + f"{v:,.0f}".replace(",", ".")) if v is not None else "—"


def _now():
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def _fmt_date(s):
    try:
        d = datetime.strptime(str(s), "%Y-%m-%d")
        dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
        return d.strftime("%d/%m") + " (" + dias[d.weekday()] + ")"
    except Exception:
        return str(s)


def _fmt_dt(s):
    try:
        return datetime.fromisoformat(s).strftime("%d/%m %H:%M")
    except Exception:
        return s or "—"


def _sparkline(series, w=104, h=28):
    pts = [p for _, p in series if p is not None]
    if len(pts) < 2:
        return '<span class="muted small">—</span>'
    lo, hi = min(pts), max(pts)
    rng = (hi - lo) or 1
    n = len(pts)
    coords = " ".join(
        f"{(i/(n-1))*(w-4)+2:.1f},{h-2-((p-lo)/rng)*(h-6):.1f}" for i, p in enumerate(pts)
    )
    color = "#22c55e" if pts[-1] <= pts[0] else "#f87171"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{coords}"/></svg>')


def _leg_table(db, frm, to, title):
    rows = db.price_by_date(frm, to)
    if not rows:
        return (f'<div class="leg"><h3>{title} <span class="muted small">({frm}→{to})</span></h3>'
                '<p class="muted small">Sem dados ainda — o monitor preenche em alguns minutos.</p></div>')
    prices = [r["price"] for r in rows if r["price"] is not None]
    gmin, gmax = (min(prices), max(prices)) if prices else (0, 1)
    rng = (gmax - gmin) or 1
    best_date = min(rows, key=lambda r: r["price"] if r["price"] is not None else 1e9)["date"]
    trs = []
    for r in rows:
        p = r["price"] if r["price"] is not None else r["min_price"]
        mn = r.get("min_price")
        wpct = 12 + 88 * (p - gmin) / rng if p is not None else 12
        is_best = r["date"] == best_date
        badge = ' <span class="tag">+ barato</span>' if is_best else ""
        min_txt = (f'<div class="muted small">mín {_money(mn)}</div>'
                   if (mn is not None and p is not None and mn < p) else "")
        spark = _sparkline(db.price_series(frm, to, r["date"]))
        url = gflights_url(frm, to, r["date"], "oneway")
        trs.append(
            f'<tr class="{"best" if is_best else ""}">'
            f'<td class="date"><a class="dlink" target="_blank" rel="noopener" '
            f'href="{url}">{_fmt_date(r["date"])} ↗</a>{badge}</td>'
            f'<td class="price">{_money(p)}{min_txt}</td>'
            f'<td class="barcell"><div class="bar" style="width:{wpct:.0f}%"></div></td>'
            f'<td>{spark}</td>'
            f'<td class="muted small">{r["checks"]}× · {_fmt_dt(r["last_checked"])}</td>'
            f'</tr>'
        )
    return (f'<div class="leg"><h3>{title} <span class="muted small">({frm}→{to})</span></h3>'
            '<table><thead><tr><th>Data</th><th>Atual</th><th>Preço</th>'
            '<th>Tendência</th><th>Atualizado</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def _routes_section(routes):
    items = []
    for i, r in enumerate(routes):
        o = (r.get("from") or r.get("origin") or "").upper()
        d = (r.get("to") or r.get("destination") or "").upper()
        trip = r.get("trip", "oneway")
        rt = f" · volta {r.get('return_date') or r.get('return') or '?'}" if trip == "roundtrip" else ""
        extra = []
        if r.get("max_stops") == 0:
            extra.append("direto")
        if r.get("threshold"):
            extra.append(f"alvo R$ {int(r['threshold'])}")
        ex = (" · " + " · ".join(extra)) if extra else ""
        items.append(
            '<tr>'
            f'<td><b>{o} → {d}</b></td><td>{r.get("date", "")}{rt}</td>'
            f'<td class="muted small">{trip}{ex}</td>'
            '<td style="text-align:right">'
            '<form method="post" action="/routes/remove" style="display:inline" '
            'onsubmit="return confirm(\'Remover esta consulta?\')">'
            f'<input type="hidden" name="index" value="{i}">'
            '<button class="btn-x">remover</button></form></td></tr>'
        )
    rows = "".join(items) or '<tr><td colspan="4" class="muted small">Nenhuma consulta ainda.</td></tr>'
    add_form = (
        '<form method="post" action="/routes/add" class="addform">'
        '<input name="origin" placeholder="Origem (GYN)" maxlength="3" required>'
        '<input name="dest" placeholder="Destino (JPA)" maxlength="3" required>'
        '<input name="date" type="date" required>'
        '<select name="trip" onchange="document.getElementById(\'rd\').style.display='
        '(this.value==\'roundtrip\'?\'inline-block\':\'none\')">'
        '<option value="oneway">só ida</option><option value="roundtrip">ida e volta</option></select>'
        '<input id="rd" name="return_date" type="date" style="display:none">'
        '<select name="max_stops"><option value="">paradas: qualquer</option>'
        '<option value="0">só direto</option></select>'
        '<input name="threshold" type="number" step="1" placeholder="alvo R$ (opcional)">'
        '<button class="btn-add">adicionar</button></form>'
    )
    return (
        '<div class="leg" style="flex-basis:100%">'
        f'<h3>⚙️ Consultas monitoradas <span class="muted small">({len(routes)})</span></h3>'
        f'<table>{rows}</table>'
        '<div class="addtitle">+ adicionar consulta</div>'
        f'{add_form}'
        '<div class="muted small" style="margin-top:6px">O monitor recarrega sozinho em ~1 min '
        'após adicionar/remover.</div></div>'
    )


def render_dashboard(db, origin, dest, routes=None, msg=None):
    ida = db.price_by_date(origin, dest)
    volta = db.price_by_date(dest, origin)

    combo = ""
    if ida and volta:
        bi = min(ida, key=lambda r: r["price"] if r["price"] is not None else 1e9)
        bv = min(volta, key=lambda r: r["price"] if r["price"] is not None else 1e9)
        total = (bi["price"] or 0) + (bv["price"] or 0)
        combo = (
            '<div class="combo"><div class="lab">Melhor combinação AGORA '
            '(ida só-ida + volta só-ida · preço atual)</div>'
            f'<div class="big">{_money(total)}</div>'
            f'<div class="leg1">🛫 ida <a target="_blank" rel="noopener" '
            f'href="{gflights_url(origin, dest, bi["date"], "oneway")}"><b>{_fmt_date(bi["date"])}</b></a>'
            f' · {_money(bi["price"])}'
            f' &nbsp;+&nbsp; 🛬 volta <a target="_blank" rel="noopener" '
            f'href="{gflights_url(dest, origin, bv["date"], "oneway")}"><b>{_fmt_date(bv["date"])}</b></a>'
            f' · {_money(bv["price"])}</div>'
            f'<div style="margin-top:10px"><a class="navtab" '
            f'href="/realprice?origin={origin}&dest={dest}&date={bi["date"]}&return_date={bv["date"]}">'
            f'🔎 ver preço REAL (ida-e-volta)</a></div></div>'
        )

    rtm = db.roundtrip_matrix(origin, dest)
    if rtm:
        brt = min(rtm, key=lambda c: c["price"] if c["price"] is not None else 1e9)
        extra = ""
        if ida and volta:
            sav = total - brt["price"]
            extra = (f" — <b>economia de {_money(sav)}</b> vs. dois só-ida" if sav > 0
                     else " (≈ igual à soma dos só-ida)")
        combo += (f'<div class="rtline">🔁 <b>Ida-e-volta casada</b> mais barata: '
                  f'<b>{_money(brt["price"])}</b> ({_fmt_date(brt["departure_date"])} → '
                  f'{_fmt_date(brt["return_date"])}){extra} · <a href="/roundtrip">ver matriz</a></div>')

    legs = _leg_table(db, origin, dest, "Ida") + _leg_table(db, dest, origin, "Volta")

    head = ('<!doctype html><html lang="pt-br"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="refresh" content="60">'
            f'<title>FlightZone {origin}&harr;{dest}</title><style>' + STYLE +
            '</style></head><body><div class="wrap">')
    header = ('<header><h1>✈️ FlightZone — '
              f'{origin} &harr; {dest}</h1>'
              f'<div class="sub">Atualiza sozinho a cada 60s · {_now()}<br>'
              '✅ <b>preços reais</b> (menor preço do Google Flights), raspados continuamente</div></header>')
    foot = ('<div class="foot">💡 Clique numa <b>data ↗</b> (ou no card) para abrir a busca no '
            'Google Flights. '
            'Cada preço de Ida/Volta é de uma passagem <b>só-ida</b>; o total do '
            'card é a soma da ida + volta mais baratas. Você pode adicionar consultas '
            '<b>ida-e-volta casada</b> abaixo (às vezes saem mais baratas).<br>'
            'Preços do Google Flights (referência) — confirme no checkout da companhia.</div>')
    msg_html = f'<div class="msg">{msg}</div>' if msg else ""
    mng = '<div class="cols">' + _routes_section(routes or []) + '</div>'
    return (head + header + _nav("home") + _health_badge(db) + msg_html + combo
            + '<div class="cols">' + legs + '</div>' + mng + foot + '</div></body></html>')


def _linechart(points, w=560, h=180):
    data = []
    for s, p in points:
        if p is None:
            continue
        try:
            data.append((datetime.fromisoformat(s).astimezone(), p))
        except Exception:
            continue
    if len(data) < 2:
        v = data[-1][1] if data else None
        extra = f" · atual {_money(v)}" if v is not None else ""
        return f'<div class="chartph muted small">Coletando dados…{extra}</div>'
    L, R, TM, B = 46, 12, 10, 22
    pw, ph = w - L - R, h - TM - B
    t0, t1 = data[0][0], data[-1][0]
    tspan = (t1 - t0).total_seconds() or 1
    pmin = min(p for _, p in data)
    pmax = max(p for _, p in data)
    if pmax == pmin:
        pmin, pmax = pmin * 0.98, pmax * 1.02 + 1
    pspan = pmax - pmin

    def fx(t):
        return L + ((t - t0).total_seconds() / tspan) * pw

    def fy(p):
        return TM + (1 - (p - pmin) / pspan) * ph

    grid = []
    for frac in (0.0, 0.5, 1.0):
        py = TM + frac * ph
        grid.append(f'<line x1="{L}" y1="{py:.1f}" x2="{w-R}" y2="{py:.1f}" stroke="#1e293b"/>')
        grid.append(f'<text x="{L-4}" y="{py+3:.1f}" text-anchor="end" class="axlbl">'
                    f'{_money(pmax - frac*pspan)}</text>')
    coords = " ".join(f"{fx(t):.1f},{fy(p):.1f}" for t, p in data)
    dots = "".join(f'<circle cx="{fx(t):.1f}" cy="{fy(p):.1f}" r="2" fill="#93c5fd"/>' for t, p in data)
    color = "#22c55e" if data[-1][1] <= data[0][1] else "#f59e0b"
    xlabels = (f'<text x="{L}" y="{h-6}" class="axlbl">{t0.strftime("%H:%M")}</text>'
               f'<text x="{w-R}" y="{h-6}" text-anchor="end" class="axlbl">{t1.strftime("%H:%M")}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" class="chart">' + "".join(grid)
            + f'<polyline fill="none" stroke="{color}" stroke-width="2.2" points="{coords}"/>'
            + dots + xlabels + '</svg>')


def _history_card(db, frm, to, date, label_dir, hours):
    pts = db.history_points(frm, to, date, hours)
    vals = [p for _, p in pts if p is not None]
    cur = vals[-1] if vals else None
    mn = min(vals) if vals else None
    mx = max(vals) if vals else None
    return (
        '<div class="hcard">'
        f'<div class="hhead"><a class="dlink" target="_blank" rel="noopener" '
        f'href="{gflights_url(frm, to, date, "oneway")}"><b>{label_dir} {_fmt_date(date)}</b> ↗</a> '
        f'<span class="muted small">{frm}→{to}</span></div>'
        f'<div class="hstats"><span class="cur">{_money(cur)}</span>'
        f'<span class="muted small">mín {_money(mn)} · máx {_money(mx)} · {len(vals)} pts</span></div>'
        f'{_linechart(pts)}</div>'
    )


def render_history(db, origin, dest, hours=24):
    cards = ""
    for r in db.price_by_date(origin, dest):
        cards += _history_card(db, origin, dest, r["date"], "🛫 Ida", hours)
    for r in db.price_by_date(dest, origin):
        cards += _history_card(db, dest, origin, r["date"], "🛬 Volta", hours)
    if not cards:
        cards = '<p class="muted">Sem histórico ainda — deixe o monitor rodar um pouco.</p>'
    head = ('<!doctype html><html lang="pt-br"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="refresh" content="60">'
            f'<title>Histórico {origin}-{dest}</title><style>' + STYLE +
            '</style></head><body><div class="wrap">')
    header = ('<header><h1>📈 Histórico de preços — '
              f'{origin} &harr; {dest}</h1>'
              f'<div class="sub">Últimas {hours}h · atualiza a cada 60s · {_now()} · '
              '<a href="/">&larr; voltar ao painel</a></div></header>')
    foot = ('<div class="foot">Cada ponto é uma verificação do monitor · '
            'linha <b style="color:#22c55e">verde</b> = caindo, '
            '<b style="color:#f59e0b">laranja</b> = subindo/estável.</div>')
    return head + header + _nav("hist") + '<div class="hgrid">' + cards + '</div>' + foot + '</div></body></html>'


def _heat_color(frac):
    hue = 140 * (1 - max(0.0, min(1.0, frac)))  # 140 = verde (barato), 0 = vermelho (caro)
    return f"hsl({hue:.0f}, 55%, 28%)"


def render_roundtrip(db, origin, dest):
    combos = db.roundtrip_matrix(origin, dest)
    head = ('<!doctype html><html lang="pt-br"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="refresh" content="60">'
            f'<title>Ida-e-volta {origin}-{dest}</title><style>' + STYLE +
            '</style></head><body><div class="wrap">')
    header = ('<header><h1>🔁 Ida-e-volta casada — '
              f'{origin} &harr; {dest}</h1>'
              f'<div class="sub">Preço total do bilhete ida-e-volta · atualiza a cada 60s · {_now()}<br>'
              '✅ <b>preços reais</b> (menor preço do Google Flights)</div></header>')
    nav = _nav("rt")
    if not combos:
        body = ('<div class="leg" style="flex-basis:100%"><p class="muted">Ainda sem dados de '
                'ida-e-volta casada. O monitor coleta os combos nos próximos minutos — recarregue '
                'em breve.</p></div>')
        return head + header + nav + body + '</div></body></html>'

    deps = sorted({c["departure_date"] for c in combos})
    rets = sorted({c["return_date"] for c in combos})
    pm = {(c["departure_date"], c["return_date"]): c["price"] for c in combos}
    prices = [c["price"] for c in combos if c["price"] is not None]
    pmin, pmax = min(prices), max(prices)
    rng = (pmax - pmin) or 1
    best = min(combos, key=lambda c: c["price"] if c["price"] is not None else 1e9)

    card = ('<div class="combo"><div class="lab">Melhor ida-e-volta casada agora</div>'
            f'<div class="big">{_money(best["price"])}</div>'
            f'<div class="leg1">🛫 ida <b>{_fmt_date(best["departure_date"])}</b> '
            f'&nbsp;→&nbsp; 🛬 volta <b>{_fmt_date(best["return_date"])}</b> &nbsp;·&nbsp; '
            f'<a target="_blank" rel="noopener" href="'
            f'{gflights_url(origin, dest, best["departure_date"], "roundtrip", best["return_date"])}">'
            f'abrir no Google Flights ↗</a></div>'
            f'<div style="margin-top:10px"><a class="navtab" '
            f'href="/realprice?origin={origin}&dest={dest}&date={best["departure_date"]}'
            f'&return_date={best["return_date"]}">🔎 ver preço REAL</a></div></div>')

    thead = ('<th class="corner">ida ↓ \\ volta →</th>'
             + "".join(f'<th>{_fmt_date(r)}</th>' for r in rets))
    trs = []
    for dep in deps:
        cells = [f'<th class="rowh">{_fmt_date(dep)}</th>']
        for ret in rets:
            p = pm.get((dep, ret))
            if p is None:
                cells.append('<td class="muted">—</td>')
            else:
                isbest = dep == best["departure_date"] and ret == best["return_date"]
                u = gflights_url(origin, dest, dep, "roundtrip", ret)
                cells.append(f'<td class="cell{" best" if isbest else ""}" '
                             f'style="background:{_heat_color((p - pmin) / rng)}">'
                             f'<a class="clink" target="_blank" rel="noopener" href="{u}">{_money(p)}</a></td>')
        trs.append("<tr>" + "".join(cells) + "</tr>")
    matrix = (f'<table class="matrix"><thead><tr>{thead}</tr></thead>'
              f'<tbody>{"".join(trs)}</tbody></table>')

    block = ('<div class="leg" style="flex-basis:100%"><h3>Matriz de preços (ida × volta)</h3>'
             f'{matrix}<div class="muted small" style="margin-top:8px">🟩 mais barato · '
             '🟥 mais caro · contorno verde = melhor combinação. <b>Clique em qualquer célula</b> '
             'para abrir a busca no Google Flights ↗.</div></div>')
    foot = ('<div class="foot">Combos das suas datas: ida 19–23/nov × volta 29/nov–03/dez '
            '(25 combinações). Gerencie as consultas no painel.</div>')
    return head + header + nav + card + '<div class="cols">' + block + '</div>' + foot + '</div></body></html>'


def render_realprice(origin, dest, date, return_date, price, secs):
    trip = "roundtrip" if return_date else "oneway"
    url = gflights_url(origin, dest, date, trip, return_date)
    rota = (f"{origin} → {dest} · ida {_fmt_date(date)}"
            + (f" · volta {_fmt_date(return_date)}" if return_date else ""))
    val = _money(price) if price else 'não consegui ler agora 😕 (tente de novo)'
    head = ('<!doctype html><html lang="pt-br"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>Preço real {origin}-{dest}</title><style>' + STYLE + '</style></head><body><div class="wrap">')
    body = ('<header><h1>🔎 Preço real — Google Flights</h1>'
            f'<div class="sub">Lido ao vivo da aba "Menores preços" em ~{secs}s</div></header>'
            + _nav("")
            + f'<div class="combo"><div class="lab">Menor preço REAL — {rota}</div>'
            + f'<div class="big">{val}</div></div>'
            + '<div class="nav">'
            + f'<a class="navtab" target="_blank" rel="noopener" href="{url}">abrir no Google Flights ↗</a>'
            + '<a class="navtab" href="/">← voltar ao painel</a></div>')
    return head + body + '</div></body></html>'
