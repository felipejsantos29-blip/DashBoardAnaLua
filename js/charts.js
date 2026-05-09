/**
 * WealthAurora - Módulo de Gráficos
 */

class ChartsManager {
  constructor(dataService) {
    this.dataService = dataService;
    this.charts = {};
  }

  async init() {
    const data = await this.dataService.fetchData();
    this.renderAll(data);
    
    this.dataService.onDataLoaded((newData) => {
      this.renderAll(newData);
    });
  }

  renderAll(data) {
    this.renderMonthlyChart(data);
    this.renderCategoryChart(data);
    this.renderLimitsList(data);
  }

  renderMonthlyChart(data) {
    const ctx = document.getElementById('monthlyChart')?.getContext('2d');
    if (!ctx) return;

    if (this.charts.monthly) this.charts.monthly.destroy();

    const evolucao = data.evolucaoMensal || [];
    this.charts.monthly = new Chart(ctx, {
      type: 'line',
      data: {
        labels: evolucao.map(e => e.mes),
        datasets: [
          { label: 'Receitas', data: evolucao.map(e => e.receita), borderColor: '#34D399', backgroundColor: 'rgba(52,211,153,0.1)', fill: true, tension: 0.3 },
          { label: 'Despesas', data: evolucao.map(e => e.despesa), borderColor: '#FB7185', backgroundColor: 'rgba(251,113,133,0.1)', fill: true, tension: 0.3 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: { legend: { labels: { color: '#94A3B8' } } },
        scales: { y: { ticks: { color: '#94A3B8', callback: v => 'R$ ' + v.toLocaleString('pt-BR') } }, x: { ticks: { color: '#94A3B8' } } }
      }
    });
  }

  renderCategoryChart(data) {
    const ctx = document.getElementById('categoryChart')?.getContext('2d');
    if (!ctx) return;

    if (this.charts.category) this.charts.category.destroy();

    const categorias = data.categorias || [];
    const cores = ['#2DD4BF', '#FB7185', '#FBBF24', '#34D399', '#A78BFA', '#F97316', '#06B6D4', '#64748B'];
    
    this.charts.category = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: categorias.map(c => c.nome),
        datasets: [{ data: categorias.map(c => c.gasto), backgroundColor: cores, borderWidth: 0 }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: { legend: { position: 'bottom', labels: { color: '#94A3B8', font: { size: 10 } } } }
      }
    });

    const legend = document.getElementById('categoryLegend');
    if (legend) {
      legend.innerHTML = categorias.map((c, i) => `
        <div class="category-legend-item" onclick="filterByCategory('${c.nome}')">
          <span style="width:10px;height:10px;border-radius:2px;background:${cores[i % cores.length]};display:inline-block"></span>
          <span style="flex:1">${c.nome}</span>
          <span>R$ ${c.gasto.toLocaleString('pt-BR')}</span>
        </div>
      `).join('');
    }
  }

  renderLimitsList(data) {
    const container = document.getElementById('limitesList');
    if (!container) return;

    const categorias = data.categorias || [];
    
    container.innerHTML = categorias.map(cat => {
      const percent = (cat.gasto / cat.limite) * 100;
      let statusClass = 'green';
      let badge = '';
      
      if (percent >= 100) {
        statusClass = 'red';
        badge = '<span class="limit-badge danger ml-2">🔴 Estourado</span>';
      } else if (percent >= 80) {
        statusClass = 'yellow';
        badge = '<span class="limit-badge warning ml-2">⚠️ Alerta</span>';
      }
      
      return `
        <div class="limit-item">
          <div class="limit-header">
            <span>${cat.nome}</span>
            <span>R$ ${cat.gasto.toLocaleString('pt-BR')} / R$ ${cat.limite.toLocaleString('pt-BR')} ${badge}</span>
          </div>
          <div class="limit-bar-bg">
            <div class="limit-bar-fill ${statusClass}" style="width: ${Math.min(100, percent)}%"></div>
          </div>
        </div>
      `;
    }).join('');
  }
}

let chartsManager;
