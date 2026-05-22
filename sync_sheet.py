"""
sync_sheet.py — WealthAurora
Lê dados do Google Sheets e gera data.json para o dashboard.

Abas esperadas no Google Sheets:
  - movimentacoes  → lançamentos do banco (colados manualmente)
  - gastos_fixos   → receitas e despesas fixas
  - orcamento      → metas/limites por categoria

Variável de ambiente necessária:
  GOOGLE_CREDENTIALS → JSON da service account do Google
"""

import gspread
import json
import os
import re
from datetime import datetime, date, timedelta
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials

# ============================================================
# CONFIGURAÇÃO
# ============================================================
SHEET_ID = "SEU_SHEET_ID_AQUI"  # substitua pelo ID do seu Google Sheets

# Mapeamento: coluna "Tipo" da planilha → identificador do cartão no dashboard
# PONTO #1 CORRIGIDO: Mapeamento correto
MAPA_TIPO_CARTAO = {
    "Latam":   "7398",   # Cartão Latam 7398
    "Click":   "5217",   # Itaú Click 5217
    "Extrato": None,     # Conta corrente / débito
}

# PONTO #6 CORRIGIDO: Categorias completas para ignorar
CATEGORIAS_IGNORAR = {
    "Cartão", "Cancelamento", "Transferência", "Cofrinhos",
    "Pix", "Dívida", "Encargos", "Casa", "Empréstimo",
}

# Descrições que indicam movimentos internos — ignorar
PALAVRAS_IGNORAR = [
    "PAGAMENTO COM SALDO", "PAGAMENTO DE FATURA", "FATURA PAGA",
    "APLICACAO COFRINHOS", "PIX TRANSF CIRLENE", "PIX TRANSF FELIPE",
    "SALDO TOTAL", "REND PAGO APLIC AUT MAIS", "DEV PIX",
    "JUROS LIMITE DA CONTA", "SEGURO LIS ITAU", "SEG CARTAO PROTEGIDO",
    "JUROS DE MORA", "ENCARGOS DE ATRASO", "MULTA POR ATRASO",
    "JUROS DE FINANCIAMENTO", "REMUNERACAO", "SALARIO", "TEF CREDITO SALARIO",
    "CREDITO LIBERAD PIX", "CREDITO SAL", "PAGTO SAL",
]

# Configuração da dívida Cirlene — PONTO #5 CORRIGIDO
DIVIDA = {
    "descricao":       "Empréstimo — Cirlene",
    "valor_original":  35000,
    "parcela_mensal":  500,
    "plr_extra":       4000,
    "meses_plr":       [8, 2],   # agosto e fevereiro
    "inicio":          "2026-06",
    "total_parcelas":  30,
}

# ============================================================
# UTILITÁRIOS
# ============================================================
def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(v):
    """Converte qualquer formato de valor para float."""
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r'[R$\s]', '', str(v).strip())
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0

def parse_data(data_str):
    """Tenta vários formatos de data, retorna objeto date ou None."""
    formatos = ["%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y",
                "%d/%m/%y", "%Y/%m/%d"]
    s = str(data_str).strip()[:10]
    for fmt in formatos:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def data_para_mes(data_str):
    d = parse_data(data_str)
    return d.strftime("%Y-%m") if d else None

def data_iso(data_str):
    d = parse_data(data_str)
    return d.isoformat() if d else str(data_str)

def deve_ignorar(descricao, categoria, valor):
    """Retorna True se o lançamento deve ser ignorado."""
    if str(categoria).strip() in CATEGORIAS_IGNORAR:
        return True
    if valor == 0:
        return True
    desc_upper = str(descricao).upper()
    if any(p.upper() in desc_upper for p in PALAVRAS_IGNORAR):
        return True
    return False

def eh_receita(descricao, categoria):
    """Identifica se é lançamento de receita."""
    if str(categoria).strip() == "Salario":
        return True
    palavras = ["SALARIO", "REMUNERACAO", "TEF CREDITO SAL",
                "CRED SAL", "PAGTO SAL", "13 SALARIO", "CREDITO SAL"]
    desc_upper = str(descricao).upper()
    return any(p in desc_upper for p in palavras)

