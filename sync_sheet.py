# sync_sheet.py
import gspread
import json
import os
import re
from datetime import datetime
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials

# ============================================================
# CONFIGURAÇÕES (NÃO ALTERE)
# ============================================================
SHEET_ID = "1BGYyMz9BZ0ypEaJfv5InDWwVZ73iK58p9W-QOsBY3Gk"
SHEET_NAME = "movimentacoes"      # Nome da aba principal
CATEGORIA_STATUS = "Valor"        # Coluna que tem "dívida"/"pago"
# ============================================================

# Mapeamento de palavras-chave para categorias
REGRA_CATEGORIA = {
    "UBER": "Transporte", "99APP": "Transporte", "TOP SP": "Transporte",
    "MERCADO": "Alimentação", "IFD": "Alimentação", "DROGARIA": "Saúde",
    "PETLOVE": "Pet", "CLARO": "Serviços", "SPOTIFY": "Streaming",
    "AMAZON": "Compras", "SHOPEE": "Compras", "AIRBNB": "Viagem",
    "SALARIO": "Salário", "REMUNERACAO": "Salário", "REND PAGO": "Rendimento",
    "IOF": "Taxas Bancárias", "JUROS": "Taxas Bancárias",
    "FATURA PAGA": "Pagamento de Fatura",
}

# Categorias e palavras que DEVEM SER IGNORADAS (não entram nas contas)
CATEGORIAS_IGNORAR = {"Pagamento Cartão", "Investimento", "Empréstimo", "Transferência", "Reembolso", "Rendimento", "Depósito"}
PALAVRAS_IGNORAR = ["FATURA PAGA", "APLICACAO COFRINHOS", "PIX TRANSF CIRLENE", "PIX TRANSF FELIPE", "SALDO TOTAL", "REND PAGO APLIC AUT MAIS", "DEV PIX", "JUROS LIMITE DA CONTA", "SEGURO LIS ITAU"]

def limpar_valor(valor_bruto):
    """
    Função SUPER robusta para converter qualquer formato de número para float.
    Trata:
    - Números com pontos como milhar: 1.644,00 → 16.44 (detecta automaticamente)
    - Números com vírgula como decimal: 16,44 → 16.44
    - Números normais: 16.44 → 16.44
    - Strings com R$: "R$ 16,44" → 16.44
    """
    if isinstance(valor_bruto, (int, float)):
        return float(valor_bruto)
    
    if not valor_bruto:
        return 0.0
    
    valor_str = str(valor_bruto).strip()
    
    # Remove 'R$' e espaços
    valor_str = re.sub(r'[R$\s]', '', valor_str)
    
    # ✅ DETECÇÃO INTELIGENTE DE SEPARADORES
    # Se tem ponto e vírgula: "1.644,00" → remove ponto, troca vírgula por ponto
    if '.' in valor_str and ',' in valor_str:
        # Formato brasileiro: 1.644,00 (ponto = milhar, vírgula = decimal)
        valor_str = valor_str.replace('.', '').replace(',', '.')
    elif ',' in valor_str and '.' not in valor_str:
        # Só tem vírgula: 16,44 → ponto de decimal
        valor_str = valor_str.replace(',', '.')
    elif '.' in valor_str:
        # Só tem ponto: pode ser 16.44 (decimal) ou 1644 (errado)
        # Se tiver 2 casas decimais após ponto, é decimal; senão, é milhar
        partes = valor_str.split('.')
        if len(partes) == 2 and len(partes[-1]) == 2:
            # 16.44 → mantém (decimal correto)
            pass
        elif len(partes) > 2:
            # 1.644.00 → remove os pontos de milhar
            valor_str = valor_str.replace('.', '')
    
    try:
        resultado = float(valor_str)
        # ✅ VALIDAÇÃO: Se o valor é absurdamente grande (> 100k), avisa
        if abs(resultado) > 100000:
            print(f"⚠️ AVISO: Valor muito alto detectado: {resultado} (origem: {valor_bruto})")
        return resultado
    except ValueError as e:
        print(f"❌ ERRO ao converter: '{valor_bruto}' → '{valor_str}' ({e})")
        return 0.0

def converter_data_para_mes(data_str):
    """Converte data em formato DD/MM/YYYY para YYYY-MM"""
    try:
        if not data_str or len(data_str) < 10:
            return None
        # Assume formato DD/MM/YYYY
        dia, mes, ano = data_str[:10].split('/')
        return f"{ano}-{mes}"
    except:
        return None

def deve_ignorar(descricao, categoria, valor):
    cat_lower = categoria.lower()
    if cat_lower in [c.lower() for c in CATEGORIAS_IGNORAR]:
        return True
    desc_upper = descricao.upper()
    if any(palavra.upper() in desc_upper for palavra in PALAVRAS_IGNORAR):
        return True
    if "EMANUEL" in desc_upper and abs(valor) > 100:
        return True
    return False

def definir_categoria(descricao):
    desc_upper = descricao.upper()
    for palavra, categoria in REGRA_CATEGORIA.items():
        if palavra.upper() in desc_upper:
            return categoria
    return "Outros"

# ============================================================
# CONEXÃO COM A PLANILHA (usando a API)
# ============================================================
def conectar_planilha():
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("ERRO: A variável de ambiente GOOGLE_CREDENTIALS não está definida.")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, escopo)
    cliente = gspread.authorize(creds)
    return cliente.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

