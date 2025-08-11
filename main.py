import os
import re
import json
import argparse
from datetime import datetime
import requests

# Carrega variáveis do .env 
from dotenv import load_dotenv
load_dotenv()

API = "https://api.digitalocean.com"
TOKEN = os.environ.get("DIGITALOCEAN_TOKEN")
if not TOKEN:
    raise SystemExit("Defina DIGITALOCEAN_TOKEN (em .env ou variável de ambiente)")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Funções utilitárias para parsing de valores e datas
def parse_amount(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    m = re.findall(r"-?\d+(?:\.\d+)?", str(val))
    return float(m[0]) if m else 0.0


def to_date(s: str) -> datetime | None:
    if not s:
        return None
    s = str(s)
    if "T" in s:
        s = s.split("T")[0]
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def parse_invoice_period(inv: dict) -> datetime | None:
    period = inv.get("invoice_period")
    if period:
        try:
            return datetime.strptime(period, "%Y-%m")
        except Exception:
            pass
    for k in ("created_at", "date", "invoice_date"):
        d = to_date(inv.get(k))
        if d:
            return d
    return None


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def month_label(dt: datetime) -> str:
    return dt.strftime("%B %Y")


def months_between(start_dt: datetime, end_dt: datetime) -> list[str]:
    out = []
    cur = datetime(start_dt.year, start_dt.month, 1)
    endm = datetime(end_dt.year, end_dt.month, 1)
    while cur <= endm:
        out.append(cur.strftime("%Y-%m"))
        y, m = cur.year, cur.month
        cur = datetime(y + (m // 12), (m % 12) + 1, 1)
    return out

# Função de API: busca todas as faturas com paginação
def fetch_all_invoices() -> list[dict]:
    url = f"{API}/v2/customers/my/invoices?per_page=200&page=1"
    out = []
    while url:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("invoices") or [])
        pages = (data.get("links") or {}).get("pages") or {}
        url = pages.get("next")
    return out

# Função de conversão: obtém cotação USD→BRL (com fallbacks)
def fetch_usd_brl_rate() -> tuple[float, str]:
    try:
        r = requests.get("https://api.exchangerate.host/latest?base=USD&symbols=BRL", timeout=10)
        if r.ok:
            j = r.json(); rate = float(j.get("rates", {}).get("BRL"))
            if rate > 0: return rate, "exchangerate.host"
    except Exception:
        pass
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        if r.ok:
            j = r.json(); rate = float(j.get("rates", {}).get("BRL"))
            if rate > 0: return rate, "open.er-api.com"
    except Exception:
        pass
    try:
        r = requests.get("https://economia.awesomeapi.com.br/json/last/USD-BRL", timeout=10)
        if r.ok:
            j = r.json(); rate = float(j.get("USDBRL", {}).get("bid"))
            if rate > 0: return rate, "awesomeapi.com.br"
    except Exception:
        pass
    return 5.0, "fallback"

# Renderiza HTML completo (gráficos responsivos + tabela em BRL)
def render_html(balance_json: dict,
                period_start: str,
                period_end: str,
                month_labels: list[str],
                month_values: list[float],
                monthly_totals_table: list[tuple[str, float]],
                usd_brl: float,
                fx_source: str):
    html = []
    html.append("<!doctype html><html><head><meta charset='utf-8'>")
    html.append("<title>Billing-DO Report</title>")
    html.append("<script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js'></script>")
    html.append("<style>"
                "body{font-family:Arial, sans-serif;line-height:1.4}"
                ".wrap{max-width:920px;margin:24px auto}"
                ".muted{color:#666} h2{margin-top:28px} table{border-collapse:collapse;margin-top:10px}"
                "th,td{border:1px solid #ddd;padding:6px 8px}"
                ".chart-box{position:relative;width:clamp(300px,80vw,720px);}"
                "canvas{display:block;width:100% !important;height:auto !important;}"
                "</style>")
    html.append("</head><body><div class='wrap'>")
    html.append("<h1>Billing-DO Report</h1>")
    html.append(f"<p class='muted'><strong>Período:</strong> {period_start} a {period_end}</p>")

    html.append("<details><summary><strong>Saldo (balance)</strong></summary><pre>")
    html.append(json.dumps(balance_json, indent=2))
    html.append("</pre></details>")

    html.append("<h2>Evolução mensal (linha)</h2>")
    html.append("<div class='chart-box' id='box_line'><canvas id='evo'></canvas></div>")

    html.append("<h2>Totais por mês (barras horizontais)</h2>")
    html.append("<div class='chart-box' id='box_bar'><canvas id='evo_hbar'></canvas></div>")

    html.append("<h2>Totais por mês</h2>")
    html.append(f"<p class='muted'>Cotação USD→BRL: <strong>{usd_brl:.4f}</strong> (fonte: {fx_source})</p>")
    html.append("<table><thead><tr><th>Mês</th><th>Total (USD)</th><th>Total (BRL)</th></tr></thead><tbody>")
    for label, total in monthly_totals_table:
        html.append(f"<tr><td>{label}</td><td>{total:.2f}</td><td>{total*usd_brl:.2f}</td></tr>")
    html.append("</tbody></table>")
    html.append("<script>")
    html.append("const LABELS = " + json.dumps(month_labels) + ";")
    html.append("const VALUES = " + json.dumps(month_values) + ";")
    html.append("""
let lineChart, barChart;
function buildCharts(){
  if(!window.Chart) return;
  const base = {responsive:true, maintainAspectRatio:true, aspectRatio:1.8, resizeDelay:120};
  const lineOpts = Object.assign({}, base, {scales:{y:{beginAtZero:true}}});
  const barOpts  = Object.assign({}, base, {indexAxis:'y', animation:false, animations:false, scales:{x:{beginAtZero:true}, y:{ticks:{autoSkip:false}, afterFit:(scale)=>{ scale.width = 120; }}}});
  const lctx = document.getElementById('evo').getContext('2d');
  const hctx = document.getElementById('evo_hbar').getContext('2d');
  if(lineChart) lineChart.destroy(); if(barChart) barChart.destroy();
  lineChart = new Chart(lctx, {type:'line', data:{labels:LABELS, datasets:[{label:'Total mensal (USD)', data:VALUES, tension:0.2, fill:false}]}, options:lineOpts});
  barChart  = new Chart(hctx, {type:'bar',  data:{labels:LABELS, datasets:[{label:'Total por mês (USD)', data:VALUES}]}, options:barOpts});
}
function init(){ buildCharts(); }
if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', init); } else { init(); }
window.addEventListener('resize', ()=>{ if(lineChart) lineChart.resize(); if(barChart) barChart.resize(); }); if(barChart) barChart.resize(); });
""")
    html.append("</script>")

    html.append("</div></body></html>")
    return "\n".join(html)

# Executa: lê args, coleta dados, agrega por mês, renderiza e salva HTML
def main():
    parser = argparse.ArgumentParser(description="Relatório de billing (gráficos responsivos + BRL)")
    parser.add_argument("--start", required=True, help="Data inicial (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Data final (YYYY-MM-DD)")
    args = parser.parse_args()

    start_dt = to_date(args.start)
    end_dt = to_date(args.end)
    if not start_dt or not end_dt:
        raise SystemExit("Formato de data inválido. Use YYYY-MM-DD")
    if end_dt < start_dt:
        raise SystemExit("Data final deve ser posterior à inicial")

    # Balance
    r = requests.get(f"{API}/v2/customers/my/balance", headers=HEADERS, timeout=30)
    r.raise_for_status()
    balance_json = r.json()

    # Invoices
    invoices = fetch_all_invoices()

    # Agregar por mês
    months = months_between(start_dt, end_dt)
    monthly_totals: dict[str, float] = {m: 0.0 for m in months}

    for inv in invoices:
        d = parse_invoice_period(inv)
        if not d:
            continue
        mk = month_key(d)
        if mk not in monthly_totals:
            continue
        amt = inv.get("amount") or inv.get("total") or inv.get("amount_due") or 0
        monthly_totals[mk] += parse_amount(amt)

    # Labels/valores + tabela
    labels: list[str] = []
    values: list[float] = []
    monthly_table: list[tuple[str, float]] = []
    for m in months:
        dt = datetime.strptime(m, "%Y-%m")
        lbl = month_label(dt)
        total = monthly_totals.get(m, 0.0)
        labels.append(lbl)
        values.append(total)
        monthly_table.append((lbl, total))

    # USD→BRL
    usd_brl, fx_source = fetch_usd_brl_rate()

    # Render
    html = render_html(
        balance_json=balance_json,
        period_start=args.start,
        period_end=args.end,
        month_labels=labels,
        month_values=values,
        monthly_totals_table=monthly_table,
        usd_brl=usd_brl,
        fx_source=fx_source,
    )

    with open("billing_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Relatório gerado: billing_report.html")

if __name__ == "__main__":
    main()
