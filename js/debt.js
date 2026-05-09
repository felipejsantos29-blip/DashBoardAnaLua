/**
 * WealthAurora - Módulo de Dívidas
 * Gerencia o empréstimo Cirlene, parcelas, simulador de amortização
 */

class DebtManager {
  constructor(dataService) {
    this.dataService = dataService;
  }

  async init() {
    const data = await this.dataService.fetchData();
    this.render(data);
    this.setupSimulator(data);
    
    this.dataService.onDataLoaded((newData) => {
      this.render(newData);
      this.setupSimulator(newData);
    });
  }

  render(data) {
    const emprestimo = data.emprestimo || {};
    const saldoDevedor = emprestimo.saldoDevedor || 35000;
    const parcelasPagas = emprestimo.parcelasPagas || 0;
    const totalParcelas = emprestimo.totalParcelas || 30;
    const percentPago = ((35000 - saldoDevedor) / 35000) * 100;

    // Renderizar summary
    const summaryHtml = `
      <div class="debt-summary">
        <div class="debt-stat"><div class="debt-stat-label">Credor</div><div class="debt-stat-val" style="color:var(--teal)">${emprestimo.nomeCredor || 'Cirlene'}</div></div>
        <div class="debt-stat"><div class="debt-stat-label">Valor Original</div><div class="debt-stat-val">R$ ${(emprestimo.valorOriginal || 35000).toLocaleString('pt-BR')}</div></div>
        <div class="debt-stat"><div class="debt-stat-label">Saldo Devedor</div><div class="debt-stat-val" style="color:var(--red)">R$ ${saldoDevedor.toLocaleString('pt-BR')}</div></div>
      </div>
    `;
    
    const debtSummary = document.getElementById('debtSummary');
    const debtProgress = document.getElementById('debtProgressFill');
    const debtStats = document.getElementById('debtStats');
    
    if (debtSummary) debtSummary.innerHTML = summaryHtml;
    if (debtProgress) debtProgress.style.width = `${Math.min(100, percentPago)}%`;
    if (debtStats) {
      debtStats.innerHTML = `
        <span>📊 ${parcelasPagas} de ${totalParcelas} parcelas pagas</span>
        <span>🎯 Quitação prevista: ${this.getPrevisaoQuitacao()}</span>
      `;
    }

    // Renderizar lista de parcelas (simuladas)
    this.renderParcelasList(parcelasPagas);
  }

  getPrevisaoQuitacao() {
    const hoje = new Date();
    hoje.setMonth(hoje.getMonth() + 30);
    return hoje.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
  }

  renderParcelasList(parcelasPagas) {
    const container = document.getElementById('parcelasList');
    if (!container) return;

    const parcelas = [];
    const inicio = new Date(2026, 5, 5); // Junho 2026
    
    for (let i = 1; i <= 12; i++) {
      const data = new Date(inicio);
      data.setMonth(inicio.getMonth() + i - 1);
      const isPLR = (i === 1 || i === 7);
      const valorBase = 500;
      const valorExtra = isPLR ? 4000 : 0;
      const valorTotal = valorBase + valorExtra;
      const isPaga = i <= parcelasPagas;
      
      parcelas.push({
        numero: i,
        data: data,
        valorTotal: valorTotal,
        isPLR: isPLR,
        isPaga: isPaga
      });
    }

    container.innerHTML = parcelas.map(p => {
      const hoje = new Date();
      const isProxima = !p.isPaga && p.data >= hoje && 
                        (!parcelas.find(p2 => !p2.isPaga && p2.data < p.data));
      
      let classes = 'parcela-item';
      if (p.isPaga) classes += ' parcela-paga';
      if (isProxima) classes += ' highlight';
      
      return `
        <div class="${classes}">
          <div>
            <strong>Parcela ${p.numero}</strong> - ${p.data.toLocaleDateString('pt-BR')}
            ${p.isPLR ? '<span class="limit-badge warning" style="margin-left:8px">⚠️ Semestral +R$4.000</span>' : ''}
          </div>
          <div class="font-mono">R$ ${p.valorTotal.toLocaleString('pt-BR')}</div>
        </div>
      `;
    }).join('');

    // Verificar próxima parcela pesada
    const nextHeavy = parcelas.find(p => !p.isPaga && p.isPLR);
    const alertContainer = document.getElementById('parcelaPesadaAlert');
    if (alertContainer && nextHeavy) {
      alertContainer.innerHTML = `
        <i class="fas fa-exclamation-triangle"></i> 
        ⚠️ Atenção! Em ${nextHeavy.data.toLocaleDateString('pt-BR')} você terá parcela de R$ ${nextHeavy.valorTotal.toLocaleString('pt-BR')} (inclui R$ 4.000 do pagamento semestral)
      `;
      alertContainer.classList.remove('hidden');
    } else if (alertContainer) {
      alertContainer.classList.add('hidden');
    }
  }

  setupSimulator(data) {
    const btn = document.getElementById('calcularSimulacao');
    const input = document.getElementById('extraAmort');
    const resultDiv = document.getElementById('simulacaoResultado');
    
    if (!btn || !input || !resultDiv) return;

    btn.onclick = () => {
      const extra = parseFloat(input.value) || 0;
      const saldoAtual = data.emprestimo?.saldoDevedor || 35000;
      const parcelaBase = 500;
      const totalMensal = parcelaBase + extra;
      
      const mesesRestantes = Math.ceil(saldoAtual / totalMensal);
      const dataQuitacao = new Date();
      dataQuitacao.setMonth(dataQuitacao.getMonth() + mesesRestantes);
      
      const mesesOriginais = 30;
      const mesesEconomizados = Math.max(0, mesesOriginais - mesesRestantes);
      const economiaEstimada = mesesEconomizados * parcelaBase;
      
      resultDiv.innerHTML = `
        <i class="fas fa-chart-line"></i>
        Com +R$ ${extra.toLocaleString('pt-BR')}/mês, você quita em ${mesesRestantes} meses 
        (${dataQuitacao.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })})
        ${mesesEconomizados > 0 ? `<br>📉 Economia de ${mesesEconomizados} meses (~R$ ${economiaEstimada.toLocaleString('pt-BR')})` : ''}
      `;
      resultDiv.style.display = 'block';
    };
  }
}

let debtManager;
