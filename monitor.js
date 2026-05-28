// ============================================
// MONITOR FINANCEIRO COMPLETO
// - Alertas de limite (80%+)
// - Relatório a cada 3 dias
// - Envio para dois números
// ============================================

// ===== CONFIGURAÇÕES =====
const API_KEY_VOCE = '4459508';
const API_KEY_ESPOSA = '';  // ⚠️ SUA ESPOSA PRECISA ATIVAR E COLOCAR A CHAVE DELA AQUI

const SEU_NUMERO = '5511993217289';
const NUMERO_ESPOSA = '';  // ⚠️ COLOQUE O NÚMERO DA SUA ESPOSA COM DDD (sem 55)

const URL_DATA_JSON = 'https://felipejsantos29-blip.github.io/DashBoardAnaLua/data.json';

// ===== FUNÇÃO PARA ENVIAR WHATSAPP =====
async function enviarWhatsApp(mensagem, destinatario) {
    const apiKey = destinatario === 'voce' ? API_KEY_VOCE : API_KEY_ESPOSA;
    const numero = destinatario === 'voce' ? SEU_NUMERO : NUMERO_ESPOSA;
    
    if (!apiKey || !numero) {
        console.log(`⚠️ Destinatário ${destinatario} não configurado`);
        return false;
    }
    
    const url = `https://api.callmebot.com/whatsapp.php?phone=${numero}&text=${encodeURIComponent(mensagem)}&apikey=${apiKey}`;
    
    try {
        const resposta = await fetch(url);
        console.log(`✅ Mensagem enviada para ${destinatario}`);
        return true;
    } catch (erro) {
        console.error(`❌ Erro ao enviar para ${destinatario}: ${erro.message}`);
        return false;
    }
}

// ===== FUNÇÃO PARA ENVIAR PARA AMBOS =====
async function enviarParaAmbos(mensagem) {
    await enviarWhatsApp(mensagem, 'voce');
    if (API_KEY_ESPOSA && NUMERO_ESPOSA) {
        await enviarWhatsApp(mensagem, 'esposa');
    }
}

