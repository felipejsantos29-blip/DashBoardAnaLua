import gspread
import json
import os
import re
from datetime import datetime
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials

# ============================================================
# UTILITÁRIO DE FORMATAÇÃO
# ============================================================
def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ============================================================
# CONFIGURAÇÕES
# ============================================================
SHEET_ID   = "1BGYyMz9BZ0ypEaJfv5InDWwVZ73iK58p9W-QOsBY3Gk"
SHEET_NAME = "movimentacoes"

# Categorias e palavras que devem ser ignoradas
CATEGORIAS_IGNORAR = {
    "pagamento cartão", "investimento", "empréstimo",
    "transferência", "reembolso", "rendimento", "depósito",
    "pagamento de fatura",
}
PALAVRAS_IGNORAR = [
    "FATURA PAGA", "APLICACAO COFRINHOS", "PIX TRANSF CIRLENE",
    "PIX TRANSF FELIPE", "SALDO TOTAL", "REND PAGO APLIC AUT MAIS",
    "DEV PIX", "JUROS LIMITE DA CONTA", "SEGURO LIS ITAU",
    "SEG CARTAO PROTEGIDO", "JUROS DE MORA", "ENCARGOS DE ATRASO",
    "MULTA POR ATRASO", "JUROS DE FINANCIAMENTO",
]

# Mapeamento de palavras-chave para categorias
REGRA_CATEGORIA = {
    "UBER": "Transporte", "99APP": "Transporte", "99 TECNOLOGIA": "Transporte",
    "TOP SP": "Transporte", "TOP SP TARFA": "Transporte",
    "IFOOD": "Alimentação", "IFD": "Alimentação", "MERCADO": "Alimentação",
    "RESTAURANTE": "Alimentação", "LANCHE": "Alimentação", "MP*MELIMAIS": "Alimentação",
    "FARMACIA": "Saúde", "DROGARIA": "Saúde", "UNIMED": "Saúde",
    "PETLOVE": "Pet", "PET": "Pet",
    "CLARO": "Serviços", "VIVO": "Serviços", "TIM": "Serviços",
    "SPOTIFY": "Streaming", "NETFLIX": "Streaming", "AMAZON PRIME": "Streaming",
    "AMAZON": "Compras", "SHOPEE": "Compras", "MAGALU": "Compras",
    "AIRBNB": "Viagem", "HOTEL": "Viagem",
    "ESCOLA": "Educação", "FACULDADE": "Educação",
    "SALARIO": "Salário", "REMUNERACAO": "Salário",
    "IOF": "Taxas Bancárias",
    "ESSENCIALLOCACOES": "Moradia",
}

LIMITES_SUGERIDOS = {
    "Alimentação": 1500,
    "Transporte": 400,
    "Compras": 600,
    "Saúde": 300,
    "Streaming": 100,
    "Serviços": 200,
    "Pet": 200,
    "Outros": 500,
}

DIVIDA_CIRLENE = {
    "valor_original": 35000,
    "parcela_mensal": 500,
    "plr_extra": 4000,
    "meses_plr": [8, 2],
    "inicio": "2026-06",
    "fim_previsto": "2028-11",
    "total_parcelas": 30,
    "proximas_parcelas": [
        {"parcela": 1, "data": "2026-06-01", "valor_total": 500,  "mes_plr": False},
        {"parcela": 2, "data": "2026-07-01", "valor_total": 500,  "mes_plr": False},
        {"parcela": 3, "data": "2026-08-01", "valor_total": 4500, "mes_plr": True},
        {"parcela": 4, "data": "2026-09-01", "valor_total": 500,  "mes_plr": False},
        {"parcela": 5, "data": "2026-10-01", "valor_total": 500,  "mes_plr": False},
    ]
}

# ============================================================
# UTILITÁRIOS
# ============================================================
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
    """Tenta vários formatos de data, retorna objeto date ou None."""
    formatos = ["%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"]
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
    if categoria.lower() in CATEGORIAS_IGNORAR:
        return True
    desc = descricao.upper()
    if any(p.upper() in desc for p in PALAVRAS_IGNORAR):
        return True
    if "EMANUEL" in desc and abs(valor) > 100:
        return True
    return False

def definir_categoria(descricao):
    desc = descricao.upper()
    for palavra, cat in REGRA_CATEGORIA.items():
        if palavra.upper() in desc:
            return cat
    return "Outros"

