// ============================================
// MONITOR DE LIMITES - VIA GITHUB ACTIONS
// ============================================

const API_KEY = '4459508';
const SEU_NUMERO = '5511993217289';
const NOME_GRUPO = 'Alertas+Financeiros'; // MUDE PARA O NOME DO SEU GRUPO

const URL_DATA_JSON = 'https://felipejsantos29-blip.github.io/DashBoardAnaLua/data.json';

async function enviarWhatsApp(mensagem) {
    const url = `https://api.callmebot.com/whatsapp.php?phone=${SEU_NUMERO}&text=${encodeURIComponent(mensagem)}&apikey=${API_KEY}&group=${encodeURIComponent(NOME_GRUPO)}`;
    
    try {
        const resposta = await fetch(url);
        const texto = await resposta.text();
        console.log(`✅ Enviado: ${texto.substring(0, 50)}`);
        return true;
    } catch (erro) {
        console.error(`❌ Erro: ${erro.message}`);
        return false;
    }
}

async function verificarLimites() {
    console.log('🔍 Verificando...', new Date().toLocaleString());
    
    try {
        const resposta = await fetch(URL_DATA_JSON + '?t=' + Date.now());
        const dados = await resposta.json();
        
        const meses = dados.mesesDisponiveis || [];
        if (meses.length === 0) return;
        
        const mesAtual = meses[meses.length - 1];
        const gastosCat = dados.gastosCatMesAtual || {};
        const limites = dados.limitesSugeridos || {};
        
        let alertasEnviados = 0;
        
        for (const [categoria, limite] of Object.entries(limites)) {
            const gasto = gastosCat[categoria] || 0;
            const percentual = (gasto / limite) * 100;
            
            if (percentual >= 80) {
                let mensagem = '';
                if (percentual >= 100) {
                    mensagem = `🚨 *LIMITE EXCEDIDO!*\n\n*${categoria}*: ${percentual.toFixed(0)}%\n💰 R$ ${gasto.toFixed(2)} / R$ ${limite.toFixed(2)}`;
                } else {
                    const restante = limite - gasto;
                    mensagem = `⚠️ *ATENÇÃO!*\n\n*${categoria}*: ${percentual.toFixed(0)}%\n💰 R$ ${gasto.toFixed(2)} / R$ ${limite.toFixed(2)}\n📌 Faltam R$ ${restante.toFixed(2)}`;
                }
                await enviarWhatsApp(mensagem);
                alertasEnviados++;
                await new Promise(r => setTimeout(r, 2000));
            }
        }
        
        console.log(`✅ ${alertasEnviados} alerta(s) enviado(s)`);
        
    } catch (erro) {
        console.error('❌ Erro:', erro.message);
    }
}

verificarLimites();
