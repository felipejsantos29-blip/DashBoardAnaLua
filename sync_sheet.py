"""
sync_sheet.py — WealthAurora
Lê dados do Google Sheets e gera data.json para o dashboard.

Abas no Google Sheets (já configuradas):
  - movimentacoes  → lançamentos do banco
  - gastos_fixos   → receitas e despesas fixas
  - orcamento      → metas/limites por categoria
"""

import gspread
import json
import os
import re
from datetime import datetime, date
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials

# ============================================================
# CONFIGURAÇÃO
# ============================================================
SHEET_ID = "1BGYyMz9BZ0ypEaJfv5InDWwVZ73iK58p9W-QOsBY3Gk"

# Mapeamento: coluna "Tipo" da planilha → identificador do cartão
MAPA_TIPO_CARTAO = {
    "Latam": "7398",
    "Click": "5217",
    "Extrato": None,
}

# Categorias para ignorar (movimentos internos)
CATEGORIAS_IGNORAR = {
    "Cartão", "Cancelamento", "Transferência", "Cofrinhos",
    "Pix", "Dívida", "Encargos", "Casa", "Empréstimo",
}

# Descrições que indicam movimentos internos
PALAVRAS_IGNORAR = [
    "PAGAMENTO COM SALDO", "PAGAMENTO DE FATURA", "FATURA PAGA",
    "APLICACAO COFRINHOS", "PIX TRANSF CIRLENE", "PIX TRANSF FELIPE",
    "SALDO TOTAL", "REND PAGO APLIC AUT MAIS", "DEV PIX",
    "JUROS LIMITE DA CONTA", "SEGURO LIS ITAU", "SEG CARTAO PROTEGIDO",
    "JUROS DE MORA", "ENCARGOS DE ATRASO", "MULTA POR ATRASO",
    "JUROS DE FINANCIAMENTO",
]

# Configuração da dívida Cirlene
DIVIDA = {
    "descricao": "Empréstimo — Cirlene",
    "valor_original": 35000,
    "parcela_mensal": 500,
    "plr_extra": 4000,
    "meses_plr": [8, 2],  # agosto e fevereiro
    "inicio": "2026-06",
    "total_parcelas": 30,
}

# ============================================================
# UTILITÁRIOS
# ============================================================
def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def limpar_valor(v):
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
    formatos = ["%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"]
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
    if str(categoria).strip() in CATEGORIAS_IGNORAR:
        return True
    if valor == 0:
        return True
    desc_upper = str(descricao).upper()
    if any(p.upper() in desc_upper for p in PALAVRAS_IGNORAR):
        return True
    return False

def eh_receita(descricao, categoria):
    if str(categoria).strip() == "Salario":
        return True
    palavras = ["SALARIO", "REMUNERACAO", "TEF CREDITO SAL", "CRED SAL", "PAGTO SAL"]
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
        print(f"⚠️ Aba '{nome_aba}' não encontrada")
        return []