// ===== FUNÇÃO PARA FORMATAR MOEDA =====
function brl(valor) {
    return `R$ ${valor.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ===== FUNÇÃO PARA CRIAR BARRA DE PROGRESSO =====
function barraProgresso(percentual) {
    const blocos = 10;
    const preenchidos = Math.min(10, Math.max(0, Math.round(percentual / 10)));
    let barra = '';
    for (let i = 0; i < blocos; i++) {
        barra += i < preenchidos ? '█' : '░';
    }
    return barra;
}

// ===== ALERTAS DE LIMITE (80%+) =====
async function verificarAlertasLimite(dados) {
    const meses = dados.mesesDisponiveis || [];
    if (meses.length === 0) return 0;
    
    const mesAtual = meses[meses.length - 1];
    const gastosCat = dados.gastosCatMesAtual || {};
    const limites = dados.limitesSugeridos || {};
    
    let alertasEnviados = 0;
    
    for (const [categoria, limite] of Object.entries(limites)) {
        const gasto = gastosCat[categoria] || 0;
        const percentual = (gasto / limite) * 100;
        
        if (percentual >= 80) {
            const restante = limite - gasto;
            const barra = barraProgresso(percentual);
            
            let mensagem = '';
            if (percentual >= 100) {
                mensagem = `🚨 *LIMITE EXCEDIDO!* 🚨\n\n📌 *${categoria}*\n💰 ${brl(gasto)} / ${brl(limite)}\n📊 ${barra} ${percentual.toFixed(0)}%\n\n⚠️ Corte gastos nesta categoria!`;
            } else {
                mensagem = `⚠️ *ATENÇÃO!* ⚠️\n\n📌 *${categoria}*\n💰 ${brl(gasto)} / ${brl(limite)}\n📊 ${barra} ${percentual.toFixed(0)}%\n📌 Faltam ${brl(restante)} para o limite.`;
            }
            
            await enviarParaAmbos(mensagem);
            alertasEnviados++;
            await new Promise(r => setTimeout(r, 2000));
        }
    }
    
    return alertasEnviados;
}

// ===== RELATÓRIO COMPLETO DE STATUS =====
async function enviarRelatorioStatus(dados) {
    const meses = dados.mesesDisponiveis || [];
    if (meses.length === 0) return;
    
    const mesAtual = meses[meses.length - 1];
    const mesAnterior = meses.length >= 2 ? meses[meses.length - 2] : null;
    
    // Dados principais
    const saldo = dados.saldoTotal || 0;
    const receitas = dados.totalReceitas || 0;
    const despesas = dados.totalGastos || 0;
    const taxaEsforco = dados.taxaEsforco || 0;
    const score = dados.scoreFinanceiro || 0;
    
    // Comparação com mês anterior
    let variacaoDespesas = 0;
    let variacaoReceitas = 0;
    if (mesAnterior) {
        const despAtual = dados.gastosMensais?.[mesAtual] || 0;
        const despAnt = dados.gastosMensais?.[mesAnterior] || 0;
        const recAtual = dados.receitasMensais?.[mesAtual] || 0;
        const recAnt = dados.receitasMensais?.[mesAnterior] || 0;
        
        variacaoDespesas = despAnt > 0 ? ((despAtual - despAnt) / despAnt * 100) : 0;
        variacaoReceitas = recAnt > 0 ? ((recAtual - recAnt) / recAnt * 100) : 0;
    }
    
    // Top categorias de gasto
    const gastosPorCat = dados.gastosPorCategoria || {};
    const topCategorias = Object.entries(gastosPorCat).slice(0, 3);
    
    // Alertas existentes
    const alertasExistentes = dados.alertas || [];
    
    // Score visual
    const scoreEmoji = score >= 70 ? '🟢' : score >= 40 ? '🟡' : '🔴';
    const saldoEmoji = saldo >= 0 ? '💰' : '🔴';
    const esforcoEmoji = taxaEsforco <= 80 ? '✅' : '⚠️';
    
    // Monta a mensagem
    let mensagem = `📊 *RELATÓRIO FINANCEIRO*\n`;
    mensagem += `📅 Período: ${mesAtual.replace('-', '/')}\n`;
    mensagem += `🕐 ${new Date().toLocaleDateString('pt-BR')}\n\n`;
    
    mensagem += `━━━━━━━━━━━━━━━━━━\n`;
    mensagem += `💰 *SALDO*: ${saldoEmoji} ${brl(saldo)}\n`;
    mensagem += `📈 *RECEITAS*: ${brl(receitas)}\n`;
    mensagem += `📉 *DESPESAS*: ${brl(despesas)}\n`;
    
    if (variacaoDespesas !== 0) {
        const sinalDesp = variacaoDespesas > 0 ? '↑' : '↓';
        mensagem += `   └─ Variação: ${sinalDesp} ${Math.abs(variacaoDespesas).toFixed(1)}% vs mês anterior\n`;
    }
    
    mensagem += `\n📊 *TAXA DE ESFORÇO*: ${esforcoEmoji} ${taxaEsforco.toFixed(1)}%\n`;
    mensagem += `🏆 *SCORE DE SAÚDE*: ${scoreEmoji} ${score}/100\n\n`;
    
    mensagem += `━━━━━━━━━━━━━━━━━━\n`;
    mensagem += `📌 *TOP GASTOS*:\n`;
    topCategorias.forEach(([cat, valor], i) => {
        mensagem += `   ${i+1}º ${cat}: ${brl(valor)}\n`;
    });
    
    if (alertasExistentes.length > 0) {
        mensagem += `\n⚠️ *ALERTAS PENDENTES*:\n`;
        alertasExistentes.slice(0, 3).forEach(alerta => {
            mensagem += `   • ${alerta.substring(0, 50)}${alerta.length > 50 ? '…' : ''}\n`;
        });
    }
    
    mensagem += `\n━━━━━━━━━━━━━━━━━━\n`;
    mensagem += `💡 *DICA*: Controle seus limites para manter a saúde financeira!`;
    
    await enviarParaAmbos(mensagem);
}

// ===== FUNÇÃO PRINCIPAL =====
async function verificarLimites() {
    console.log('🔍 Iniciando monitoramento...', new Date().toLocaleString());
    
    try {
        const resposta = await fetch(URL_DATA_JSON + '?t=' + Date.now());
        const dados = await resposta.json();
        
        console.log(`✅ Dados carregados: ${dados.mesesDisponiveis?.length || 0} meses`);
        
        // 1. Verificar alertas de limite
        const alertasEnviados = await verificarAlertasLimite(dados);
        console.log(`📊 Alertas de limite: ${alertasEnviados} enviado(s)`);
        
        // 2. Verificar se precisa enviar relatório (a cada 3 dias)
        const ultimoRelatorio = localStorage ? localStorage.getItem('ultimoRelatorio') : null;
        const agora = new Date();
        const tresDias = 3 * 24 * 60 * 60 * 1000;
        
        let enviarRelatorio = false;
        if (!ultimoRelatorio) {
            enviarRelatorio = true;
        } else {
            const ultimo = new Date(ultimoRelatorio);
            if (agora - ultimo >= tresDias) {
                enviarRelatorio = true;
            }
        }
        
        if (enviarRelatorio) {
            console.log('📨 Enviando relatório periódico...');
            await enviarRelatorioStatus(dados);
            if (localStorage) {
                localStorage.setItem('ultimoRelatorio', agora.toISOString());
            }
            console.log('✅ Relatório enviado com sucesso');
        } else {
            const diasFaltando = Math.ceil((tresDias - (agora - new Date(ultimoRelatorio))) / (24 * 60 * 60 * 1000));
            console.log(`⏳ Próximo relatório em ${diasFaltando} dia(s)`);
        }
        
        console.log('🏁 Monitoramento concluído');
        
    } catch (erro) {
        console.error('❌ Erro no monitoramento:', erro.message);
    }
}

// Executar
verificarLimites();