# ============================================================
# LEITURA E PROCESSAMENTO DOS DADOS
# ============================================================
def processar_dados():
    print("🔄 Conectando à planilha...")
    planilha = conectar_planilha()
    dados = planilha.get_all_records()
    print(f"✅ {len(dados)} linhas encontradas.")

    gastos_reais = []
    receitas_reais = []
    detalhes_ignorados = []

    for idx, linha in enumerate(dados, start=2):
        # --- 1. Extrair e limpar os campos ---
        descricao = str(linha.get("descrição", "")).strip()
        if not descricao:
            continue
        categoria_bruta = str(linha.get("categoria", "")).strip()
        data_str = str(linha.get("data", "")).strip()
        tipo = str(linha.get("tipo_registro", "")).strip().lower()
        status = str(linha.get(CATEGORIA_STATUS, "")).strip().lower()
        cartao_final = str(linha.get("cartao_final", "")).strip()

        # Converte o valor usando a função SUPER robusta
        valor_bruto = linha.get("valor", 0.0)
        valor_float = limpar_valor(valor_bruto)

        # Pula linhas sem valor ou com valor zero
        if valor_float == 0.0:
            continue

        # --- 2. Aplicar as regras de sinal (baseado na coluna 'Valor') ---
        if status == "divida":
            if valor_float > 0:
                valor_float = -abs(valor_float)    # Se for positivo, torna negativo (despesa)
            # Se já for negativo, mantém
        elif status == "pago":
            if valor_float < 0:
                valor_float = abs(valor_float)     # Se for negativo, torna positivo (receita)
            # Se já for positivo, mantém
        # Se não houver status, não altera o sinal (confia no que veio)

        # --- 3. Filtros (ignorar transações que não devem ser contabilizadas) ---
        if deve_ignorar(descricao, categoria_bruta, valor_float):
            detalhes_ignorados.append(f"  ⏭️ [{descricao[:50]}] R$ {valor_float:.2f}")
            continue

        # --- 4. Classificar como GASTO ou RECEITA (baseado no sinal após as regras) ---
        if valor_float < 0:  # É despesa
            categoria_final = definir_categoria(descricao)
            cartao = cartao_final if cartao_final not in ["", "None", "nan"] else None
            gastos_reais.append({
                "data": data_str,
                "descricao": descricao[:60],
                "valor": round(abs(valor_float), 2),  # ✅ Arredonda para 2 casas decimais
                "categoria": categoria_final,
                "tipo": tipo,
                "cartao": cartao,
            })
        elif valor_float > 0:  # É receita
            # Confirma se é realmente uma receita (salário, etc.)
            if "SALARIO" in descricao.upper() or "REMUNERACAO" in descricao.upper() or "TEF CREDITO" in descricao.upper():
                receitas_reais.append({
                    "data": data_str,
                    "descricao": descricao[:60],
                    "valor": round(valor_float, 2),  # ✅ Arredonda para 2 casas decimais
                    "categoria": "Salário",
                })
            else:
                # Outras receitas (ex: transferências, reembolsos) são ignoradas por padrão
                detalhes_ignorados.append(f"  ➕ Receita ignorada: {descricao[:50]} - R$ {valor_float:.2f}")
        # Se for zero, já foi ignorado antes

    print(f"📊 Resumo: {len(gastos_reais)} gastos | {len(receitas_reais)} receitas | {len(detalhes_ignorados)} ignorados")
    if detalhes_ignorados:
        print("Principais ignorados:")
        for ign in detalhes_ignorados[:5]:
            print(ign)

    return gastos_reais, receitas_reais

# ============================================================
# MONTAGEM DO JSON FINAL
# ============================================================
if __name__ == "__main__":
    gastos, receitas = processar_dados()
    total_gastos = sum(g["valor"] for g in gastos)
    total_receitas = sum(r["valor"] for r in receitas)

    # Cálculos básicos para o dashboard
    saldo = total_receitas - total_gastos
    taxa_esforco = (total_gastos / total_receitas * 100) if total_receitas > 0 else 0

    # Agregar gastos por mês e categoria
    gastos_mensais = defaultdict(float)
    receitas_mensais = defaultdict(float)
    gastos_por_categoria = defaultdict(float)
    meses_disponiveis = set()

    for g in gastos:
        mes = converter_data_para_mes(g["data"])
        if mes:
            gastos_mensais[mes] += g["valor"]
            gastos_por_categoria[g["categoria"]] += g["valor"]
            meses_disponiveis.add(mes)

    for r in receitas:
        mes = converter_data_para_mes(r["data"])
        if mes:
            receitas_mensais[mes] += r["valor"]
            meses_disponiveis.add(mes)

    # Criação do objeto final
    data = {
        "lastUpdate": datetime.now().isoformat(),
        "totalReceitas": round(total_receitas, 2),
        "totalGastos": round(total_gastos, 2),
        "saldoTotal": round(saldo, 2),
        "taxaEsforco": round(taxa_esforco, 2),
        "scoreFinanceiro": 45,
        "gastosMensais": {k: round(v, 2) for k, v in gastos_mensais.items()},
        "receitasMensais": {k: round(v, 2) for k, v in receitas_mensais.items()},
        "gastosPorCategoria": {k: round(v, 2) for k, v in gastos_por_categoria.items()},
        "extrato": gastos,
        "receitas": receitas,
        "mesesDisponiveis": sorted(list(meses_disponiveis)),
        "stats": {
            "total_transacoes": len(gastos) + len(receitas),
            "meses_com_dados": len(meses_disponiveis),
            "total_receitas": len(receitas),
        },
    }

    # Salva o arquivo data.json
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("\n✅ data.json gerado com sucesso!")
