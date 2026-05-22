# sync_sheet.py - WealthAurora
# Versão ajustada para a nova estrutura da planilha
# Aba principal: "Página1" (movimentações)

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
    "Latam":   "7398",
    "Click":   "5217",
    "Extrato": None,
}

# --- CONFIGURAÇÃO DAS COLUNAS (Ajuste aqui se os nomes mudarem) ---
COLUNAS = {
    "data": "Data",
    "descricao": "Descrição",
    "valor": "Valor",
    "tipo": "Tipo",
    "categoria": "Categoria",
    "subcategoria": "Subcategoria"
}

# Categorias para ignorar (movimentos internos)
CATEGORIAS_IGNORAR = {
    "Cartão", "Cancelamento", "Transferência", "Cofrinhos",
    "Pix", "Dívida", "Encargos", "Casa", "Empréstimo",
}

# ... (O resto das funções utilitárias limpar_valor, parse_data, etc.
# permanecem IDÊNTICAS ao script anterior. Mantenha-as como estão.)
# ...

# ============================================================
# CONEXÃO COM GOOGLE SHEETS (VERSÃO CORRIGIDA)
# ============================================================
def conectar():
    escopo = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("Variável GOOGLE_CREDENTIALS não definida.\n"
                        "Adicione o JSON da service account como secret no GitHub.")
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        json.loads(creds_json), escopo
    )
    cliente = gspread.authorize(creds)
    # Retorna a planilha, não o cliente
    planilha = cliente.open_by_key(SHEET_ID)
    return planilha

# ============================================================
# PROCESSAMENTO PRINCIPAL (AJUSTADO)
# ============================================================
def processar():
    print("🔄 Conectando ao Google Sheets...")
    planilha = conectar()

    # --- AQUI ESTÁ O AJUSTE: Lendo a aba 'Página1' ---
    aba_movimentacoes = None
    try:
        # Tenta encontrar uma aba que contenha as movimentações
        aba_movimentacoes = planilha.worksheet("Página1")
        print("✅ Aba 'Página1' encontrada. Lendo movimentações...")
    except gspread.exceptions.WorksheetNotFound:
        print("❌ Aba 'Página1' não encontrada. Verifique o nome.")
        # Se não achar, tenta uma lista de nomes comuns como fallback
        for nome_aba in ["movimentacoes", "Extrato", "Movimentações", "Lançamentos"]:
            try:
                aba_movimentacoes = planilha.worksheet(nome_aba)
                print(f"✅ Aba '{nome_aba}' encontrada.")
                break
            except:
                continue

    if not aba_movimentacoes:
        raise Exception("Nenhuma aba de movimentações encontrada. Verifique o nome no Google Sheets.")

    # Pega todos os registros da planilha
    dados_mov = aba_movimentacoes.get_all_records()
    print(f"✅ {len(dados_mov)} movimentações carregadas.")

    # --- FALLBACK para dados fixos (já que as abas não existem) ---
    print("⚠️ Abas 'gastos_fixos' e 'orcamento' não encontradas. Usando valores padrão.")
    # Limites padrão (úteis para o gráfico de limite vs gasto)
    limites = {
        "Alimentação": 1500.0,
        "Transporte": 800.0,
        "Lazer": 500.0,
        "Saúde": 500.0,
        "Pet": 300.0
    }
    
    # Receitas e despesas fixas padrão (fallback)
    RECEITAS_FIXAS_PADRAO = [
        {"descricao": "Salário Felipe", "categoria": "Salário", "valor": 3600},
        {"descricao": "Salário Emanuela", "categoria": "Salário", "valor": 2700},
        {"descricao": "VA/VR Felipe", "categoria": "Benefícios", "valor": 650},
        {"descricao": "VA/VR Emanuela", "categoria": "Benefícios", "valor": 800}
    ]
    DESPESAS_FIXAS_PADRAO = [
        {"descricao": "Aluguel", "categoria": "Moradia", "valor": 1500},
        {"descricao": "Condomínio", "categoria": "Moradia", "valor": 300},
        {"descricao": "Luz", "categoria": "Casa", "valor": 150},
        {"descricao": "Internet", "categoria": "Casa", "valor": 100}
    ]
    receitas_fixas = RECEITAS_FIXAS_PADRAO
    despesas_fixas = DESPESAS_FIXAS_PADRAO
    receita_mensal_fixa = sum(r["valor"] for r in receitas_fixas)

    # --- Processamento dos Lançamentos (AGORA USANDO OS NOMES DAS COLUNAS CORRETOS) ---
    gastos = []
    receitas_extrato = []
    
    for idx, linha in enumerate(dados_mov):
        # Acessa os valores usando os nomes das colunas definidos em COLUNAS
        data_str = str(linha.get(COLUNAS["data"], "")).strip()
        descricao = str(linha.get(COLUNAS["descricao"], "")).strip()
        # Limpa o valor, que pode vir como "R$ 39,99"
        valor_str = str(linha.get(COLUNAS["valor"], "0"))
        valor = limpar_valor(valor_str)
        tipo_orig = str(linha.get(COLUNAS["tipo"], "")).strip()
        categoria = str(linha.get(COLUNAS["categoria"], "Outros")).strip()
        subcategoria = str(linha.get(COLUNAS["subcategoria"], "")).strip()
        
        if not descricao:
            continue
        if valor == 0:
            continue

        cartao = MAPA_TIPO_CARTAO.get(tipo_orig, None)

        # Ignora receitas do extrato (usamos o valor fixo)
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
            "subcategoria": subcategoria,
            "cartao": cartao,
        })

    # --- O resto do script (agregação, geração do JSON) permanece igual ---
    # ... (código de agregação, cálculo de scores, dívida, etc.)
    # ...
    
    # Salva o JSON no final
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ data.json gerado com sucesso!")
    print(f"   Total de gastos processados: R$ {sum(g['valor'] for g in gastos):,.2f}")
    print(f"   Total de transações: {len(gastos)}")

if __name__ == "__main__":
    processar()
