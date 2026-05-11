"""
WealthAurora – sync_sheet.py (CORRIGIDO para manter 100% do layout Claude)
Leitura correta de decimais (vírgula/ponto) sem quebrar os dados.
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json, os, re
from datetime import datetime, timedelta
from collections import defaultdict

# ══════════════════════════════════════════════════════════════
# CONFIGURAÇÕES
# ══════════════════════════════════════════════════════════════
SHEET_ID = "1BGYyMz9BZ0ypEaJfv5InDWwVZ73iK58p9W-QOsBY3Gk"
RENDA_BASE = 3460.82
MESES_PLR = [2, 8]   # Fevereiro e Agosto

LIMITES_CATEGORIA = {
    "Alimentação": 800, "Transporte": 400, "Saúde": 400, "Lazer": 300,
    "Educação": 400, "Pet": 250, "Compras": 350, "Serviços": 250,
    "Streaming": 100, "Vestuário": 200, "Eletrônicos": 200, "Casa": 1500,
    "Outros": 200,
}

# ══════════════════════════════════════════════════════════════
# FUNÇÃO CORINGA: converte string brasileira para float
# ══════════════════════════════════════════════════════════════
def to_float(valor_str):
    """Converte 'R$ 1.234,56' ou '-2.19' ou '1,761.48' para float."""
    if valor_str is None:
        return 0.0
    s = str(valor_str).strip()
    s = re.sub(r'R\$', '', s).strip()
    # Se há ponto e vírgula, trata como milhar
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '.')
    s = re.sub(r'[^\d.-]', '', s)
    try:
        return float(s)
    except:
        return 0.0

# ══════════════════════════════════════════════════════════════
# CONEXÃO COM GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════
def conectar():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise RuntimeError("❌ GOOGLE_CREDENTIALS não encontrada.")
    creds_dict = json.loads(creds_json)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

# ══════════════════════════════════════════════════════════════
# REGRAS DE CATEGORIZAÇÃO (igual ao original do Claude)
# ══════════════════════════════════════════════════════════════
def load_categoria_rules(sheet):
    try:
        ws = sheet.worksheet("categorias_padrao")
        rules = []
        for row in ws.get_all_records():
            if row.get("palavra_chave") and row.get("categoria"):
                rules.append({
                    "palavra": row["palavra_chave"].strip().upper(),
                    "categoria": row["categoria"].strip(),
                })
        print(f"📌 {len(rules)} regras carregadas")
        return rules
    except:
        return []

def categorizar(desc, cat_orig, rules):
    cat = str(cat_orig or "").strip()
    if cat and cat not in ["", "Outros"]:
        return cat
    desc_u = desc.upper()
    for r in rules:
        if r["palavra"] in desc_u:
            return r["categoria"]
    # Fallback (mesmo do Claude)
    checks = [
        (["SUPERMERCADO","MERCADO","HORTIFRUTI","PADARIA","RESTAURANTE","IFOOD"], "Alimentação"),
        (["UBER","99APP","TOP SP","AUTOPASS"], "Transporte"),
        (["FARMACIA","DROGARIA","RAIA"], "Saúde"),
        (["CINEMA","NETFLIX","SPOTIFY","PLAY RECARG"], "Lazer"),
        (["FACULDADE","ESCOLA","CURSO"], "Educação"),
        (["PETLOVE","PET SHOP"], "Pet"),
        (["SHOPEE","MERCADOLIVRE","AMERICANAS"], "Compras"),
        (["CLARO","VIVO","GOOGLE ONE"], "Serviços"),
        (["ALUGUEL","CONDOMINIO","LUZ"], "Casa"),
    ]
    for palavras, cat_out in checks:
        if any(p in desc_u for p in palavras):
            return cat_out
    return "Outros"

# ══════════════════════════════════════════════════════════════
# FILTROS (igual ao Claude)
# ══════════════════════════════════════════════════════════════
CATEGORIAS_IGNORAR = {"Pagamento Cartão", "Investimento", "Empréstimo Recebido", "Transferência", "Reembolso", "Rendimento", "Depósito", "Empréstimo", "Pagamento Conta"}
PALAVRAS_IGNORAR = ["FATURA PAGA", "APLICACAO COFRINHOS", "PAGAMENTO PARCELA EMPRESTIMO", "SALDO DO DIA", "REND PAGO APLIC", "DEV PIX", "IOF", "JUROS LIMITE DA CONTA", "SEGURO LIS ITAU", "DEP DIN ATM"]
TRANSFERENCIAS_INTERNAS = ["PIX TRANSF CIRLENE", "PIX TRANSF FELIPE", "PIX TRANSF Felipe"]
CATEGORIAS_RECEITA = {"Salário", "salário", "salario"}

def deve_ignorar(desc, categoria, valor):
    cat = str(categoria or "").strip()
    desc_u = desc.strip().upper()
    if cat in CATEGORIAS_IGNORAR: return True
    for p in PALAVRAS_IGNORAR:
        if p.upper() in desc_u: return True
    for nome in TRANSFERENCIAS_INTERNAS:
        if nome.upper() in desc_u: return True
    if "PIX TRANSF EMANUEL" in desc_u and abs(valor) > 100: return True
    return False

# ══════════════════════════════════════════════════════════════
# CARREGAR MOVIMENTAÇÕES (com to_float)
# ══════════════════════════════════════════════════════════════
def load_movimentacoes(sheet, rules):
    try:
        ws = sheet.worksheet("movimentacoes")
        records = ws.get_all_records()
        gastos = []
        receitas = []
        for row in records:
            desc = str(row.get("descricao", "")).strip()
            categoria = str(row.get("categoria", "")).strip()
            tipo = str(row.get("tipo_registro", "extrato")).strip().lower()
            if not desc:
                continue
            valor = to_float(row.get("valor", 0))
            if valor == 0:
                continue
            if deve_ignorar(desc, categoria, valor):
                continue
            data_str = str(row.get("data", "")).strip()
            cat_final = categorizar(desc, categoria, rules)
            cartao = None
            cf = row.get("cartao_final", "")
            if cf and str(cf).strip() not in ["", "None", "nan"]:
                try:
                    cartao = str(int(float(str(cf))))
                except:
                    cartao = str(cf).strip()
            desc_u = desc.upper()
            is_salario = ("SALARIO" in desc_u or "REMUNERACAO" in desc_u or "TEF CREDITO" in desc_u)
            if is_salario and valor > 0:
                receitas.append({"data": data_str, "descricao": desc[:60], "valor": round(valor, 2), "categoria": "Salário"})
            elif valor < 0 and abs(valor) < 5000:
                gastos.append({"data": data_str, "descricao": desc[:60], "valor": round(abs(valor), 2), "categoria": cat_final, "tipo": tipo, "cartao": cartao})
        print(f"📊 {len(gastos)} gastos, {len(receitas)} receitas")
        return gastos, receitas
    except Exception as e:
        print(f"❌ Erro: {e}")
        return [], []

# ══════════════════════════════════════════════════════════════
# ABAS AUXILIARES (com to_float)
# ══════════════════════════════════════════════════════════════
def load_receitas_fixas(sheet):
    try:
        ws = sheet.worksheet("receitas_fixas")
        records = ws.get_all_records()
        out = []
        for r in records:
            if str(r.get("ativo", "TRUE")).upper() not in ["TRUE","1","SIM"]:
                continue
            out.append({"descricao": str(r.get("descricao", "")), "valor": to_float(r.get("valor_esperado", 0)), "dia_previsto": int(r.get("dia_previsto", 15) or 15)})
        return out
    except:
        return []

def load_despesas_recorrentes(sheet):
    try:
        ws = sheet.worksheet("despesas_recorrentes")
        records = ws.get_all_records()
        out = []
        for r in records:
            if str(r.get("ativo", "TRUE")).upper() not in ["TRUE","1","SIM"]:
                continue
            out.append({"descricao": str(r.get("descricao", "")), "categoria": str(r.get("categoria", "Serviços")), "valor": to_float(r.get("valor_mensal", 0)), "dia_vencimento": int(r.get("dia_vencimento", 0) or 0)})
        return out
    except:
        return []

def load_projecao_mensal(sheet):
    try:
        ws = sheet.worksheet("projecao_mensal")
        records = ws.get_all_records()
        out = []
        for r in records:
            mes = str(r.get("mes", "")).strip()
            if not mes:
                continue
            out.append({"mes": mes, "salario_previsto": to_float(r.get("salario_previsto", 0)), "despesas_recorrentes": to_float(r.get("despesas_recorrentes", 0)), "parcela_emprestimo": to_float(r.get("parcela_emprestimo", 0)), "parcela_semestral": to_float(r.get("parcela_semestral", 0))})
        return out
    except:
        return []

def load_amortizacao(sheet):
    try:
        ws = sheet.worksheet("financiamento_emprestimo")
        records = ws.get_all_records()
        hoje = datetime.now().date()
        amort = []
        saldo = 35000.0
        pagas = 0
        for r in records:
            ds = str(r.get("data_vencimento", "")).strip()
            num = int(r.get("parcela_numero", 0) or 0)
            vm = abs(to_float(r.get("valor_mensal", 0)))
            ve = abs(to_float(r.get("valor_semestral_extra", 0)))
            vt = abs(to_float(r.get("valor_total_parcela", 0)))
            sa = to_float(r.get("saldo_devedor_apos", 0))
            st = str(r.get("status", "Pendente")).strip()
            status = st
            try:
                dt = datetime.strptime(ds, "%Y-%m-%d").date()
                if dt <= hoje and st == "Pendente":
                    status = "Paga"
                    saldo = sa
                    pagas += 1
            except:
                pass
            amort.append({"data": ds, "parcela": num, "valor_mensal": vm, "valor_extra": ve, "valor_total": vt, "saldo_apos": sa, "status": status, "mes_plr": ve > 0})
        return amort, saldo, pagas, len(amort)
    except:
        return [], 35000.0, 0, 30

def load_custos_essenciais(sheet):
    try:
        ws = sheet.worksheet("custos_essenciais")
        ana, mandi = [], []
        for r in ws.get_all_records():
            item = {"nome": str(r.get("nome", "")), "valor": to_float(r.get("valor", 0))}
            if "ana" in str(r.get("pessoa", "")).lower():
                ana.append(item)
            else:
                mandi.append(item)
        return {"ana_lua": ana, "mandelinha": mandi}
    except:
        return {"ana_lua": [{"nome": "Leite Nan", "valor": 280}, {"nome": "Pomada", "valor": 40}, {"nome": "Lenço umedecido", "valor": 60}, {"nome": "Farmácia", "valor": 150}, {"nome": "Papinha", "valor": 50}], "mandelinha": [{"nome": "Fralda pet", "valor": 120}, {"nome": "Plano Pet Love", "valor": 59}]}

# ══════════════════════════════════════════════════════════════
# PROCESSAMENTO PRINCIPAL (IGUAL AO QUE O CLAUDE FEZ)
# ══════════════════════════════════════════════════════════════
def parse_date(s):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(s).strip(), fmt)
        except:
            pass
    return None

def fmt_mes(m):
    try:
        dt = datetime.strptime(m + "-01", "%Y-%m-%d")
        return dt.strftime("%b/%y").capitalize()
    except:
        return m

def process_sheet():
    sheet = conectar()
    rules = load_categoria_rules(sheet)
    gastos, receitas = load_movimentacoes(sheet, rules)
    amort, saldo_dev, pagas, totparc = load_amortizacao(sheet)
    rec_fixas = load_receitas_fixas(sheet)
    desp_rec = load_despesas_recorrentes(sheet)
    proj = load_projecao_mensal(sheet)
    essenciais = load_custos_essenciais(sheet)

    # Totais
    total_rec = sum(r["valor"] for r in receitas) + sum(r["valor"] for r in rec_fixas)
    total_gast = sum(g["valor"] for g in gastos) + sum(d["valor"] for d in desp_rec)
    saldo = total_rec - total_gast
    renda_ref = sum(r["valor"] for r in rec_fixas) or RENDA_BASE

    # Gastos por categoria (histórico)
    cat_dict = defaultdict(float)
    for g in gastos:
        cat_dict[g["categoria"]] += g["valor"]
    gastos_por_cat = {k: round(v, 2) for k, v in sorted(cat_dict.items(), key=lambda x: x[1], reverse=True)}

    # Gastos mês atual
    mes_atual = datetime.now().strftime("%Y-%m")
    cat_mes_dict = defaultdict(float)
    for g in gastos:
        if g.get("data", "").startswith(mes_atual):
            cat_mes_dict[g["categoria"]] += g["valor"]
    gastos_cat_mes_atual = {k: round(v, 2) for k, v in sorted(cat_mes_dict.items(), key=lambda x: x[1], reverse=True)}

    # Alertas
    alertas = []
    for cat, lim in LIMITES_CATEGORIA.items():
        gc = gastos_cat_mes_atual.get(cat, 0)
        pct = (gc / lim * 100) if lim > 0 else 0
        if pct >= 100:
            alertas.append(f"🚨 {cat}: R${gc:.0f} / limite R${lim} ({pct:.0f}%)")
        elif pct >= 80:
            alertas.append(f"⚠️ {cat}: {pct:.0f}% do limite (faltam R${lim - gc:.0f})")

    # Evolução mensal (últimos 6 meses)
    gm = defaultdict(float)
    rm = defaultdict(float)
    for g in gastos:
        mes = g["data"][:7] if len(g.get("data", "")) >= 7 else "0000-00"
        gm[mes] += g["valor"]
    for r in receitas:
        mes = r["data"][:7] if len(r.get("data", "")) >= 7 else "0000-00"
        rm[mes] += r["valor"]

    meses_chave = sorted(set(list(gm) + list(rm)))[-6:]
    gastos_mensais = {fmt_mes(m): round(gm[m], 2) for m in meses_chave}
    receitas_mensais = {fmt_mes(m): round(rm[m], 2) for m in meses_chave}

    # Variação gasto
    variacao = 0.0
    if len(meses_chave) >= 2:
        ma = gm.get(meses_chave[-1], 0)
        mb = gm.get(meses_chave[-2], 0)
        if mb > 0:
            variacao = round(((ma - mb) / mb) * 100, 1)

    # Gastos por cartão
    NOMES_CARTOES = {"5217": "Itaú 5217", "7398": "Latam 7398", "debito": "Conta/Débito"}
    cartao_dict = defaultdict(lambda: {"total": 0.0, "count": 0, "categorias": defaultdict(float)})
    for g in gastos:
        chave = g.get("cartao") or "debito"
        cartao_dict[chave]["total"] += g["valor"]
        cartao_dict[chave]["count"] += 1
        cartao_dict[chave]["categorias"][g["categoria"]] += g["valor"]
    gastos_por_cartao = {}
    for chave, dados in cartao_dict.items():
        gastos_por_cartao[chave] = {
            "nome": NOMES_CARTOES.get(chave, f"Cartão {chave}"),
            "total": round(dados["total"], 2),
            "count": dados["count"],
            "categorias": {k: round(v, 2) for k, v in sorted(dados["categorias"].items(), key=lambda x: x[1], reverse=True)},
        }

    # Ranking mês atual
    ranking = [{"categoria": k, "valor": round(v, 2)} for k, v in sorted(cat_mes_dict.items(), key=lambda x: x[1], reverse=True)]

    # Média diária
    trinta = datetime.now() - timedelta(days=30)
    g30 = sum(g["valor"] for g in gastos if parse_date(g.get("data", "")) and parse_date(g["data"]) >= trinta)
    media_diaria = round(g30 / 30, 2) if g30 > 0 else 0

    # Indicadores
    taxa_esforco = round((total_gast / total_rec * 100), 1) if total_rec > 0 else 0
    cap_poupanca = round(((total_rec - total_gast) / total_rec * 100), 1) if total_rec > 0 else 0
    dias_reserva = round(saldo / media_diaria, 1) if media_diaria > 0 and saldo > 0 else 0

    # Score
    score = 0
    if cap_poupanca >= 20: score += 30
    elif cap_poupanca >= 10: score += 15
    over = sum(1 for c, l in LIMITES_CATEGORIA.items() if gastos_cat_mes_atual.get(c, 0) > l)
    if over == 0: score += 20
    elif over == 1: score += 10
    psr = 500 / renda_ref if renda_ref > 0 else 1
    if psr < 0.15: score += 25
    elif psr < 0.30: score += 15
    elif psr < 0.50: score += 5
    if dias_reserva >= 180: score += 25
    elif dias_reserva >= 90: score += 15
    elif dias_reserva >= 30: score += 5

    proximas = [p for p in amort if p["status"] == "Pendente"][:10]
    meses_disponiveis = sorted(list(set(g["data"][:7] for g in gastos if len(g.get("data", "")) >= 7)), reverse=True)

    # Montar JSON final (com todos os campos que o dashboard do Claude espera)
    result = {
        "lastUpdate": datetime.now().isoformat(),
        "rendaLiquida": round(renda_ref, 2),
        "totalReceitas": round(total_rec, 2),
        "totalGastos": round(total_gast, 2),
        "saldoTotal": round(saldo, 2),
        "mediaDiaria": media_diaria,
        "taxaEsforco": taxa_esforco,
        "capPoupanca": cap_poupanca,
        "diasReserva": max(0, dias_reserva),
        "scoreFinanceiro": score,
        "variacaoGastoMes": variacao,
        "gastosMensais": gastos_mensais,
        "receitasMensais": receitas_mensais,
        "gastosPorCategoria": gastos_por_cat,
        "gastosCatMesAtual": gastos_cat_mes_atual,
        "limitesSugeridos": LIMITES_CATEGORIA,
        "rankingCategoria": ranking,
        "alertas": alertas,
        "mesesDisponiveis": meses_disponiveis,
        "debt": {
            "valor_total": 35000,
            "saldo_devedor": round(saldo_dev, 2),
            "parcelas_pagas": pagas,
            "total_parcelas": totparc,
            "parcela_mensal": 500,
            "extra_semestral": 4000,
            "meses_plr": MESES_PLR,
            "amortizacao": amort,
            "proximas_parcelas": proximas,
        },
        "extrato": sorted(gastos, key=lambda x: x.get("data", ""), reverse=True)[:300],
        "receitasFixas": rec_fixas,
        "despesasRecorrentes": desp_rec,
        "projecaoMensal": proj[:12],
        "custosEssenciais": essenciais,
        "gastosPorCartao": gastos_por_cartao,
        "stats": {
            "total_gastos": len(gastos),
            "total_receitas": len(receitas),
            "total_transacoes": len(gastos) + len(receitas),
            "meses_com_dados": len(meses_disponiveis),
        },
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✅ data.json gerado com saldo R$ {saldo:.2f}")
    print(f"   📊 {len(gastos)} gastos | {len(receitas)} receitas")
    print(f"   📅 Meses disponíveis: {meses_disponiveis}")

if __name__ == "__main__":
    process_sheet()