def eh_receita(descricao):
    palavras = [
        "SALARIO", "REMUNERACAO", "TEF CREDITO", "CRED SAL",
        "PAGTO SAL", "DEPOSITO SAL", "13 SALARIO", "BONUS",
        "PAGAMENTO SAL", "CREDITO SAL",
    ]
    return any(p in descricao.upper() for p in palavras)

# ============================================================
# CÁLCULO DE SCORE MENSAL
# ============================================================
def calcular_score_mensal(
    gastos_mes, receitas_mes,
    saldo_acumulado, media_diaria,
    gastos_cat_mes, limites,
    divida_pts=25
):
    """
    Calcula o score financeiro para um mês específico.
    Retorna o score total (0–100) e os pontos por componente.
    """
    total_rec  = sum(receitas_mes.values())
    total_desp = sum(gastos_mes.values())
    saldo_mes  = total_rec - total_desp

    # Capacidade de poupança no mês
    cap_poupy = round(saldo_mes / total_rec * 100, 2) if total_rec > 0 else 0

    # Reserva (usa saldo acumulado até aquele mês)
    dias_reserva = round(saldo_acumulado / media_diaria, 0) if media_diaria > 0 else 0

    # Limites violados no mês
    over_count = sum(
        1 for c, l in limites.items()
        if gastos_cat_mes.get(c, 0) > l
    )

    poup_pts = 30 if cap_poupy >= 20 else 15 if cap_poupy >= 10 else 0
    res_pts  = 25 if dias_reserva >= 180 else 15 if dias_reserva >= 90 else 5 if dias_reserva >= 30 else 0
    lim_pts  = 20 if over_count == 0 else 10 if over_count == 1 else 0
    score    = poup_pts + res_pts + lim_pts + divida_pts

    return {
        "score": score,
        "poup_pts": poup_pts,
        "res_pts": res_pts,
        "lim_pts": lim_pts,
        "div_pts": divida_pts,
        "cap_poupanca": cap_poupy,
        "dias_reserva": int(dias_reserva),
        "over_limits": over_count,
    }

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
        raise Exception("GOOGLE_CREDENTIALS não definida.")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        json.loads(creds_json), escopo
    )
    cliente = gspread.authorize(creds)
    return cliente.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

