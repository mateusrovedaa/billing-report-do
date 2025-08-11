# Billing-DO — Gerador de relatório HTML da DigitalOcean Billing API

Gera um **relatório HTML responsivo** com:
- **Série temporal (linha)** por mês
- **Totais mensais (barras horizontais)**
- **Tabela de Totais por mês** com **conversão USD → BRL** (cotação online)

---

## Requisitos
- **Python 3.10+**  
- `pip`

## Instalação

Crie e ative um ambiente virtual:
```bash
python -m venv .venv
source .venv/bin/activate
````

Instale as dependências:

```bash
pip install -r requirements.txt
```

## Configuração do token

Defina seu token da DigitalOcean em `DIGITALOCEAN_TOKEN`.

```bash
cp .env.example .env
```

Adicione o valor gerado na Digital Ocean

```env
DIGITALOCEAN_TOKEN=dop_v1_...
```

## Uso

Execute com um intervalo de datas (limites **incluem** os meses informados):

```bash
python main.py --start 2024-01-01 --end 2025-07-31
```

O script gera um arquivo `billing_report.html` na raiz do projeto contendo:

- Cabeçalho do período e **snapshot de balance** (JSON)
- **Gráfico de linha**: evolução mensal (USD)
- **Gráfico de barras horizontais**: total por mês (USD)
- **Tabela de Totais** com colunas em **USD** e **BRL**\
  (inclui a **cotação** utilizada e a **fonte**)

## Conversão USD → BRL

A conversão usa a **cotação mais recente** no momento da execução (não é histórica).\
Ordem de tentativa e exibição da **fonte**:

1. `exchangerate.host`
2. `open.er-api.com`
3. `economia.awesomeapi.com.br`\
   Se todas falharem, usa fallback **5.0**.

> ⚠️ Os valores em BRL são **aproximações** com a cotação atual, não a de cada mês.

## Endpoints utilizados

- `GET /v2/customers/my/balance`
- `GET /v2/customers/my/invoices?per_page=200&page=1`\
  (o script segue a paginação via `links.pages.next`)

## Detalhes de frontend

- Charts com **Chart.js**:\
  `https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js`
