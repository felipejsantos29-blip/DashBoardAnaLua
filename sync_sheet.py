"""
sync_sheet.py — WealthAurora
Lê dados do Google Sheets e gera data.json para o dashboard.
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

MAPA_TIPO_CARTAO = {
    "Latam": "7398",
    "Click": "5217",
    "Extrato": None,
}

CATEGORIAS_IGNORAR = {
    "Cartão", "Cancelamento", "Transferência", "Cofrinhos",
    "Pix", "Dívida", "Encargos", "Casa", "Empréstimo",
}

PALAVRAS_IGNORAR = [
    "PAGAMENTO COM SALDO", "PAGAMENTO DE FATURA", "FATURA PAGA",
    "APLICACAO COFRINHOS", "PIX TRANSF", "SALDO TOTAL",
]

DIVIDA = {
    "descricao": "Empréstimo — Cirlene",
    "valor_original": 35000,
    "parcela_mensal": 500,
    "plr_extra": 4000,
    "meses_plr": [8, 2],
    "inicio": "2026-06",
    "total_parcelas": 30,
}

RECEITAS_FIXAS_PADRAO = [
    {"descricao": "Salário Felipe", "categoria": "Salário", "valor": 3600},
    {"descricao": "Salário Emanuela", "categoria": "Salário", "valor": 2700},
    {"descricao": "VA/VR Felipe", "categoria": "Benefícios", "valor": 650},
    {"descricao": "VA/VR Emanuela", "categoria": "Benefícios", "valor": 800},
]

DESPESAS_FIXAS_PADRAO = [
    {"descricao": "Aluguel", "categoria": "Moradia", "valor": 1500},
    {"descricao": "Condomínio", "categoria": "Moradia", "valor": 300},
    {"descricao": "Luz", "categoria": "Casa", "valor": 150},
    {"descricao": "Internet", "categoria": "Casa", "valor": 100},
]

LIMITES_PADRAO = {
    "Alimentação": 1500, "Transporte": 800, "Lazer": 500,
    "Saúde": 500, "Pet": 300, "Telefonia": 200, "Assinatura": 150,
}

# ============================================================
# FUNÇÕES UTILITÁRIAS (TODAS DEFINIDAS ANTES DE SEREM USADAS)
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
# CONEXÃO
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
    cliente = gspread.authorize(creds)
    planilha = cliente.open_by_key(SHEET_ID)
    return planilha

# ============================================================
# AMORTIZAÇÃO
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
            "parcela": i+1,
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

    # Localizar aba de movimentações
    aba_nome = None
    for nome in ["movimentacoes", "Página1", "Extrato"]:
        try:
            planilha.worksheet(nome)
            aba_nome = nome
            break
        except:
            continue
    if not aba_nome:
        raise Exception("Nenhuma aba de movimentações encontrada.")
    print(f"✅ Aba '{aba_nome}' encontrada.")
    dados_mov = planilha.worksheet(aba_nome).get_all_records()
    print(f"   {len(dados_mov)} lançamentos carregados.")

    # Fallback para abas que não existem
    print("⚠️ Abas 'gastos_fixos' e 'orcamento' não encontradas. Usando valores padrão.")
    receitas_fixas = RECEITAS_FIXAS_PADRAO
    despesas_fixas = DESPESAS_FIXAS_PADRAO
    receita_mensal_fixa = sum(r["valor"] for r in receitas_fixas)
    limites = LIMITES_PADRAO

    # Processar cada linha
    gastos = []
    receitas_extrato = []

    for linha in dados_mov:
        data_str = str(linha.get("Data", "")).strip()
        descricao = str(linha.get("Descrição", "")).strip()
        valor_raw = linha.get("Valor", 0)
        valor = limpar_valor(valor_raw)  # <--- AGORA ESTÁ DEFINIDA
        tipo_orig = str(linha.get("Tipo", "")).strip()
        categoria = str(linha.get("Categoria", "Outros")).strip()
        subcategoria = str(linha.get("Subcategoria", "")).strip()

        if not descricao or valor == 0:
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
            "categoria": categoria,
            "subcategoria": subcategoria,
            "cartao": cartao,
        })

    # Agregações
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
    taxa_esforco = round(total_gastos / total_receitas * 100, 2) if total_receitas > 0 else 0

    variacao = 0.0
    if len(meses_sorted) >= 2:
        g_ant = gastos_mensais.get(meses_sorted[-2], 0)
        g_atu = gastos_mensais.get(meses_sorted[-1], 0)
        variacao = round((g_atu - g_ant) / g_ant * 100, 1) if g_ant > 0 else 0

    media_mensal = total_gastos / max(len(meses_sorted), 1)
    media_diaria = round(media_mensal / 30, 2)
    dias_reserva = round(max(0, saldo_total) / media_diaria, 0) if media_diaria > 0 else 0
    cap_poupanca = round((total_receitas - total_gastos) / total_receitas * 100, 2) if total_receitas > 0 else 0
    mes_atual = meses_sorted[-1] if meses_sorted else None
    gastos_cat_atual = dict(gastos_cat_por_mes.get(mes_atual, {})) if mes_atual else {}
    over_limits = sum(1 for c, l in limites.items() if gastos_cat_atual.get(c, 0) > l)

    def calc_score(cap, dias, over):
        poup = 30 if cap >= 20 else 15 if cap >= 10 else 0
        res = 25 if dias >= 180 else 15 if dias >= 90 else 5 if dias >= 30 else 0
        lim = 20 if over == 0 else 10 if over == 1 else 0
        return poup + res + lim + 25

    score = calc_score(cap_poupanca, dias_reserva, over_limits)

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
        total_desp_ate = sum(gastos_mensais.get(m, 0) for m in meses_sorted[:i+1])
        med_diaria_mes = round(total_desp_ate / ((i+1)*30), 2)
        dias_res_mes = round(max(0, saldo_acumulado) / med_diaria_mes, 0) if med_diaria_mes > 0 else 0
        cap_mes = round((rec_mes - desp_mes) / rec_mes * 100, 2) if rec_mes > 0 else 0
        over_mes = sum(1 for c, l in limites.items() if gastos_cat_por_mes[mes].get(c, 0) > l)
        score_mes = calc_score(cap_mes, dias_res_mes, over_mes)
        score_historico[mes] = score_mes
        cats_mes = {k: round(v,2) for k,v in sorted(gastos_cat_por_mes[mes].items(), key=lambda x: -x[1])}
        top_cat = list(cats_mes.items())[0] if cats_mes else ("—", 0)
        comparacao_mensal[mes] = {
            "receitas": round(rec_mes,2),
            "despesas": round(desp_mes,2),
            "saldo": round(rec_mes - desp_mes,2),
            "taxa_esforco": round(desp_mes/rec_mes*100,2) if rec_mes>0 else 0,
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
    meses_proj = ["Jun/26","Jul/26","Ago/26","Set/26","Out/26","Nov/26","Dez/26"]
    for i, label in enumerate(meses_proj):
        mes_num = i+6
        eh_plr = mes_num in DIVIDA["meses_plr"]
        parcela_proj = DIVIDA["parcela_mensal"] + (DIVIDA["plr_extra"] if eh_plr else 0)
        projecao.append({
            "mes": label,
            "salario_previsto": receita_mensal_fixa,
            "despesas_recorrentes": sum(d["valor"] for d in despesas_fixas if d["categoria"] not in ("Moradia",)),
            "parcela_emprestimo": DIVIDA["parcela_mensal"],
            "parcela_semestral": DIVIDA["plr_extra"] if eh_plr else 0,
        })

    custos_essenciais = {
        "ana_lua": [{"nome": "Saúde", "valor": 200}],
        "mandelinha": [{"nome": "Pet", "valor": 150}],
    }

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
        "gastosMensais": {k: round(v,2) for k,v in sorted(gastos_mensais.items())},
        "receitasMensais": {k: round(v,2) for k,v in sorted(receitas_mensais.items())},
        "mesesDisponiveis": meses_sorted,
        "comparacaoMensal": comparacao_mensal,
        "scoreHistorico": score_historico,
        "gastosPorCategoria": {k: round(v,2) for k,v in sorted(gastos_por_cat.items(), key=lambda x: -x[1])},
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

    print(f"\n✅ data.json gerado com sucesso!")
    print(f"   Saldo:   {brl(saldo_total)}")
    print(f"   Score:   {score}/100")
    print(f"   Alertas: {len(alertas)}")
    print(f"   Meses:   {len(meses_sorted)}")
    print(f"   Dívida:  {brl(saldo_divida)} restantes")

if __name__ == "__main__":
    processar()
