"""
WealthAurora – sync_sheet.py
Lê a planilha Google Sheets e gera o data.json consumido pelo dashboard.

REGRAS DE NEGÓCIO IMPLEMENTADAS:
1. Pagamento de fatura de cartão (Click / Latam) NÃO é contabilizado como gasto —
   cada linha de cartão já entrou individualmente; só o débito final seria duplicata.
2. PLR / 13º pago em Agosto e Fevereiro. O empréstimo de R$35k tem:
      - Parcela fixa: R$500/mês (a partir de jun/2026)
      - Extra semestral: R$4.000 em Agosto (recebe PLR) e em Fevereiro (recebe 13°-PLR)
3. Transferências internas, aplicações e estornos são ignorados.
4. Limites por categoria configuráveis — alerta quando ultrapassado.
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json, os, re
from datetime import datetime, timedelta, date
from collections import defaultdict

# ──────────────────────────────────────────────
# CONFIGURAÇÕES GERAIS
# ──────────────────────────────────────────────
SHEET_ID = "1BGYyMz9BZ0ypEaJfv5InDWwVZ73iK58p9W-QOsBY3Gk"
RENDA_LIQUIDA_REAL = 3500   # Renda líquida mensal base (sem PLR)

# Limites mensais por categoria (R$) — edite aqui conforme preferir
LIMITES_CATEGORIA = {
    "Alimentação":  700,
    "Transporte":   500,
    "Saúde":        400,
    "Lazer":        300,
    "Educação":     400,
    "Pet":          200,
    "Compras":      300,
    "Serviços":     200,
    "Casa":         1200,
    "Outros":       300,
}

# Meses em que recebe PLR/13° (mês numérico)
MESES_PLR = [2, 8]   # Fevereiro e Agosto

# ──────────────────────────────────────────────
# PALAVRAS-CHAVE QUE INDICAM PAGAMENTO DE FATURA
# (não devem ser contabilizadas como gasto)
# ──────────────────────────────────────────────
PALAVRAS_FATURA = [
    "PAGAMENTO FATURA",
    "PGTO FATURA",
    "PGT FATURA",
    "FATURA CARTAO",
    "FATURA PAGA",
    "PAGTO CARTAO",
    "PAGAMENTO CARTAO",
    "PAG CARTAO",
    "PAGAMENTO CLICK",
    "PAGAMENTO LATAM",
    "LATAM PASS FATURA",
    "CLICK FATURA",
    "NUBANK FATURA",
    "FAT CARTAO",
]

# Outras linhas a ignorar (transferências internas, etc.)
PALAVRAS_IGNORAR = [
    "APLICACAO",
    "RESGATE",
    "TRANSFERENCIA ENTRE CONTAS",
    "TED PROPRIA",
    "PIX PROPRIA",
    "ESTORNO",
    "SALDO DO DIA",
    "PAGAMENTO PARCELA EMPRESTIMO",  # o empréstimo Cirlene é tratado separadamente
]

# ──────────────────────────────────────────────
# 1. REGRAS DE CATEGORIZAÇÃO
# ──────────────────────────────────────────────
def load_categoria_rules(sheet):
    try:
        ws = sheet.worksheet("categorias_padrao")
        records = ws.get_all_records()
        rules = []
        for row in records:
            if row.get("palavra_chave") and row.get("categoria"):
                rules.append({
                    "palavra":      row["palavra_chave"].strip().upper(),
                    "categoria":    row["categoria"].strip(),
                    "subcategoria": row.get("subcategoria", ""),
                    "tipo":         row.get("tipo", "Despesa"),
                })
        print(f"📌 {len(rules)} regras de categorização carregadas")
        return rules
    except Exception as e:
        print(f"⚠️  Sem aba categorias_padrao: {e}")
        return []

def categorizar(descricao, rules):
    desc = descricao.upper()
    for r in rules:
        if r["palavra"] in desc:
            return r["categoria"], r["tipo"]
    # Fallback simples
    fallbacks = [
        (["SUPERMERCADO","MERCADO","HORTIFRUTI","PADARIA","ACOUGUE","PEIXARIA"], "Alimentação"),
        (["RESTAURANTE","LANCHE","IFOOD","RAPPI","UBER EATS","DELIVERY"], "Alimentação"),
        (["POSTO","GASOLINA","COMBUSTIVEL","ESTACIONAMENTO","UBER","99","ONIBUS","METRO","PEDAGIO"], "Transporte"),
        (["FARMACIA","DROGARIA","HOSPITAL","CLINICA","MEDICO","PLANO DE SAUDE","ODONTO","LABORATORIO"], "Saúde"),
        (["CINEMA","TEATRO","NETFLIX","SPOTIFY","AMAZON PRIME","DISNEY","SHOW","INGRESSO"], "Lazer"),
        (["ESCOLA","FACULDADE","CURSO","LIVRO","PAPELARIA","MATERIAL ESCOLAR"], "Educação"),
        (["PET","VETERINARIO","RACAO","ANIMAL"], "Pet"),
        (["ALUGUEL","CONDOMINIO","LUZ","ENERGIA","GAS","AGUA","INTERNET","TELEFONE","SEGURO"], "Casa"),
        (["LOJA","SHOPEE","AMAZON","AMERICANAS","MAGAZINE","RENNER","HERING","ZARA"], "Compras"),
    ]
    for palavras, cat in fallbacks:
        if any(p in desc for p in palavras):
            return cat, "Despesa"
    return "Outros", "Despesa"

def deve_ignorar(descricao):
    """Retorna True se a linha não deve ser contabilizada."""
    desc = descricao.strip().upper()
    for p in PALAVRAS_FATURA + PALAVRAS_IGNORAR:
        if p in desc:
            return True
    return False

# ──────────────────────────────────────────────
# 2. MOVIMENTAÇÕES REAIS
# ──────────────────────────────────────────────
def load_movimentacoes(sheet, rules):
    try:
        ws = sheet.worksheet("movimentacoes")
        records = ws.get_all_records()

        gastos   = []
        receitas = []

        for row in records:
            desc = str(row.get("descricao", "")).strip()
            if not desc:
                continue

            # Ignorar linhas de fatura e transferências internas
            if deve_ignorar(desc):
                print(f"   ⏭️  Ignorado: {desc[:50]}")
                continue

            valor_str = str(row.get("valor", "0")).replace(",", ".").replace("R$", "").strip()
            try:
                valor = float(valor_str)
            except ValueError:
                continue

            if valor == 0:
                continue

            data_str  = str(row.get("data", "")).strip()
            cat_orig  = str(row.get("categoria", "")).strip()

            categoria, tipo = categorizar(desc, rules)
            # Se já veio categorizado na planilha, respeitar
            if cat_orig and cat_orig.lower() not in ["outros", ""]:
                categoria = cat_orig

            # Receita: valores positivos até R$20k (evitar outliers)
            if valor > 0 and valor < 20000:
                receitas.append({
                    "data":       data_str,
                    "descricao":  desc[:50],
                    "valor":      round(valor, 2),
                    "categoria":  categoria,
                })
            # Despesa: valores negativos até -R$5k por transação
            elif valor < 0 and abs(valor) < 5000:
                gastos.append({
                    "data":       data_str,
                    "descricao":  desc[:50],
                    "valor":      round(abs(valor), 2),
                    "categoria":  categoria,
                })

        print(f"📊 Movimentações: {len(gastos)} gastos, {len(receitas)} receitas")
        return gastos, receitas

    except Exception as e:
        print(f"❌ Erro em movimentacoes: {e}")
        return [], []

# ──────────────────────────────────────────────
# 3. EMPRÉSTIMO CIRLENE + CÁLCULO PLR
# ──────────────────────────────────────────────
def load_amortizacao(sheet):
    """
    Lê a aba financiamento_emprestimo.
    Lógica de PLR:
      - Parcela base: R$500/mês a partir de Jun/2026
      - Extra de R$4.000 nos meses de PLR (Agosto e Fevereiro)
        → Agosto porque o semestre que fecha em Jun paga em Ago
        → Fevereiro porque o semestre que fecha em Dez paga em Fev
    O CSV já tem esse calendário calculado; aqui apenas lemos e
    calculamos o saldo atual marcando como pagas as parcelas com
    data_vencimento <= hoje.
    """
    try:
        ws = sheet.worksheet("financiamento_emprestimo")
        records = ws.get_all_records()

        hoje = datetime.now()
        amortizacao = []
        saldo_atual = 35000.0
        parcelas_pagas = 0

        for row in records:
            data_str    = str(row.get("data_vencimento", "")).strip()
            parcela_num = int(row.get("parcela_numero", 0))
            val_mensal  = float(str(row.get("valor_mensal", 0)).replace(",", ".") or 0)
            val_semest  = float(str(row.get("valor_semestral_extra", 0)).replace(",", ".") or 0)
            val_total   = float(str(row.get("valor_total_parcela", 0)).replace(",", ".") or 0)
            saldo_apos  = float(str(row.get("saldo_devedor_apos", 0)).replace(",", ".") or 0)
            status_orig = str(row.get("status", "Pendente")).strip()

            # Determinar se já foi paga com base na data
            status = status_orig
            try:
                dt = datetime.strptime(data_str, "%Y-%m-%d")
                if dt.date() <= hoje.date() and status_orig == "Pendente":
                    status = "Paga"
                    saldo_atual = saldo_apos
                    parcelas_pagas += 1
            except ValueError:
                pass

            amortizacao.append({
                "data":          data_str,
                "parcela":       parcela_num,
                "valor_mensal":  abs(val_mensal),
                "valor_extra":   abs(val_semest),
                "valor_total":   abs(val_total),
                "saldo_apos":    saldo_apos,
                "status":        status,
                "mes_plr":       abs(val_semest) > 0,  # True = mês com PLR extra
            })

        total_parcelas = len(amortizacao)
        print(f"💸 Dívida Cirlene: saldo atual R$ {saldo_atual:,.2f} | {parcelas_pagas}/{total_parcelas} pagas")
        return amortizacao, saldo_atual, parcelas_pagas, total_parcelas

    except Exception as e:
        print(f"⚠️  Erro em financiamento_emprestimo: {e}")
        return [], 35000.0, 0, 30

# ──────────────────────────────────────────────
# 4. RECEITAS FIXAS
# ──────────────────────────────────────────────
def load_receitas_fixas(sheet):
    try:
        ws = sheet.worksheet("receitas_fixas")
        records = ws.get_all_records()
        return [
            {
                "descricao":    str(r.get("descricao", "")),
                "valor":        float(str(r.get("valor_esperado", 0)).replace(",", ".") or 0),
                "dia_previsto": int(r.get("dia_previsto", 15)),
            }
            for r in records
            if str(r.get("ativo", "True")).lower() in ["true", "1", "sim", "s"]
        ]
    except Exception as e:
        print(f"⚠️  Sem aba receitas_fixas: {e}")
        return []

# ──────────────────────────────────────────────
# 5. DESPESAS RECORRENTES
# ──────────────────────────────────────────────
def load_despesas_recorrentes(sheet):
    try:
        ws = sheet.worksheet("despesas_recorrentes")
        records = ws.get_all_records()
        return [
            {
                "descricao":       str(r.get("descricao", "")),
                "categoria":       str(r.get("categoria", "Outros")),
                "valor":           abs(float(str(r.get("valor_mensal", 0)).replace(",", ".") or 0)),
                "dia_vencimento":  int(r.get("dia_vencimento", 0)),
            }
            for r in records
            if str(r.get("ativo", "True")).lower() in ["true", "1", "sim", "s"]
        ]
    except Exception as e:
        print(f"⚠️  Sem aba despesas_recorrentes: {e}")
        return []

# ──────────────────────────────────────────────
# 6. PROJEÇÃO MENSAL
# ──────────────────────────────────────────────
def load_projecao_mensal(sheet):
    try:
        ws = sheet.worksheet("projecao_mensal")
        records = ws.get_all_records()
        result = []
        for r in records:
            mes = str(r.get("mes", "")).strip()
            if not mes:
                continue
            result.append({
                "mes":                   mes,
                "salario_previsto":      abs(float(str(r.get("salario_previsto", 0)).replace(",", ".") or 0)),
                "despesas_recorrentes":  abs(float(str(r.get("despesas_recorrentes", 0)).replace(",", ".") or 0)),
                "parcela_emprestimo":    abs(float(str(r.get("parcela_emprestimo", 0)).replace(",", ".") or 0)),
                "parcela_semestral":     abs(float(str(r.get("parcela_semestral", 0)).replace(",", ".") or 0)),
            })
        return result
    except Exception as e:
        print(f"⚠️  Sem aba projecao_mensal: {e}")
        return []

# ──────────────────────────────────────────────
# 7. CUSTOS ESSENCIAIS (Ana Lua + Mandelinha)
# ──────────────────────────────────────────────
def load_custos_essenciais(sheet):
    """
    Tenta ler uma aba 'custos_essenciais'.
    Se não existir, usa os valores-padrão hardcoded.
    """
    try:
        ws = sheet.worksheet("custos_essenciais")
        records = ws.get_all_records()
        ana_lua    = []
        mandelinha = []
        for r in records:
            item = {"nome": str(r.get("nome", "")), "valor": float(str(r.get("valor", 0)).replace(",", ".") or 0)}
            if str(r.get("pessoa", "")).lower() in ["ana lua", "ana_lua", "analua"]:
                ana_lua.append(item)
            else:
                mandelinha.append(item)
        return {"ana_lua": ana_lua, "mandelinha": mandelinha}
    except Exception:
        return {
            "ana_lua": [
                {"nome": "Leite Nan",          "valor": 280},
                {"nome": "Pomada",              "valor": 40},
                {"nome": "Lenço umedecido",     "valor": 60},
                {"nome": "Farmácia",            "valor": 150},
                {"nome": "Comida (papinha)",    "valor": 50},
            ],
            "mandelinha": [
                {"nome": "Fralda pet",   "valor": 120},
                {"nome": "Plano Pet Love","valor": 59},
            ],
        }

# ──────────────────────────────────────────────
# 8. PROCESSAMENTO PRINCIPAL
# ──────────────────────────────────────────────
def process_sheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        print("❌ ERRO: variável GOOGLE_CREDENTIALS não encontrada.")
        return

    creds_dict = json.loads(creds_json)
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet  = client.open_by_key(SHEET_ID)
    print(f"📂 Planilha aberta: {sheet.title}")

    # ── Carregar dados ──────────────────────────────────
    rules                          = load_categoria_rules(sheet)
    gastos, receitas               = load_movimentacoes(sheet, rules)
    amortizacao, saldo_devedor, \
        parcelas_pagas, total_parc = load_amortizacao(sheet)
    receitas_fixas                 = load_receitas_fixas(sheet)
    despesas_recorrentes           = load_despesas_recorrentes(sheet)
    projecao_mensal                = load_projecao_mensal(sheet)
    custos_essenciais              = load_custos_essenciais(sheet)

    # ── Totais gerais ────────────────────────────────────
    total_receitas = sum(r["valor"] for r in receitas) + sum(r["valor"] for r in receitas_fixas)
    total_gastos   = sum(g["valor"] for g in gastos)   + sum(d["valor"] for d in despesas_recorrentes)
    saldo_total    = total_receitas - total_gastos

    # ── Gastos por categoria ─────────────────────────────
    cat_dict = defaultdict(float)
    for g in gastos:
        cat_dict[g["categoria"]] += g["valor"]
    for d in despesas_recorrentes:
        cat_dict[d["categoria"]] += d["valor"]

    gastos_por_categoria = {
        k: round(v, 2)
        for k, v in sorted(cat_dict.items(), key=lambda x: x[1], reverse=True)
    }

    # ── Alertas de limite ────────────────────────────────
    alertas = []
    for cat, limite in LIMITES_CATEGORIA.items():
        gasto_cat = gastos_por_categoria.get(cat, 0)
        pct = (gasto_cat / limite * 100) if limite > 0 else 0
        status = "ok"
        if pct >= 100:
            status = "over"
            alertas.append(f"🚨 {cat}: R${gasto_cat:.0f} / limite R${limite} ({pct:.0f}%)")
        elif pct >= 80:
            status = "warn"
            alertas.append(f"⚠️  {cat}: {pct:.0f}% do limite (R${limite - gasto_cat:.0f} restam)")

    # ── Evolução mensal (últimos 6 meses) ────────────────
    gastos_mensais   = defaultdict(float)
    receitas_mensais = defaultdict(float)
    for g in gastos:
        mes = g["data"][:7] if len(g.get("data", "")) >= 7 else "0000-00"
        gastos_mensais[mes] += g["valor"]
    for r in receitas:
        mes = r["data"][:7] if len(r.get("data", "")) >= 7 else "0000-00"
        receitas_mensais[mes] += r["valor"]

    meses_ordenados = sorted(set(list(gastos_mensais) + list(receitas_mensais)))[-6:]
    gastos_mensais_out   = {m: round(gastos_mensais[m], 2)   for m in meses_ordenados}
    receitas_mensais_out = {m: round(receitas_mensais[m], 2) for m in meses_ordenados}

    # Variação mês atual vs anterior
    variacao_gasto = 0.0
    if len(meses_ordenados) >= 2:
        m_atual    = gastos_mensais.get(meses_ordenados[-1], 0)
        m_anterior = gastos_mensais.get(meses_ordenados[-2], 0)
        if m_anterior > 0:
            variacao_gasto = round(((m_atual - m_anterior) / m_anterior) * 100, 1)

    # ── Ranking por categoria (mês atual) ───────────────
    mes_atual_key = datetime.now().strftime("%Y-%m")
    ranking_mes   = defaultdict(float)
    for g in gastos:
        if g.get("data", "").startswith(mes_atual_key):
            ranking_mes[g["categoria"]] += g["valor"]
    ranking_categoria = [
        {"categoria": k, "valor": round(v, 2)}
        for k, v in sorted(ranking_mes.items(), key=lambda x: x[1], reverse=True)
    ]

    # ── Média diária ─────────────────────────────────────
    trinta_atras     = datetime.now() - timedelta(days=30)
    gastos_30        = sum(
        g["valor"] for g in gastos
        if _parse_date(g.get("data", "")) and _parse_date(g["data"]) >= trinta_atras
    )
    media_diaria     = round(gastos_30 / 30, 2) if gastos_30 > 0 else 0

    # ── Taxa de esforço e saúde financeira ───────────────
    taxa_esforco   = round((total_gastos / total_receitas * 100), 1) if total_receitas > 0 else 0
    cap_poupanca   = round(((total_receitas - total_gastos) / total_receitas * 100), 1) if total_receitas > 0 else 0
    dias_reserva   = round(saldo_total / media_diaria, 1) if media_diaria > 0 else 0

    # Score de saúde (0–100)
    score = 0
    if cap_poupanca >= 20: score += 30
    elif cap_poupanca >= 10: score += 15
    over_limite = sum(1 for c, l in LIMITES_CATEGORIA.items() if gastos_por_categoria.get(c, 0) > l)
    if over_limite == 0: score += 20
    elif over_limite == 1: score += 10
    parcela_mensal_total = 500  # empréstimo Cirlene
    if total_receitas > 0 and (parcela_mensal_total / total_receitas) < 0.30: score += 25
    elif total_receitas > 0 and (parcela_mensal_total / total_receitas) < 0.50: score += 10
    if dias_reserva >= 180: score += 25
    elif dias_reserva >= 90: score += 15
    elif dias_reserva >= 30: score += 5

    # ── Próximas parcelas (com alerta PLR) ───────────────
    proximas = [p for p in amortizacao if p["status"] == "Pendente"][:10]

    # ── Montar JSON final ────────────────────────────────
    result = {
        "lastUpdate":            datetime.now().isoformat(),
        "rendaLiquida":          RENDA_LIQUIDA_REAL,
        "totalReceitas":         round(total_receitas, 2),
        "totalGastos":           round(total_gastos, 2),
        "saldoTotal":            round(saldo_total, 2),
        "mediaDiaria":           media_diaria,
        "taxaEsforco":           taxa_esforco,
        "capPoupanca":           cap_poupanca,
        "diasReserva":           max(0, dias_reserva),
        "scoreFinanceiro":       score,
        "variacaoGastoMes":      variacao_gasto,

        # Evolução mensal
        "gastosMensais":         gastos_mensais_out,
        "receitasMensais":       receitas_mensais_out,

        # Categorias
        "gastosPorCategoria":    gastos_por_categoria,
        "limitesSugeridos":      LIMITES_CATEGORIA,
        "rankingCategoria":      ranking_categoria,
        "alertas":               alertas,

        # Empréstimo
        "debt": {
            "valor_total":       35000,
            "saldo_devedor":     round(saldo_devedor, 2),
            "parcelas_pagas":    parcelas_pagas,
            "total_parcelas":    total_parc,
            "parcela_mensal":    500,
            "extra_semestral":   4000,
            "meses_plr":         MESES_PLR,
            "amortizacao":       amortizacao,
            "proximas_parcelas": proximas,
        },

        # Extrato (últimas 150 transações, ordenado por data desc)
        "extrato": sorted(gastos, key=lambda x: x.get("data", ""), reverse=True)[:150],

        # Fixos e planejamento
        "receitasFixas":         receitas_fixas,
        "despesasRecorrentes":   despesas_recorrentes,
        "projecaoMensal":        projecao_mensal[:12],
        "custosEssenciais":      custos_essenciais,

        # Stats
        "stats": {
            "total_gastos":       len(gastos),
            "total_receitas":     len(receitas),
            "total_transacoes":   len(gastos) + len(receitas),
        },
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n✅ data.json gerado com sucesso!")
    print(f"   💰 Receitas:      R$ {total_receitas:>10,.2f}")
    print(f"   💸 Gastos:        R$ {total_gastos:>10,.2f}")
    print(f"   ⚖️  Saldo:         R$ {saldo_total:>10,.2f}")
    print(f"   📊 Taxa esforço:  {taxa_esforco}%")
    print(f"   🏦 Dívida Cirlene: R$ {saldo_devedor:,.2f}")
    print(f"   ❤️  Score:          {score}/100")
    if alertas:
        print("\n   🚨 ALERTAS DE LIMITE:")
        for a in alertas:
            print(f"      {a}")


def _parse_date(s):
    """Tenta converter string de data para datetime. Retorna None se falhar."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            pass
    return None


if __name__ == "__main__":
    process_sheet()