# ============================================================
# CONEXÃO COM GOOGLE SHEETS
# ============================================================
def conectar():
    escopo = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("Variável GOOGLE_CREDENTIALS não definida.")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        json.loads(creds_json), escopo
    )
    return gspread.authorize(creds)

def ler_aba(planilha, nome_aba):
    try:
        ws = planilha.worksheet(nome_aba)
        return ws.get_all_records()
    except gspread.exceptions.WorksheetNotFound:
        print(f"⚠️ Aba '{nome_aba}' não encontrada — usando padrão.")
        return []

# ============================================================
# GERAR AMORTIZAÇÃO (SEM dateutil)
# ============================================================
def gerar_amortizacao():
    """Gera cronograma de parcelas — SEM relativedelta."""
    ano_inicio, mes_inicio = map(int, DIVIDA["inicio"].split("-"))
    saldo = DIVIDA["valor_original"]
    parcelas = []

    for i in range(DIVIDA["total_parcelas"]):
        # Cálculo manual de data (PONTO #5 e sem dateutil)
        ano = ano_inicio + (mes_inicio + i - 1) // 12
        mes = (mes_inicio + i - 1) % 12 + 1
        dt = date(ano, mes, 1)
        
        eh_plr = mes in DIVIDA["meses_plr"]
        valor_parcela = DIVIDA["parcela_mensal"] + (DIVIDA["plr_extra"] if eh_plr else 0)
        saldo = max(0, saldo - valor_parcela)

        parcelas.append({
            "parcela": i + 1,
            "data": dt.isoformat(),
            "valor_total": valor_parcela,
            "mes_plr": eh_plr,
            "saldo_apos": round(saldo, 2),
            "status": "Pendente",
        })
        if saldo <= 0:
            break
    return parcelas