# ============================================================
# PROCESSAMENTO
# ============================================================
def processar():
    print("🔄 Conectando à planilha...")
    ws = conectar()
    dados = ws.get_all_records()
    print(f"✅ {len(dados)} linhas encontradas.")

    gastos, receitas = [], []

    for linha in dados:
        descricao = str(linha.get("descrição", "")).strip()
        if not descricao:
            continue

        categoria_bruta = str(linha.get("categoria", "")).strip()
        data_str        = str(linha.get("data", "")).strip()
        cartao_final    = str(linha.get("cartao_final", "")).strip()

        valor = limpar_valor(linha.get("valor", 0))
        if valor == 0:
            continue

        if deve_ignorar(descricao, categoria_bruta, valor):
            continue

        data_formatada = data_iso(data_str)

        if valor < 0:  # Despesa
            cat    = definir_categoria(descricao)
            cartao = cartao_final if cartao_final not in ("", "None", "nan") else None
            gastos.append({
                "data":      data_formatada,
                "descricao": descricao[:60],
                "valor":     round(abs(valor), 2),
                "categoria": cat,
                "cartao":    cartao,
            })
        elif valor > 0 and eh_receita(descricao):  # Receita
            receitas.append({
                "data":      data_formatada,
                "descricao": descricao[:60],
                "valor":     round(valor, 2),
                "categoria": "Salário",
            })

    print(f"📊 {len(gastos)} gastos | {len(receitas)} receitas")
    return gastos, receitas

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    gastos, receitas = processar()

    total_gastos   = round(sum(g["valor"] for g in gastos), 2)
    total_receitas = round(sum(r["valor"] for r in receitas), 2)
    saldo          = round(total_receitas - total_gastos, 2)
    taxa_esforco   = round(total_gastos / total_receitas * 100, 2) if total_receitas > 0 else 0

    gastos_mensais    = defaultdict(float)
    receitas_mensais  = defaultdict(float)
    gastos_por_cat    = defaultdict(float)
    gastos_por_cartao = defaultdict(lambda: {"nome": "", "total": 0.0, "count": 0})
    gastos_cat_por_mes = defaultdict(lambda: defaultdict(float))  # {mes: {cat: valor}}
    meses             = set()

    for g in gastos:
        mes = data_para_mes(g["data"])
        if mes:
            gastos_mensais[mes]              += g["valor"]
            gastos_por_cat[g["categoria"]]   += g["valor"]
            gastos_cat_por_mes[mes][g["categoria"]] += g["valor"]
            meses.add(mes)
        c = g.get("cartao") or "debito"
        gastos_por_cartao[c]["total"] += g["valor"]
        gastos_por_cartao[c]["count"] += 1
        gastos_por_cartao[c]["nome"]   = (
            "Itaú 5217"   if c == "5217" else
            "Latam 7398"  if c == "7398" else
            "Conta/Débito"
        )

    for r in receitas:
        mes = data_para_mes(r["data"])
        if mes:
            receitas_mensais[mes] += r["valor"]
            meses.add(mes)

    meses_sorted = sorted(meses)

    # Gastos do mês mais recente
    mes_atual = meses_sorted[-1] if meses_sorted else None
    gastos_cat_mes_atual = dict(gastos_cat_por_mes.get(mes_atual, {})) if mes_atual else {}

    # Variação de gastos mês a mês
    variacao = 0.0
    if len(meses_sorted) >= 2:
        m_ant = gastos_mensais.get(meses_sorted[-2], 0)
        m_atu = gastos_mensais.get(meses_sorted[-1], 0)
        variacao = round((m_atu - m_ant) / m_ant * 100, 1) if m_ant > 0 else 0.0

    # Alertas: categorias acima do limite no mês atual
    alertas = []
    for cat, lim in LIMITES_SUGERIDOS.items():
        gasto = gastos_cat_mes_atual.get(cat, 0)
        if gasto > lim:
            alertas.append(f"🚨 {cat}: {brl(gasto)} (limite {brl(lim)})")

    # ── Métricas globais ─────────────────────────────────────
    cap_poupy    = round(saldo / total_receitas * 100, 2) if total_receitas > 0 else 0
    media_mensal = total_gastos / max(len(meses_sorted), 1)
    media_diaria = round(media_mensal / 30, 2)
    dias_reserva = round(saldo / media_diaria, 0) if media_diaria > 0 else 0

    over_count = sum(1 for c, l in LIMITES_SUGERIDOS.items() if gastos_cat_mes_atual.get(c, 0) > l)
    poup_pts   = 30 if cap_poupy >= 20 else 15 if cap_poupy >= 10 else 0
    res_pts    = 25 if dias_reserva >= 180 else 15 if dias_reserva >= 90 else 5 if dias_reserva >= 30 else 0
    lim_pts    = 20 if over_count == 0 else 10 if over_count == 1 else 0
    div_pts    = 25
    score      = poup_pts + res_pts + lim_pts + div_pts

    # ── NOVO: Score histórico por mês ────────────────────────
    # Calcula score mês a mês para o gráfico de tendência de score
    score_historico = {}
    saldo_acumulado_ate = 0.0

    for mes in meses_sorted:
        rec_mes  = receitas_mensais.get(mes, 0)
        desp_mes = gastos_mensais.get(mes, 0)
        saldo_acumulado_ate += rec_mes - desp_mes

        # Média diária até este mês (rolling)
        idx = meses_sorted.index(mes)
        total_desp_ate = sum(gastos_mensais.get(m, 0) for m in meses_sorted[:idx+1])
        media_diaria_mes = round(total_desp_ate / ((idx + 1) * 30), 2) if idx >= 0 else 0

        resultado = calcular_score_mensal(
            gastos_mes   = {mes: desp_mes},
            receitas_mes = {mes: rec_mes},
            saldo_acumulado = saldo_acumulado_ate,
            media_diaria    = media_diaria_mes,
            gastos_cat_mes  = dict(gastos_cat_por_mes.get(mes, {})),
            limites         = LIMITES_SUGERIDOS,
        )
        score_historico[mes] = resultado

    # ── NOVO: Comparação detalhada mês a mês ─────────────────
    comparacao_mensal = {}
    for mes in meses_sorted:
        rec  = round(receitas_mensais.get(mes, 0), 2)
        desp = round(gastos_mensais.get(mes, 0), 2)
        saldo_mes = round(rec - desp, 2)
        esforco   = round(desp / rec * 100, 2) if rec > 0 else 0

        cats_mes = {
            k: round(v, 2)
            for k, v in sorted(
                gastos_cat_por_mes[mes].items(),
                key=lambda x: -x[1]
            )
        }
        top_cat = list(cats_mes.items())[0] if cats_mes else ("—", 0)

        comparacao_mensal[mes] = {
            "receitas":     rec,
            "despesas":     desp,
            "saldo":        saldo_mes,
            "taxa_esforco": esforco,
            "score":        score_historico.get(mes, {}).get("score", 0),
            "top_categoria": {"nome": top_cat[0], "valor": top_cat[1]},
            "categorias":   cats_mes,
        }

    # ── Saldo devedor da dívida Cirlene ──────────────────────
    parcelas_pagas = sum(1 for g in gastos if "CIRLENE" in g["descricao"].upper())
    plr_pago       = sum(g["valor"] for g in gastos if "CIRLENE" in g["descricao"].upper() and g["valor"] > 500)
    saldo_divida   = round(35000 - (parcelas_pagas * 500) - plr_pago, 2)

    # ── Payload final ────────────────────────────────────────
    payload = {
        "lastUpdate": datetime.now().isoformat(),

        # Totais
        "totalReceitas": total_receitas,
        "totalGastos":   total_gastos,
        "saldoTotal":    saldo,
        "taxaEsforco":   taxa_esforco,

        # Saúde financeira
        "scoreFinanceiro":  score,
        "capPoupanca":      cap_poupy,
        "diasReserva":      dias_reserva,
        "mediaDiaria":      media_diaria,
        "variacaoGastoMes": variacao,

        # Mensais
        "gastosMensais":    {k: round(v, 2) for k, v in sorted(gastos_mensais.items())},
        "receitasMensais":  {k: round(v, 2) for k, v in sorted(receitas_mensais.items())},
        "mesesDisponiveis": meses_sorted,

        # NOVO: Comparação mensal detalhada
        "comparacaoMensal": comparacao_mensal,

        # NOVO: Score histórico por mês (para gráfico de evolução do score)
        "scoreHistorico": {
            mes: dados["score"]
            for mes, dados in score_historico.items()
        },

        # Categorias
        "gastosPorCategoria": {
            k: round(v, 2)
            for k, v in sorted(gastos_por_cat.items(), key=lambda x: -x[1])
        },
        "gastosCatMesAtual": {k: round(v, 2) for k, v in gastos_cat_mes_atual.items()},
        "limitesSugeridos":  LIMITES_SUGERIDOS,

        # Cartões
        "gastosPorCartao": {
            k: {"nome": v["nome"], "total": round(v["total"], 2), "count": v["count"]}
            for k, v in gastos_por_cartao.items()
        },

        # Extrato
        "extrato":  sorted(gastos,   key=lambda x: x["data"], reverse=True),
        "receitas": sorted(receitas, key=lambda x: x["data"], reverse=True),

        # Alertas
        "alertas": alertas,

        # Dívida
        "debt": {
            **DIVIDA_CIRLENE,
            "saldo_devedor":  saldo_divida,
            "parcelas_pagas": parcelas_pagas,
        },

        # Stats
        "stats": {
            "total_transacoes": len(gastos) + len(receitas),
            "meses_com_dados":  len(meses_sorted),
            "total_receitas":   len(receitas),
        },
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\n✅ data.json gerado com sucesso!")
    print(f"   Saldo: {brl(saldo)} | Score: {score}/100 | Alertas: {len(alertas)}")
    print(f"   Meses processados: {len(meses_sorted)} | Score histórico: {len(score_historico)} entradas")

    # Preview da comparação dos 2 últimos meses
    if len(meses_sorted) >= 2:
        m_ant = meses_sorted[-2]
        m_atu = meses_sorted[-1]
        print(f"\n📅 Comparação {m_ant} → {m_atu}:")
        for campo in ("receitas", "despesas", "saldo", "taxa_esforco", "score"):
            v_ant = comparacao_mensal[m_ant].get(campo, 0)
            v_atu = comparacao_mensal[m_atu].get(campo, 0)
            delta = round((v_atu - v_ant) / abs(v_ant) * 100, 1) if v_ant else 0
            seta  = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            print(f"   {campo:16s}: {v_ant:>10.2f} → {v_atu:>10.2f}  {seta} {abs(delta)}%")
