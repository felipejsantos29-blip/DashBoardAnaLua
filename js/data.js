/**
 * WealthAurora - Módulo de Dados
 * Responsável por buscar, cachear e processar dados da planilha
 */

const MOCK_DATA = {
  saldoAtual: 4230.50,
  totalReceitas: 7000.00,
  totalDespesas: 5840.00,
  taxaEsforco: 83.4,
  mediaDiaria: 194.67,
  reservaEmergencia: 8500,
  capPoupanca: 18.5,
  diasReserva: 22,
  scoreFinanceiro: 65,
  variacaoGastoMes: -5.2,
  
  categorias: [
    { nome: "Alimentação", gasto: 1240, limite: 1400 },
    { nome: "Transporte", gasto: 620, limite: 600 },
    { nome: "Lazer", gasto: 480, limite: 550 },
    { nome: "Saúde", gasto: 310, limite: 400 },
    { nome: "Ana Lua", gasto: 680, limite: 760 },
    { nome: "Mandelinha", gasto: 190, limite: 200 },
    { nome: "Casa", gasto: 1200, limite: 1200 },
    { nome: "Outros", gasto: 320, limite: 400 }
  ],
  
  evolucaoMensal: [
    { mes: "Jan", receita: 6800, despesa: 5200 },
    { mes: "Fev", receita: 6800, despesa: 5600 },
    { mes: "Mar", receita: 7200, despesa: 6100 },
    { mes: "Abr", receita: 7000, despesa: 5400 },
    { mes: "Mai", receita: 7000, despesa: 5840 }
  ],
  
  extrato: [],
  
  emprestimo: {
    nomeCredor: "Cirlene",
    valorOriginal: 35000,
    parcelasPagas: 0,
    totalParcelas: 30,
    parcelaMensal: 500,
    extraSemestral: 4000,
    saldoDevedor: 35000
  },
  
  receitasFixas: [
    { descricao: "Salário Principal", valor: 1761.48, dia: 15 },
    { descricao: "Salário Complementar", valor: 1699.34, dia: 15 },
    { descricao: "Salário Variável", valor: 1819.33, dia: 30 }
  ],
  
  despesasRecorrentes: [
    { descricao: "Faculdade", valor: 328.67, dia: 24 },
    { descricao: "Claro Flex", valor: 39.99, dia: 22 },
    { descricao: "Spotify", valor: 40.90, dia: 10 }
  ],
  
  custosEssenciais: {
    ana_lua: [
      { nome: "Leite Nan", valor: 280 },
      { nome: "Pomada", valor: 40 },
      { nome: "Lenço umedecido", valor: 60 },
      { nome: "Farmácia", valor: 150 },
      { nome: "Comida (papinha)", valor: 50 }
    ],
    mandelinha: [
      { nome: "Fralda pet", valor: 120 },
      { nome: "Plano Pet Love", valor: 59 }
    ]
  },
  
  limitesSugeridos: {
    "Alimentação": 1400,
    "Transporte": 600,
    "Saúde": 400,
    "Lazer": 550,
    "Educação": 500,
    "Pet": 200,
    "Compras": 400,
    "Serviços": 300
  },
  
  gastosPorCategoria: {},
  gastosMensais: {},
  receitasMensais: {},
  rankingCategoria: [],
  alertas: []
};

const CACHE_KEY = 'wealthaurora_data';
const CACHE_EXPIRY = 5 * 60 * 1000;

class DataService {
  constructor() {
    this.data = null;
    this.listeners = [];
  }

  onDataLoaded(callback) {
    this.listeners.push(callback);
  }

  notifyListeners() {
    this.listeners.forEach(cb => cb(this.data));
  }

  getCachedData() {
    const cached = sessionStorage.getItem(CACHE_KEY);
    if (cached) {
      const { data, timestamp } = JSON.parse(cached);
      if (Date.now() - timestamp < CACHE_EXPIRY) return data;
    }
    return null;
  }

  setCachedData(data) {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ data, timestamp: Date.now() }));
  }

  async fetchData(forceRefresh = false) {
    if (!forceRefresh) {
      const cached = this.getCachedData();
      if (cached) {
        this.data = cached;
        this.notifyListeners();
        return cached;
      }
    }

    try {
      const response = await fetch('data.json?v=' + Date.now());
      if (response.ok) {
        const json = await response.json();
        this.data = this.transformData(json);
        this.setCachedData(this.data);
        this.notifyListeners();
        return this.data;
      }
      throw new Error('API não disponível');
    } catch (error) {
      console.warn('Usando dados mock:', error);
      this.data = MOCK_DATA;
      this.notifyListeners();
      return this.data;
    }
  }

  transformData(apiData) {
    const categorias = [];
    const gastosPorCategoria = apiData.gastosPorCategoria || {};
    const limites = apiData.limitesSugeridos || MOCK_DATA.limitesSugeridos;
    
    for (const [nome, gasto] of Object.entries(gastosPorCategoria)) {
      categorias.push({ nome, gasto, limite: limites[nome] || gasto * 1.2 });
    }

    return {
      saldoAtual: apiData.saldoTotal || MOCK_DATA.saldoAtual,
      totalReceitas: apiData.totalReceitas || MOCK_DATA.totalReceitas,
      totalDespesas: apiData.totalGastos || MOCK_DATA.totalDespesas,
      taxaEsforco: apiData.taxaEsforco || MOCK_DATA.taxaEsforco,
      mediaDiaria: apiData.mediaDiaria || MOCK_DATA.mediaDiaria,
      reservaEmergencia: MOCK_DATA.reservaEmergencia,
      capPoupanca: apiData.capPoupanca || MOCK_DATA.capPoupanca,
      diasReserva: apiData.diasReserva || MOCK_DATA.diasReserva,
      scoreFinanceiro: apiData.scoreFinanceiro || MOCK_DATA.scoreFinanceiro,
      variacaoGastoMes: apiData.variacaoGastoMes || MOCK_DATA.variacaoGastoMes,
      categorias,
      evolucaoMensal: this.buildEvolucaoMensal(apiData),
      extrato: apiData.extrato || [],
      emprestimo: apiData.debt || MOCK_DATA.emprestimo,
      receitasFixas: apiData.receitasFixas || MOCK_DATA.receitasFixas,
      despesasRecorrentes: apiData.despesasRecorrentes || MOCK_DATA.despesasRecorrentes,
      custosEssenciais: apiData.custosEssenciais || MOCK_DATA.custosEssenciais,
      limitesSugeridos: limites,
      gastosPorCategoria,
      gastosMensais: apiData.gastosMensais || {},
      receitasMensais: apiData.receitasMensais || {},
      rankingCategoria: apiData.rankingCategoria || [],
      alertas: apiData.alertas || []
    };
  }

  buildEvolucaoMensal(apiData) {
    const gastos = apiData.gastosMensais || {};
    const receitas = apiData.receitasMensais || {};
    const meses = [...new Set([...Object.keys(gastos), ...Object.keys(receitas)])].sort().slice(-6);
    return meses.map(mes => ({
      mes: this.formatMonth(mes),
      despesa: gastos[mes] || 0,
      receita: receitas[mes] || 0
    }));
  }

  formatMonth(monthStr) {
    const [year, month] = monthStr.split('-');
    const meses = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${meses[parseInt(month)-1]}/${year.slice(2)}`;
  }
}

const dataService = new DataService();
