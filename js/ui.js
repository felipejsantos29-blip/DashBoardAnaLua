/**
 * WealthAurora - Módulo de Interface do Usuário
 * Gerencia tabs, filtros, extrato, metas, reserva de emergência
 */

class UIManager {
  constructor(dataService) {
    this.dataService = dataService;
  }

  async init() {
    const data = await this.dataService.fetchData();
    this.setupTabs();
    this.setupRefreshButton();
    this.setupExtratoFilters(data);
    this.setupMetas();
    this.renderEssenciais(data);
    this.renderReservaEmergencia(data);
    this.renderVariacoes(data);
    this.renderReceitasDespesasFixas(data);
    
    this.dataService.onDataLoaded((newData) => {
      this.renderEssenciais(newData);
      this.renderReservaEmergencia(newData);
      this.renderVariacoes(newData);
      this.renderReceitasDespesasFixas(newData);
      this.updateMainCards(newData);
    });
    
    this.updateMainCards(data);
  }

  setupTabs() {
    const tabs = document.querySelectorAll('.tab-btn');
    const contents = document.querySelectorAll('.tab-content');
    
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const tabId = tab.getAttribute('data-tab');
        
        tabs.forEach(t => t.classList.remove('active'));
        contents.forEach(c => c.classList.add('hidden'));
        
        tab.classList.add('active');
        const activeContent = document.getElementById(`tab-${tabId}`);
        if (activeContent) activeContent.classList.remove('hidden');
      });
    });
  }

  setupRefreshButton() {
    const btn = document.getElementById('refreshBtn');
    if (btn) {
      btn.addEventListener('click', async () => {
        const data = await this.dataService.fetchData(true);
        this.updateLastUpdateTime();
        this.renderEssenciais(data);
        this.renderReservaEmergencia(data);
        this.renderVariacoes(data);
        this.updateMainCards(data);
        if (chartsManager) chartsManager.renderAll(data);
        if (insightsManager) {
          insightsManager.generateInsights(data);
          insightsManager.calculateHealthScore(data);
        }
      });
    }
    this.updateLastUpdateTime();
  }

  updateLastUpdateTime() {
    const timeElement = document.getElementById('lastUpdateTime');
    if (timeElement) {
      const now = new Date();
      timeElement.innerHTML = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }
  }

  updateMainCards(data) {
    const saldoEl = document.getElementById('saldoAtual');
    const receitasEl = document.getElementById('totalReceitas');
    const despesasEl = document.getElementById('totalDespesas');
    const taxaEl = document.getElementById('taxaEsforco');
    const capPoupanca = document.getElementById('capPoupanca');
    const poupancaBar = document.getElementById('poupancaBar');
    const diasReserva = document.getElementById('diasReserva');
    
    if (saldoEl) {
      saldoEl.innerHTML = `R$ ${(data.saldoAtual || 0).toLocaleString('pt-BR')}`;
      saldoEl.style.color = data.saldoAtual >= 0 ? 'var(--emerald)' : 'var(--red)';
    }
    if (receitasEl) receitasEl.innerHTML = `R$ ${(data.totalReceitas || 0).toLocaleString('pt-BR')}`;
    if (despesasEl) despesasEl.innerHTML = `R$ ${(data.totalDespesas || 0).toLocaleString('pt-BR')}`;
    if (taxaEl) taxaEl.innerHTML = `${(data.taxaEsforco || 0).toFixed(1)}%`;
    
    const poupanca = data.capPoupanca || 0;
    if (capPoupanca) capPoupanca.innerHTML = `${poupanca.toFixed(1)}%`;
    if (poupancaBar) poupancaBar.style.width = `${Math.min(100, poupanca)}%`;
    if (diasReserva) diasReserva.innerHTML = Math.floor(data.diasReserva || 0);
  }

  setupExtratoFilters(data) {
    const filtroMes = document.getElementById('filtroMes');
    const filtroCategoria = document.getElementById('filtroCategoria');
    const buscaInput = document.getElementById('buscaExtrato');
    const limparBtn = document.getElementById('limparFiltros');
    
    if (!filtroMes) return;
    
    // Popular meses
    const meses = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06'];
    filtroMes.innerHTML = '<option value="todos">Todos os meses</option>' + 
      meses.map(m => `<option value="${m}">${this.formatMonth(m)}</option>`).join('');
    
    // Popular categorias
    const categorias = data.categorias || [];
    if (filtroCategoria) {
      filtroCategoria.innerHTML = '<option value="todas">Todas categorias</option>' + 
        categorias.map(c => `<option value="${c.nome}">${c.nome}</option>`).join('');
    }
    
    // Eventos
    filtroMes.addEventListener('change', () => this.renderExtrato(data));
    filtroCategoria.addEventListener('change', () => this.renderExtrato(data));
    if (buscaInput) buscaInput.addEventListener('input', () => this.renderExtrato(data));
    if (limparBtn) limparBtn.addEventListener('click', () => {
      filtroMes.value = 'todos';
      filtroCategoria.value = 'todas';
      if (buscaInput) buscaInput.value = '';
      this.renderExtrato(data);
    });
    
    this.renderExtrato(data);
  }

  renderExtrato(data) {
    const extrato = data.extrato || [];
    const mes = document.getElementById('filtroMes')?.value || 'todos';
    const categoria = document.getElementById('filtroCategoria')?.value || 'todas';
    const busca = document.getElementById('buscaExtrato')?.value.toLowerCase() || '';
    
    let filtered = [...extrato];
    
    if (filtered.length === 0) {
      // Dados mock para exemplo
      filtered = [
        { data: "2026-05-05", descricao: "PIX QRS 121 SMART", categoria: "Alimentação", valor: 2.19 },
        { data: "2026-05-04", descricao: "FATURA PAGA LATAM", categoria: "Cartão", valor: 1917.54 },
        { data: "2026-04-29", descricao: "TEF CREDITO SALARIO", categoria: "Salário", valor: -1739.69 }
      ];
    }
    
    if (mes !== 'todos') {
      filtered = filtered.filter(e => e.data?.startsWith(mes));
    }
    if (categoria !== 'todas') {
      filtered = filtered.filter(e => e.categoria === categoria);
    }
    if (busca) {
      filtered = filtered.filter(e => e.descricao?.toLowerCase().includes(busca));
    }
    
    const tbody = document.getElementById('extratoBody');
    const total = filtered.reduce((s, e) => s + (Math.abs(e.valor) || 0), 0);
    
    if (tbody) {
      tbody.innerHTML = filtered.slice(0, 50).map(e => `
        <tr>
          <td>${e.data || '-'}</td>
          <td>${e.descricao || '-'}</td>
          <td><span class="cat-pill" style="background:var(--slate-800);padding:2px 8px;border-radius:12px;font-size:10px">${e.categoria || 'Outros'}</span></td>
          <td class="${e.valor < 0 ? 'text-emerald' : 'text-rose'}">${e.valor < 0 ? 'R$' : '-R$'} ${Math.abs(e.valor).toLocaleString('pt-BR')}</td>
        </tr>
      `).join('');
    }
    
    const totalEl = document.getElementById('totalFiltro');
    if (totalEl) totalEl.innerHTML = `R$ ${total.toLocaleString('pt-BR')}`;
  }

  renderEssenciais(data) {
    const essenciais = data.custosEssenciais || { ana_lua: [], mandelinha: [] };
    
    // Sidebar Essenciais (se existir) ou no painel de planejamento
    const envelopesContainer = document.getElementById('envelopes');
    if (envelopesContainer) {
      const anaTotal = (essenciais.ana_lua || []).reduce((s, i) => s + i.valor, 0);
      const mandiTotal = (essenciais.mandelinha || []).reduce((s, i) => s + i.valor, 0);
      const limiteAna = 760;
      const limiteMandi = 200;
      
      envelopesContainer.innerHTML = `
        <div class="envelope" style="background:var(--glass-bg);border-radius:12px;padding:16px;margin-bottom:12px;border:1px solid var(--glass-border)">
          <div class="env-header" style="display:flex;justify-content:space-between;margin-bottom:8px">
            <span class="env-name" style="font-weight:600">👶 Ana Lua</span>
            <span class="env-total" style="color:var(--blue)">R$ ${anaTotal} / R$ ${limiteAna}</span>
          </div>
          <div class="env-bar" style="background:var(--slate-800);height:6px;border-radius:3px;overflow:hidden;margin-bottom:8px">
            <div class="env-fill" style="width:${Math.min(100, (anaTotal/limiteAna)*100)}%;background:var(--blue);height:100%"></div>
          </div>
          <div class="env-detail" style="font-size:11px;color:var(--text-secondary)">${(essenciais.ana_lua || []).map(i => `${i.nome}: R$ ${i.valor}`).join(' • ')}</div>
        </div>
        <div class="envelope" style="background:var(--glass-bg);border-radius:12px;padding:16px;border:1px solid var(--glass-border)">
          <div class="env-header" style="display:flex;justify-content:space-between;margin-bottom:8px">
            <span class="env-name" style="font-weight:600">🐾 Mandelinha</span>
            <span class="env-total" style="color:var(--amber)">R$ ${mandiTotal} / R$ ${limiteMandi}</span>
          </div>
          <div class="env-bar" style="background:var(--slate-800);height:6px;border-radius:3px;overflow:hidden;margin-bottom:8px">
            <div class="env-fill" style="width:${Math.min(100, (mandiTotal/limiteMandi)*100)}%;background:var(--amber);height:100%"></div>
          </div>
          <div class="env-detail" style="font-size:11px;color:var(--text-secondary)">${(essenciais.mandelinha || []).map(i => `${i.nome}: R$ ${i.valor}`).join(' • ')}</div>
        </div>
      `;
    }
  }

  renderReservaEmergencia(data) {
    const saldo = Math.max(0, data.saldoAtual || 0);
    const mediaGastoMensal = data.totalDespesas || 5000;
    const metaReserva = mediaGastoMensal * 6;
    const percent = Math.min(100, (saldo / metaReserva) * 100);
    const meses = (saldo / mediaGastoMensal).toFixed(1);
    
    const reservaAtualEl = document.getElementById('reservaAtual');
    const reservaMetaEl = document.getElementById('reservaMeta');
    const reservaProgress = document.getElementById('reservaProgress');
    const reservaMsg = document.getElementById('reservaMsg');
    
    if (reservaAtualEl) reservaAtualEl.innerHTML = `R$ ${saldo.toLocaleString('pt-BR')}`;
    if (reservaMetaEl) reservaMetaEl.innerHTML = `R$ ${metaReserva.toLocaleString('pt-BR')}`;
    if (reservaProgress) reservaProgress.style.width = `${percent}%`;
    if (reservaMsg) {
      if (saldo >= metaReserva) {
        reservaMsg.innerHTML = '🎉 Parabéns! Você atingiu sua meta de reserva de emergência!';
      } else {
        reservaMsg.innerHTML = `📌 Faltam R$ ${(metaReserva - saldo).toLocaleString('pt-BR')} para sua meta (${meses} meses de despesas)`;
      }
    }
  }

  renderVariacoes(data) {
    const evolucao = data.evolucaoMensal || [];
    if (evolucao.length >= 2) {
      const ultimo = evolucao[evolucao.length - 1];
      const anterior = evolucao[evolucao.length - 2];
      const varDespesas = ((ultimo.despesa - anterior.despesa) / anterior.despesa) * 100;
      
      const despesasVarEl = document.getElementById('despesasVariacao');
      if (despesasVarEl) {
        despesasVarEl.innerHTML = `${varDespesas <= 0 ? '↓' : '↑'} ${Math.abs(varDespesas).toFixed(1)}% vs ${anterior.mes}`;
        despesasVarEl.className = `card-footer ${varDespesas <= 0 ? 'text-emerald' : 'text-rose'}`;
      }
    }
  }

  renderReceitasDespesasFixas(data) {
    const receitasContainer = document.getElementById('receitasFixasList');
    const despesasContainer = document.getElementById('despesasFixasList');
    
    if (receitasContainer) {
      const receitas = data.receitasFixas || [];
      receitasContainer.innerHTML = receitas.map(r => `
        <div class="fix-row" style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05)">
          <span>${r.descricao}</span>
          <span style="color:var(--emerald)">R$ ${r.valor.toLocaleString('pt-BR')}</span>
        </div>
      `).join('');
    }
    
    if (despesasContainer) {
      const despesas = data.despesasRecorrentes || [];
      despesasContainer.innerHTML = despesas.map(d => `
        <div class="fix-row" style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05)">
          <span>${d.descricao}</span>
          <span style="color:var(--rose)">R$ ${d.valor.toLocaleString('pt-BR')}</span>
        </div>
      `).join('');
    }
  }

  setupMetas() {
    this.loadMetas();
    const addBtn = document.getElementById('addMetaBtn');
    if (addBtn) {
      addBtn.onclick = () => this.addMeta();
    }
  }

  loadMetas() {
    const metas = JSON.parse(localStorage.getItem('wealthaurora_metas') || '[]');
    const container = document.getElementById('metasList');
    if (!container) return;
    
    container.innerHTML = metas.map((meta, idx) => `
      <div class="meta-item" style="display:flex;justify-content:space-between;align-items:center;padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;margin-bottom:8px">
        <div class="meta-info">
          <div class="meta-nome" style="font-weight:600">${meta.nome}</div>
          <div class="meta-progresso" style="font-size:11px;color:var(--text-secondary)">Alvo: R$ ${meta.valor.toLocaleString('pt-BR')} até ${meta.data}</div>
        </div>
        <div class="meta-valor" style="color:var(--teal)">R$ ${(meta.valor / this.getMesesAteData(meta.data)).toLocaleString('pt-BR')}/mês</div>
        <button class="delete-meta" onclick="uiManager.deleteMeta(${idx})" style="background:none;border:none;color:var(--text-secondary);cursor:pointer"><i class="fas fa-trash"></i></button>
      </div>
    `).join('');
  }

  addMeta() {
    const nome = document.getElementById('novaMetaNome')?.value;
    const valor = parseFloat(document.getElementById('novaMetaValor')?.value);
    const data = document.getElementById('novaMetaData')?.value;
    
    if (!nome || !valor || !data) {
      alert('Preencha todos os campos da meta!');
      return;
    }
    
    const metas = JSON.parse(localStorage.getItem('wealthaurora_metas') || '[]');
    metas.push({ nome, valor, data });
    localStorage.setItem('wealthaurora_metas', JSON.stringify(metas));
    
    document.getElementById('novaMetaNome').value = '';
    document.getElementById('novaMetaValor').value = '';
    document.getElementById('novaMetaData').value = '';
    
    this.loadMetas();
  }

  deleteMeta(idx) {
    const metas = JSON.parse(localStorage.getItem('wealthaurora_metas') || '[]');
    metas.splice(idx, 1);
    localStorage.setItem('wealthaurora_metas', JSON.stringify(metas));
    this.loadMetas();
  }

  getMesesAteData(dataStr) {
    const hoje = new Date();
    const alvo = new Date(dataStr);
    const diffMeses = (alvo.getFullYear() - hoje.getFullYear()) * 12 + (alvo.getMonth() - hoje.getMonth());
    return Math.max(1, diffMeses);
  }

  formatMonth(monthStr) {
    const [year, month] = monthStr.split('-');
    const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${meses[parseInt(month)-1]}/${year}`;
  }
}

let uiManager;
