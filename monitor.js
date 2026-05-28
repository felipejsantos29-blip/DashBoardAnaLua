// ============================================
// VERSÃO DE TESTE - COM GASTO FALSO ALTO
// ============================================

const API_KEY = '4459508';
const SEU_NUMERO = '5511993217289';
const NOME_GRUPO = 'Alertas+Financeiro'; // Nome exato do seu grupo

const URL_DATA_JSON = 'https://felipejsantos29-blip.github.io/DashBoardAnaLua/data.json';

async function enviarWhatsApp(mensagem) {
    const url = `https://api.callmebot.com/whatsapp.php?phone=${SEU_NUMERO}&text=${encodeURIComponent(mensagem)}&apikey=${API_KEY}&group=${NOME_GRUPO}`;
    
    try {
        const resposta = await fetch(url);
        console.log(`✅ Alerta enviado: ${mensagem.substring(0, 50)}...`);
        return true;
    } catch (erro) {
        console.error(`❌ Erro: ${erro.message}`);
        return false;
    }
}

// VERSÃO DE TESTE: Forçando gastos altos para gerar alerta
async function verificarLimites() {
    console.log('🔍 TESTE - Forçando alertas...', new Date().toLocaleString());
    
    // Dados falsos para teste
    const gastosTeste = {
        'Alimentação': 1400,   // 93% do limite de 1500 -> ALERTA
        'Transporte': 750,     // 93% do limite de 800 -> ALERTA
        'Lazer': 480,          // 96% do limite de 500 -> ALERTA
        'Pet': 100,            // 33% do limite -> SEM ALERTA
        'Assinatura': 140      // 93% -> ALERTA
    };
    
    const limites = {
        'Alimentação': 1500,
        'Transporte': 800,
        'Lazer': 500,
        'Pet': 300,
        'Assinatura': 150
    };
    
    let alertasEnviados = 0;
    
    for (const [categoria, limite] of Object.entries(limites)) {
        const gasto = gastosTeste[categoria] || 0;
        const percentual = (gasto / limite) * 100;
        
        if (percentual >= 80) {
            let mensagem = '';
            if (percentual >= 100) {
                mensagem = `🚨 *LIMITE EXCEDIDO!* (TESTE)\n\n*${categoria}*: ${percentual.toFixed(0)}%\n💰 R$ ${gasto} / R$ ${limite}`;
            } else {
                const restante = limite - gasto;
                mensagem = `⚠️ *TESTE - ATENÇÃO!*\n\n*${categoria}* está em ${percentual.toFixed(0)}% do limite\n💰 Gastou: R$ ${gasto} / R$ ${limite}\n📌 Faltam R$ ${restante}`;
            }
            await enviarWhatsApp(mensagem);
            alertasEnviados++;
            await new Promise(r => setTimeout(r, 2000));
        }
    }
    
    console.log(`✅ TESTE CONCLUÍDO: ${alertasEnviados} alerta(s) enviado(s)`);
}

verificarLimites();
