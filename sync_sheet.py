"""
WealthAurora – sync_sheet.py (CORRIGIDO)
Lê a planilha Google Sheets e gera o data.json para o dashboard.
Correção: valores decimais agora são lidos corretamente (sem multiplicar por 100).
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json, os, re
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# CONFIGURAÇÕES — edite aqui conforme sua realidade
# ============================================================
SHEET_ID = "1BGYyMz9BZ0ypEaJfv5InDWwVZ73iK58p9W-QOsBY3Gk"
RENDA_BASE = 3460.82  # fallback se receitas_fixas estiver vazio
MESES_PLR = [2, 8]  # Fevereiro e Agosto

# Limites mensais por categoria — AJUSTE A VONTADE
LIMITES_CATEGORIA = {
    "Alimentação": 800,
    "Transporte": 400,
    "Saúde": 400,
    "Lazer": 300,
    "Educação": 400,
    "Pet": 250,
    "Compras": 350,
    "Serviços": 250,
    "Streaming": 100,
    "Vestuário": 200,
    "Eletrônicos": 200,
    "Casa": 1500,
    "Outros": 200,
}

# ============================================================
# REGRAS DE FILTRO (IGNORAR TRANSFERÊNCIAS INTERNAS, ETC.)
# ============================================================
CATEGORIAS_IGNORAR = {
    "Pagamento Cartão", "Pagamento cartão",
    "Investimento",
    "Empréstimo Recebido",
    "Transferência",
    "Reembolso",
    "Rendimento",
    "Depósito",
    "Empréstimo",
    "Pagamento Conta",
}

PALAVRAS_IGNORAR = [
    "FATURA PAGA",
    "PAGAMENTO FATURA",
    "PGTO FATURA",
    "APLICACAO COFRINHOS",
    "PAGAMENTO PARCELA EMPRESTIMO",
    "SALDO DO DIA",
    "REND PAGO APLIC",
    "DEV PIX",
    "IOF",
    "JUROS LIMITE DA CONTA",
    "SEGURO LIS ITAU",
    "DEP DIN ATM",
]

TRANSFERENCIAS_INTERNAS = [
    "PIX TRANSF CIRLENE",
    "PIX TRANSF FELIPE",
    "PIX TRANSF Felipe",
]

CATEGORIAS_RECEITA = {"Salário", "salário", "salario"}

# ============================================================
# 1. FUNÇÃO AUXILIAR: converte string brasileira para float
# ============================================================
def parse_br_number(valor_str):
    """
    Converte string de número no formato brasileiro (R$ 1.234,56) para float.
    Ex: "R$ 1.761,48" -> 1761.48
    """
    if valor_str is None:
        return 0.0

    # Remove 'R$' e espaços extras
    cleaned = str(valor_str).strip().replace("R$", "").strip()
    # Remove pontos de milhar
    cleaned = re.sub(r"\.(?=\d{3})", "", cleaned)  # remove ponto apenas seguido de dígitos
    # Substitui vírgula decimal por ponto
    cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return 0.0


# ============================================================
# 2. CONEXÃO COM O GOOGLE SHEETS
# ============================================================
def conectar():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise RuntimeError("❌ Variável GOOGLE_CREDENTIALS não encontrada.")
    creds_dict = json.loads(creds_json)
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    print(f"📂 Conectado: {sheet.title}")
    return sheet


# ============================================================
# 3. CATEGORIZAÇÃO (igual ao original, sem alterações)
# ============================================================
def load_categoria_rules(sheet):
    try:
        ws = sheet.worksheet("categorias_padrao")
        rules = []
        for row in ws.get_all_records():
            if row.get("palavra_chave") and row.get("categoria"):
                rules.append({
                    "palavra": str(row["palavra_chave"]).strip().upper(),
                    "categoria": str(row["categoria"]).strip(),
                })
        print(f"📌 {len(rules)} regras de categorização carregadas")
        return rules
    except Exception as e:
        print(f"⚠️  Sem aba categorias_padrao: {e}")
        return []


def categorizar(desc, cat_original, rules):
    cat = str(cat_original or "").strip()
    if cat and cat not in ["", "Outros"]:
        return cat

    desc_up = desc.upper()
    for r in rules:
        if r["palavra"] in desc_up:
            return r["categoria"]

    # Fallback (mesmo do seu código original)
    checks = [
        (["SUPERMERCADO", "MERCADO POR", "MERCADO PAG", "HORTIFRUTI", "PADARIA",
          "RESTAURANTE", "LANCHE", "IFOOD", "KEETA", "DELIVERY",
          "CHICO NORDESTINO", "FOOD TO SAV", "PASTEL", "BECO ALFA",
          "PANIFICAD", "SCARLLET", "RODOSNACK", "ESQUINA DO", "ADEGA",
          "BRAHMAN ATA", "SEU JOAO", "OUTBACK", "LANCHONETE",
          "PAULISTA SUPERMERCAD", "JOSE RAIMUNDO", "MP*RAYFOND",
          "99FOOD", "RESTAURANTE", "FOOD "], "Alimentação"),
        (["UBER", "99APP", "99SAO", "99*", "TOP SP TARFA", "AUTOPASS",
          "ONIBUS", "METRO", "PEDAGIO", "GASOLINA", "POSTO",
          "UBER * PENDING", "UBER *TRIP"], "Transporte"),
        (["FARMACIA", "DROGARIA", "HOSPITAL", "CLINICA", "MEDICO",
          "RAIA", "LABORATORIO", "R & R DROGA", "DROGAFARMA"], "Saúde"),
        (["CINEMA", "TEATRO", "NETFLIX", "SPOTIFY", "AMAZON PRIME",
          "DISNEY", "SHOW", "INGRESSO", "PLAY RECARG", "ESPACO GAST"], "Lazer"),
        (["FACULDADE", "ESCOLA", "CURSO", "LIVRO", "PAPELARIA",
          "PAG BOLETO FACULDADES", "BOLETO FACULDADE"], "Educação"),
        (["PETLOVE", "PET SHOP", "VETERINARIO", "RACAO", "DOG B",
          "PG *P_PETLOVE", "PET LOVE"], "Pet"),
        (["SHOPEE", "MERCADOLIVRE", "MERCADO LIVRE", "AMERICANAS",
          "MAGAZINE", "RENNER", "HERING", "ZARA", "KIAMOR", "MIX DEZ",
          "NC SATT", "MIDIA DA S1", "CO BASI", "MP*MELIMAIS",
          "IFD *CO BASI", "AMAZON RETAIL"], "Compras"),
        (["CLARO", "VIVO", "TIM", "OI", "GOOGLE ONE", "EBN*POSTIFY",
          "DL*GOOGLE", "CLARO FLEX", "MPROYALMAQUINAS",
          "SEG CARTAO PROTEGIDO", "LEITURA OSA", "IFOOD CLUB",
          "PG *P_PETLOVE"], "Serviços"),
        (["ALUGUEL", "CONDOMINIO", "ENERGIA", "AGUA",
          "INTERNET", "BOLETO CAIXA"], "Casa"),
        (["SHOPEE *MINGST", "ELETRONICO"], "Eletrônicos"),
        (["KIAMOR", "MIX DEZ OSASCO", "RENNER", "ZARA",
          "HERING", "VESTUARIO"], "Vestuário"),
    ]
    for palavras, cat in checks:
        if any(p in desc_up for p in palavras):
            return cat

    return "Outros"


# ============================================================
# 4. VERIFICAÇÃO: DEVE IGNORAR?
# ============================================================
def deve_ignorar(desc, categoria, valor):
    cat = str(categoria or "").strip()
    desc_u = desc.strip().upper()

    if cat in CATEGORIAS_IGNORAR:
        return True, f"cat={cat}"
    for p in PALAVRAS_IGNORAR:
        if p.upper() in desc_u:
            return True, f"palavra={p}"
    for nome in TRANSFERENCIAS_INTERNAS:
        if nome.upper() in desc_u:
            return True, f"interno={nome}"
    if "PIX TRANSF EMANUEL" in desc_u and abs(valor) > 100:
        return True, "EMANUEL>100=interno"
    return False, ""


# ============================================================
# 5. CARREGAR MOVIMENTAÇÕES (CORRIGIDO!)
# ============================================================
def load_movimentacoes(sheet, rules):
    try:
        ws = sheet.worksheet("movimentacoes")
        records = ws.get_all_records()

        gastos = []
        receitas = []
        ignorados = []

        for row in records:
            desc = str(row.get("descricao", "")).strip()
            categoria = str(row.get("categoria", "")).strip()
            tipo = str(row.get("tipo_registro", "extrato")).strip().lower()

            if not desc:
                continue

            # ✅ CORREÇÃO: parse do valor usando a função
            valor = parse_br_number(row.get("valor", "0"))

            if valor == 0:
                continue

            ignorar, motivo = deve_ignorar(desc, categoria, valor)
            if ignorar:
                ignorados.append(f"  ⏭️  [{motivo}] {desc[:50]} R${valor:.2f}")
                continue

            data_str = str(row.get("data", "")).strip()
            cat_final = categorizar(desc, categoria, rules)

            cf_raw = row.get("cartao_final", "")
            cartao = None
            if cf_raw and str(cf_raw).strip() not in ["", "None", "nan"]:
                try:
                    cartao = str(int(float(str(cf_raw))))
                except (ValueError, TypeError):
                    cartao = str(cf_raw).strip()

            desc_u = desc.upper()
            is_salario = (
                categoria in CATEGORIAS_RECEITA
                or "SALARIO" in desc_u
                or "REMUNERACAO" in desc_u
                or "TEF CREDITO" in desc_u
            )

            if is_salario and valor > 0:
                receitas.append({
                    "data": data_str,
                    "descricao": desc[:60],
                    "valor": round(valor, 2),
                    "categoria": "Salário",
                })
                continue

            if valor < 0 and abs(valor) < 5000:
                gastos.append({
                    "data": data_str,
                    "descricao": desc[:60],
                    "valor": round(abs(valor), 2),
                    "categoria": cat_final,
                    "tipo": tipo,
                    "cartao": cartao,
                })

        print(f"📊 {len(gastos)} gastos | {len(receitas)} receitas | {len(ignorados)} ignorados")
        if ignorados:
            print("   Principais ignorados:")
            for i in ignorados[:10]:
                print(i)
        return gastos, receitas

    except Exception as e:
        print(f"❌ Erro em movimentacoes: {e}")
        import traceback
        traceback.print_exc()
        return [], []


# ============================================================
# 6. EMPRÉSTIMO CIRLENE (sem mudanças)
# ============================================================
def load_amortizacao(sheet):
    try:
        ws = sheet.worksheet("financiamento_emprestimo")
        records = ws.get_all_records()
        hoje = datetime.now().date()
        amort = []
        saldo = 35000.0
        pagas = 0

        for row in records:
            ds = str(row.get("data_vencimento", "")).strip()
            num = int(row.get("parcela_numero", 0) or 0)
            vm = abs(float(str(row.get("valor_mensal", 0) or 0).replace(",", ".")))
            ve = abs(float(str(row.get("valor_semestral_extra", 0) or 0).replace(",", ".")))
            vt = abs(float(str(row.get("valor_total_parcela", 0) or 0).replace(",", ".")))
            sa = float(str(row.get("saldo_devedor_apos", 0) or 0).replace(",", "."))
            st = str(row.get("status", "Pendente")).strip()

            status = st
            try:
                dt = datetime.strptime(ds, "%Y-%m-%d").date()
                if dt <= hoje and st == "Pendente":
                    status = "Paga"
                    saldo = sa
                    pagas += 1
            except ValueError:
                pass

            amort.append({
                "data": ds,
                "parcela": num,
                "valor_mensal": vm,
                "valor_extra": ve,
                "valor_total": vt,
                "saldo_apos": sa,
                "status": status,
                "mes_plr": ve > 0,
            })

        print(f"💸 Cirlene: R${saldo:,.2f} | {pagas}/{len(amort)} pagas")
        return amort, saldo, pagas, len(amort)

    except Exception as e:
        print(f"⚠️  financiamento_emprestimo: {e}")
        return [], 35000.0, 0, 30


# ============================================================
# 7. ABAS AUXILIARES (CORRIGIDAS: parse_br_number)
# ============================================================
def load_receitas_fixas(sheet):
    try:
        ws = sheet.worksheet("receitas_fixas")
        out = []
        for r in ws.get_all_records():
            if str(r.get("ativo", "TRUE")).upper() not in ["TRUE", "1", "SIM", "S", "VERDADEIRO"]:
                continue
            out.append({
                "descricao": str(r.get("descricao", "")),
                "valor": parse_br_number(r.get("valor_esperado", 0)),
                "dia_previsto": int(r.get("dia_previsto", 15) or 15),
            })
        return out
    except Exception as e:
        print(f"⚠️  receitas_fixas: {e}")
        return []


def load_despesas_recorrentes(sheet):
    try:
        ws = sheet.worksheet("despesas_recorrentes")
        out = []
        for r in ws.get_all_records():
            if str(r.get("ativo", "TRUE")).upper() not in ["TRUE", "1", "SIM", "S", "VERDADEIRO"]:
                continue
            out.append({
                "descricao": str(r.get("descricao", "")),
                "categoria": str(r.get("categoria", "Serviços")),
                "valor": parse_br_number(r.get("valor_mensal", 0)),
                "dia_vencimento": int(r.get("dia_vencimento", 0) or 0),
            })
        return out
    except Exception as e:
        print(f"⚠️  despesas_recorrentes: {e}")
        return []


def load_projecao_mensal(sheet):
    try:
        ws = sheet.worksheet("projecao_mensal")
        out = []
        for r in ws.get_all_records():
            mes = str(r.get("mes", "")).strip()
            if not mes:
                continue
            out.append({
                "mes": mes,
                "salario_previsto": parse_br_number(r.get("salario_previsto", 0)),
                "despesas_recorrentes": parse_br_number(r.get("despesas_recorrentes", 0)),
                "parcela_emprestimo": parse_br_number(r.get("parcela_emprestimo", 0)),
                "parcela_semestral": parse_br_number(r.get("parcela_semestral", 0)),
            })
        return out
    except Exception as e:
        print(f"⚠️  projecao_mensal: {e}")
        return []


def load_custos_essenciais(sheet):
    """Tenta ler aba custos_essenciais; se não existir usa valores padrão."""
    try:
        ws = sheet.worksheet("custos_essenciais")
        ana = []
        mandi = []
        for r in ws.get_all_records():
            item = {"nome": str(r.get("nome", "")),
                    "valor": parse_br_number(r.get("valor", 0))}
            pessoa = str(r.get("pessoa", "")).lower()
            if "ana" in pessoa:
                ana.append(item)
            else:
                mandi.append(item)
        return {"ana_lua": ana, "mandelinha": mandi}
    except Exception:
        return {
            "ana_lua": [
                {"nome": "Leite Nan",       "valor": 280},
                {"nome": "Pomada",          "valor": 40},
                {"nome": "Lenço umedecido", "valor": 60},
                {"nome": "Farmácia",        "valor": 150},
                {"nome": "Papinha",         "valor": 50},
            ],
            "mandelinha": [
                {"nome": "Fralda pet",     "valor": 120},
                {"nome": "Plano Pet Love", "valor": 59},
            ],
        }


# ============================================================
# 8. HELPERS
# ============================================================
def parse_date(s):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(s).strip(), fmt)
        except (ValueError, TypeError):
            pass
    return None


def fmt_mes(m):
    try:
        dt = datetime.strptime(m + "-01", "%Y-%m-%d")
        return dt.strftime("%b/%y").capitalize()
    except Exception:
        return m


# ============================================================
# 9. PROCESSAMENTO PRINCIPAL
# ============================================================
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
    total_rec = sum(r["valor"] for r in receitas)
    total_gast = sum(g["valor"] for g in gastos)
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

    # Evolução mensal
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

    # Variação
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

    # Média diária (últimos 30 dias)
    trinta = datetime.now() - timedelta(days=30)
    g30 = sum(g["valor"] for g in gastos if parse_date(g.get("data", "")) and parse_date(g["data"]) >= trinta)
    media_diaria = round(g30 / 30, 2) if g30 > 0 else 0

    # Indicadores
    taxa_esforco = round((total_gast / total_rec * 100), 1) if total_rec > 0 else 0
    cap_poupanca = round(((total_rec - total_gast) / total_rec * 100), 1) if total_rec > 0 else 0
    dias_reserva = round(saldo / media_diaria, 1) if media_diaria > 0 and saldo > 0 else 0

    # Score
    score = 0
    if cap_poupanca >= 20:
        score += 30
    elif cap_poupanca >= 10:
        score += 15

    over = sum(1 for c, l in LIMITES_CATEGORIA.items() if gastos_cat_mes_atual.get(c, 0) > l)
    if over == 0:
        score += 20
    elif over == 1:
        score += 10

    psr = 500 / renda_ref if renda_ref > 0 else 1
    if psr < 0.15:
        score += 25
    elif psr < 0.30:
        score += 15
    elif psr < 0.50:
        score += 5

    if dias_reserva >= 180:
        score += 25
    elif dias_reserva >= 90:
        score += 15
    elif dias_reserva >= 30:
        score += 5

    proximas = [p for p in amort if p["status"] == "Pendente"][:10]
    meses_disponiveis = sorted(list(set(g["data"][:7] for g in gastos if len(g.get("data", "")) >= 7)), reverse=True)

    # JSON final
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

    print("\n✅ data.json gerado CORRETAMENTE!")
    print(f"   💰 Receitas:      R$ {total_rec:>10,.2f}")
    print(f"   💸 Gastos:        R$ {total_gast:>10,.2f}")
    print(f"   ⚖️  Saldo:         R$ {saldo:>10,.2f}")
    print(f"   📊 Taxa esforço:  {taxa_esforco}%")
    print(f"   💪 Cap. poupança: {cap_poupanca}%")
    print(f"   ❤️  Score:         {score}/100")
    print(f"   🏦 Dívida:        R$ {saldo_dev:,.2f}")
    print(f"   📅 Meses com dados: {len(meses_disponiveis)}")
    if alertas:
        print(f"\n   🚨 {len(alertas)} alertas de limite:")
        for a in alertas:
            print(f"      {a}")


if __name__ == "__main__":
    process_sheet()