# ============================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================
def processar():
    print("🔄 Conectando ao Google Sheets...")
    planilha = conectar()

    # Ler abas
    dados_mov = ler_aba(planilha, "movimentacoes")
    dados_fix = ler_aba(planilha, "gastos_fixos")
    dados_orc = ler_aba(planilha, "orcamento")

    print(f"✅ {len(dados_mov)} movimentações | {len(dados_fix)} fixos | {len(dados_orc)} orçamentos")

    # PONTO #7: Limites da aba orcamento
    limites = {}
    for linha in dados_orc:
        cat = str(linha.get("Categoria", "")).strip()
        meta = limpar_valor(linha.get("Meta", 0))
        if cat and meta > 0:
            limites[cat] = meta

    # PONTO #8: Receitas e despesas fixas da aba gastos_fixos
    receitas_fixas = []
    despesas_fixas = []
    receita_mensal_fixa = 0

    for linha in dados_fix:
        tipo = str(linha.get("Tipo", "")).strip()
        categoria = str(linha.get("Categoria", "")).strip()
        subcat = str(linha.get("Subcategoria", "")).strip()
        valor = limpar_valor(linha.get("Valor", 0))

        if valor <= 0:
            continue

        item = {
            "descricao": f"{categoria} — {subcat}" if subcat else categoria,
            "categoria": categoria,
            "valor": valor
        }

        if tipo == "Receita":
            receitas_fixas.append(item)
            receita_mensal_fixa += valor
        elif tipo == "Despesa":
            despesas_fixas.append(item)

    # Se não tiver dados fixos, usa fallback
    if not receitas_fixas:
        receitas_fixas = [
            {"descricao": "Salário Felipe", "categoria": "Salário", "valor": 3600},
            {"descricao": "Salário Emanuela", "categoria": "Salário", "valor": 2700},
            {"descricao": "VA/VR Felipe", "categoria": "Benefícios", "valor": 650},
            {"descricao": "VA/VR Emanuela", "categoria": "Benefícios", "valor": 800},
        ]
        receita_mensal_fixa = sum(r["valor"] for r in receitas_fixas)

    # Processar movimentações
    gastos = []
    receitas_extrato = []

    for linha in dados_mov:
        descricao = str(linha.get("Descrição", "")).strip()
        if not descricao:
            continue

        # PONTO #2: Usa a categoria da planilha diretamente
        categoria = str(linha.get("Categoria", "Outros")).strip()
        subcateg = str(linha.get("Subcategoria", "")).strip()
        data_str = str(linha.get("Data", "")).strip()
        tipo_orig = str(linha.get("Tipo", "")).strip()
        valor_raw = linha.get("Valor", 0)
        valor = limpar_valor(valor_raw)

        if valor == 0:
            continue

        # PONTO #1: Mapeamento correto
        cartao = MAPA_TIPO_CARTAO.get(tipo_orig, None)

        if eh_receita(descricao, categoria):
            receitas_extrato.append({
                "data": data_iso(data_str),
                "descricao": descricao[:60],
                "valor": round(abs(valor), 2),
                "categoria": "Salário",
            })
            continue

        if deve_ignorar(descricao, categoria, valor):
            continue

        valor_abs = abs(valor)
        if valor_abs <= 0:
            continue

        gastos.append({
            "data": data_iso(data_str),
            "descricao": descricao[:60],
            "valor": round(valor_abs, 2),
            "categoria": categoria if categoria else "Outros",
            "subcategoria": subcateg,
            "cartao": cartao,
        })

    # Agregações mensais
    gastos_mensais = defaultdict(float)
    gastos_cat_por_mes = defaultdict(lambda: defaultdict(float))
    gastos_por_cat = defaultdict(float)
    meses = set()

    for g in gastos:
        mes = data_para_mes(g["data"])
        if mes:
            gastos_mensais[mes] += g["valor"]
            gastos_cat_por_mes[mes][g["categoria"]] += g["valor"]
            gastos_por_cat[g["categoria"]] += g["valor"]
            meses.add(mes)

    meses_sorted = sorted(meses)
    receitas_mensais = {m: receita_mensal_fixa for m in meses_sorted}

    total_gastos = round(sum(g["valor"] for g in gastos), 2)
    total_receitas = round(receita_mensal_fixa * len(meses_sorted), 2)
    saldo = round(total_receitas - total_gastos, 2)

    # Dívida
    amortizacao = gerar_amortizacao()
    hoje = date.today()
    pagas = sum(1 for p in amortizacao if parse_data(p["data"]) and parse_data(p["data"]) < hoje)
    saldo_divida = amortizacao[pagas]["saldo_apos"] if pagas < len(amortizacao) else 0

    # PONTO #10: Dados da dívida para o HTML
    payload = {
        "lastUpdate": datetime.now().isoformat(),
        "totalReceitas": total_receitas,
        "totalGastos": total_gastos,
        "saldoTotal": saldo,
        "gastosMensais": {k: round(v, 2) for k, v in sorted(gastos_mensais.items())},
        "receitasMensais": {k: round(v, 2) for k, v in sorted(receitas_mensais.items())},
        "gastosPorCategoria": {k: round(v, 2) for k, v in sorted(gastos_por_cat.items(), key=lambda x: -x[1])},
        "extrato": sorted(gastos, key=lambda x: x["data"], reverse=True)[:50],
        "limitesSugeridos": limites,
        "receitasFixas": receitas_fixas,
        "despesasRecorrentes": despesas_fixas,
        "debt": {
            "descricao": DIVIDA["descricao"],
            "valor_original": DIVIDA["valor_original"],
            "saldo_devedor": round(saldo_divida, 2),
            "parcela_mensal": DIVIDA["parcela_mensal"],
            "total_parcelas": len(amortizacao),
            "parcelas_pagas": pagas,
            "fim_previsto": amortizacao[-1]["data"][:7] if amortizacao else "—",
            "proximas_parcelas": [p for p in amortizacao if parse_data(p["data"]) and parse_data(p["data"]) >= hoje][:6],
        }
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\n✅ data.json gerado!")
    print(f"   Saldo: R$ {saldo:,.2f}")
    print(f"   Receitas: R$ {total_receitas:,.2f}")
    print(f"   Gastos: R$ {total_gastos:,.2f}")
    print(f"   Dívida restante: R$ {saldo_divida:,.2f}")

if __name__ == "__main__":
    processar()
