/**
 * WealthAurora - Main Entry Point
 * Inicializa todos os módulos e orquestra o carregamento
 */

// Variáveis globais
window.dataService = dataService;
window.filterByCategory = function(categoria) {
  const tabBtn = document.querySelector('.tab-btn[data-tab="extrato"]');
  if (tabBtn) tabBtn.click();
  const filtroCategoria = document.getElementById('filtroCategoria');
  if (filtroCategoria) {
    filtroCategoria.value = categoria;
    filtroCategoria.dispatchEvent(new Event('change'));
  }
};

// Inicialização completa
document.addEventListener('DOMContentLoaded', async () => {
  // Mostrar loading
  const loadingEl = document.getElementById('loadingState');
  const dashboardEl = document.getElementById('dashboardContent');
  const emptyStateEl = document.getElementById('emptyState');
  
  if (loadingEl) loadingEl.classList.remove('hidden');
  if (dashboardEl) dashboardEl.classList.add('hidden');
  if (emptyStateEl) emptyStateEl.classList.add('hidden');
  
  try {
    // Carregar dados primeiro
    const data = await dataService.fetchData();
    
    // Inicializar módulos sequencialmente
    chartsManager = new ChartsManager(dataService);
    insightsManager = new InsightsManager(dataService);
    debtManager = new DebtManager(dataService);
    uiManager = new UIManager(dataService);
    
    await Promise.all([
      chartsManager.init(),
      insightsManager.init(),
      debtManager.init(),
      uiManager.init()
    ]);
    
    // Esconder loading, mostrar dashboard
    if (loadingEl) loadingEl.classList.add('hidden');
    if (dashboardEl) dashboardEl.classList.remove('hidden');
    
    // Atualizar data/hora
    if (uiManager) uiManager.updateLastUpdateTime();
    
    console.log('✅ WealthAurora inicializado com sucesso!');
  } catch (error) {
    console.error('❌ Erro na inicialização:', error);
    if (loadingEl) {
      loadingEl.innerHTML = `
        <div style="text-align:center;padding:40px">
          <i class="fas fa-exclamation-triangle" style="font-size:48px;color:var(--amber);margin-bottom:16px;display:block"></i>
          <p style="color:var(--red)">Erro ao carregar o dashboard</p>
          <p style="font-size:12px;color:var(--text-secondary);margin-top:8px">${error.message}</p>
          <button onclick="location.reload()" class="btn-primary" style="margin-top:20px">Tentar novamente</button>
        </div>
      `;
    }
  }
});

// Recarregar dados a cada 5 minutos
setInterval(async () => {
  if (dataService) {
    const newData = await dataService.fetchData(true);
    if (chartsManager) chartsManager.renderAll(newData);
    if (insightsManager) {
      insightsManager.generateInsights(newData);
      insightsManager.calculateHealthScore(newData);
    }
    if (debtManager) debtManager.render(newData);
    if (uiManager) {
      uiManager.renderEssenciais(newData);
      uiManager.renderReservaEmergencia(newData);
      uiManager.renderVariacoes(newData);
      uiManager.updateMainCards(newData);
      uiManager.updateLastUpdateTime();
    }
  }
}, 5 * 60 * 1000);
