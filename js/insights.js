/**
 * WealthAurora - Módulo de Insights Automáticos
 */

class InsightsManager {
  constructor(dataService) {
    this.dataService = dataService;
  }

  async init() {
    const data = await this.dataService.fetchData();
    this.generateInsights(data);
    this.calculateHealthScore(data);
    
    this.dataService.onDataLoaded((newData) => {
      this.generateInsights(newData);
      this.calculateHealthScore(newData);
    });
  }

  generateInsights(data) {
    const container = document.getElementById('insightText');
    if (!container) return;

    const insights = [];
    const categorias = data.categorias || [];
    const evolucao = data.evolucaoMensal || [];

    if (evolucao.length >= 2) {
      const ultimo = evolucao[evolucao.length - 1];
      const anterior = evolucao[evolucao.length - 2];
      const variacao = ((ultimo.despesa - anterior.despesa) / anterior.despesa) * 100;
      
      if (variacao < -5) {
        insights.push(`📉 Gastos ${Math.abs(variacao).toFixed(1)}% menores que o mês passado! Continue assim!`);
      } else if (variacao > 10) {
        insights