# ============================================================
# GERAR AMORTIZAÇÃO (SEM dateutil)
# ============================================================
def gerar_amortizacao():
    ano_inicio, mes_inicio = map(int, DIVIDA["inicio"].split("-"))
    saldo = DIVIDA["valor_original"]
    parcelas = []

    for i in range(DIVIDA["total_parcelas"]):
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

    # Limites da aba orcamento
    limites = {}
    for linha in dados_orc:
        cat = str(linha.get("Categoria", "")).strip()
        meta = limpar_valor(linha.get("Meta", 0))
        if cat and meta > 0:
            limites[cat] = meta

    # Receitas e despesas fixas
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
            "valor": round(valor, 2)
        }

        if tipo == "Receita":
            receitas_fixas.append(item)
            receita_mensal_fixa += valor
        elif tipo == "Despesa":
            despesas_fixas.append(item)

    # Processar movimentações
    gastos = []
    receitas_extrato = []

    for linha in dados_mov:
        descricao = str(linha.get("Descrição", "")).strip()
        if not descricao:
            continue

        categoria = str(linha.get("Categoria", "Outros")).strip()
        subcateg = str(linha.get("Subcategoria", "")).strip()
        data_str = str(linha.get("Data", "")).strip()
        tipo_orig = str(linha.get("Tipo", "")).strip()
        valor = limpar_valor(linha.get("Valor", 0))

        if valor == 0:
            continue

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
    receitas_mensais = {}
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
    for mes in meses_sorted:
        receitas_mensais[mes] = receita_mensal_fixa

    total_gastos = round(sum(gastos_mensais.values()), 2)
    total_receitas = round(receita_mensal_fixa * len(meses_sorted), 2)
    saldo_total = round(total_receitas - total_gastos, 2)

    # Taxa de esforço
    taxa_esforco = round(total_gastos / total_receitas * 100, 2) if total_receitas > 0 else 0

    # Mês atual
    mes_atual = meses_sorted[-1] if meses_sorted else None

    # Variação
    variacao = 0.0
    if len(meses_sorted) >= 2:
        g_ant = gastos_mensais.get(meses_sorted[-2], 0)
        g_atu = gastos_mensais.get(meses_sorted[-1], 0)
        variacao = round((g_atu - g_ant) / g_ant * 100, 1) if g_ant > 0 else 0

    # Score
    cap_poupanca = round(saldo_total / total_receitas * 100, 2) if total_receitas > 0 else 0
    media_mensal = total_gastos / max(len(meses_sorted), 1)
    media_diaria = round(media_mensal / 30, 2) if media_mensal > 0 else 0
    dias_reserva = round(max(0, saldo_total) / media_diaria, 0) if media_diaria > 0 else 0

    gastos_cat_atual = dict(gastos_cat_por_mes.get(mes_atual, {})) if mes_atual else {}
    over_limits = sum(1 for c, l in limites.items() if gastos_cat_atual.get(c, 0) > l)

    def calcular_score(cap, dias, over):
        poup_pts = 30 if cap >= 20 else 15 if cap >= 10 else 0
        res_pts = 25 if dias >= 180 else 15 if dias >= 90 else 5 if dias >= 30 else 0
        lim_pts = 20 if over == 0 else 10 if over == 1 else 0
        div_pts = 25  # assumindo dívida em dia
        return poup_pts + res_pts + lim_pts + div_pts

    score = calcular_score(cap_poupanca, dias_reserva, over_limits)

    # Alertas
    alertas = []
    for cat, lim in limites.items():
        gasto = gastos_cat_atual.get(cat, 0)
        if gasto > lim:
            alertas.append(f"🚨 {cat}: {brl(gasto)} (limite {brl(lim)})")

    # Score histórico
    score_historico = {}
    comparacao_mensal = {}
    saldo_acumulado = 0

    for i, mes in enumerate(meses_sorted):
        rec_mes = receita_mensal_fixa
        desp_mes = gastos_mensais.get(mes, 0)
        saldo_acumulado += rec_mes - desp_mes

        total_desp_ate = sum(gastos_mensais.get(m, 0) for m in meses_sorted[:i + 1])
        med_diaria_mes = round(total_desp_ate / ((i + 1) * 30), 2)
        dias_res_mes = round(max(0, saldo_acumulado) / med_diaria_mes, 0) if med_diaria_mes > 0 else 0
        cap_mes = round((rec_mes - desp_mes) / rec_mes * 100, 2) if rec_mes > 0 else 0
        over_mes = sum(1 for c, l in limites.items() if gastos_cat_por_mes[mes].get(c, 0) > l)
        score_mes = calcular_score(cap_mes, dias_res_mes, over_mes)

        score_historico[mes] = score_mes

        cats_mes = {k: round(v, 2) for k, v in sorted(gastos_cat_por_mes[mes].items(), key=lambda x: -x[1])}
        top_cat = list(cats_mes.items())[0] if cats_mes else ("—", 0)

        comparacao_mensal[mes] = {
            "receitas": round(rec_mes, 2),
            "despesas": round(desp_mes, 2),
            "saldo": round(rec_mes - desp_mes, 2),
            "taxa_esforco": round(desp_mes / rec_mes * 100, 2) if rec_mes > 0 else 0,
            "score": score_mes,
            "top_categoria": {"nome": top_cat[0], "valor": top_cat[1]},
            "categorias": cats_mes,
        }

    # Dívida
    amortizacao = gerar_amortizacao()
    hoje = date.today()
    pagas = sum(1 for p in amortizacao if parse_data(p["data"]) and parse_data(p["data"]) < hoje)
    saldo_divida = amortizacao[pagas]["saldo_apos"] if pagas < len(amortizacao) else 0
    fim_previsto = amortizacao[-1]["data"][:7] if amortizacao else "—"
    proximas = [p for p in amortizacao if parse_data(p["data"]) and parse_data(p["data"]) >= hoje][:6]

    # Projeção
    projecao = []
    meses_proj = ["Jun/26", "Jul/26", "Ago/26", "Set/26", "Out/26", "Nov/26", "Dez/26"]
    for i, label in enumerate(meses_proj):
        mes_num = i + 6
        eh_plr = mes_num in DIVIDA["meses_plr"]
        parcela_proj = DIVIDA["parcela_mensal"] + (DIVIDA["plr_extra"] if eh_plr else 0)
        projecao.append({
            "mes": label,
            "salario_previsto": receita_mensal_fixa,
            "despesas_recorrentes": sum(d["valor"] for d in despesas_fixas if d["categoria"] not in ("Moradia",)),
            "parcela_emprestimo": DIVIDA["parcela_mensal"],
            "parcela_semestral": DIVIDA["plr_extra"] if eh_plr else 0,
        })

    # Custos essenciais (envelopes)
    custos_essenciais = {
        "ana_lua": [
            {"nome": item["descricao"].split("—")[-1].strip(), "valor": item["valor"]}
            for item in despesas_fixas if "Ana Lua" in item.get("categoria", "")
        ],
        "mandelinha": [
            {"nome": item["descricao"].split("—")[-1].strip(), "valor": item["valor"]}
            for item in despesas_fixas if "Mandelinha" in item.get("categoria", "")
        ],
    }

    # Payload final
    payload = {
        "lastUpdate": datetime.now().isoformat(),
        "totalReceitas": total_receitas,
        "totalGastos": total_gastos,
        "saldoTotal": saldo_total,
        "taxaEsforco": taxa_esforco,
        "scoreFinanceiro": score,
        "capPoupanca": cap_poupanca,
        "diasReserva": int(dias_reserva),
        "mediaDiaria": media_diaria,
        "variacaoGastoMes": variacao,
        "gastosMensais": {k: round(v, 2) for k, v in sorted(gastos_mensais.items())},
        "receitasMensais": {k: round(v, 2) for k, v in sorted(receitas_mensais.items())},
        "mesesDisponiveis": meses_sorted,
        "comparacaoMensal": comparacao_mensal,
        "scoreHistorico": score_historico,
        "gastosPorCategoria": {k: round(v, 2) for k, v in sorted(gastos_por_cat.items(), key=lambda x: -x[1])},
        "gastosCatMesAtual": gastos_cat_atual,
        "limitesSugeridos": limites,
        "extrato": sorted(gastos, key=lambda x: x["data"], reverse=True),
        "receitas": sorted(receitas_extrato, key=lambda x: x["data"], reverse=True),
        "alertas": alertas,
        "debt": {
            "descricao": DIVIDA["descricao"],
            "valor_original": DIVIDA["valor_original"],
            "parcela_mensal": DIVIDA["parcela_mensal"],
            "plr_extra": DIVIDA["plr_extra"],
            "total_parcelas": len(amortizacao),
            "parcelas_pagas": pagas,
            "saldo_devedor": round(saldo_divida, 2),
            "fim_previsto": fim_previsto,
            "proximas_parcelas": proximas,
            "amortizacao": amortizacao,
        },
        "receitasFixas": receitas_fixas,
        "despesasRecorrentes": despesas_fixas,
        "custosEssenciais": custos_essenciais,
        "projecaoMensal": projecao,
        "stats": {
            "total_transacoes": len(gastos) + len(receitas_extrato),
            "meses_com_dados": len(meses_sorted),
            "total_receitas": len(receitas_extrato),
        },
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\n✅ data.json gerado!")
    print(f"   Saldo:   {brl(saldo_total)}")
    print(f"   Score:   {score}/100")
    print(f"   Alertas: {len(alertas)}")
    print(f"   Meses:   {len(meses_sorted)}")
    print(f"   Dívida:  {brl(saldo_divida)} restantes")

    if len(meses_sorted) >= 2:
        m_ant = meses_sorted[-2]
        m_atu = meses_sorted[-1]
        print(f"\n📅 {m_ant} → {m_atu}:")
        for campo in ("receitas", "despesas", "saldo", "taxa_esforco", "score"):
            v_ant = comparacao_mensal[m_ant].get(campo, 0)
            v_atu = comparacao_mensal[m_atu].get(campo, 0)
            delta = round((v_atu - v_ant) / abs(v_ant) * 100, 1) if v_ant else 0
            seta = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            print(f"   {campo:16s}: {v_ant:>10.2f} → {v_atu:>10.2f}  {seta} {abs(delta)}%")


if __name__ == "__main__":
    processar()
