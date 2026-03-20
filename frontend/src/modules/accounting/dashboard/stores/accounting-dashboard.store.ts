import { defineStore } from 'pinia';

import {
  fetchBranchPerformance,
  fetchCashPosition,
  fetchExecutiveSummary,
  fetchMonthlyTrends,
  fetchReconciliationHealth,
  fetchRevenueVsExpense,
} from '../services/dashboard.service';
import type {
  BranchPerformanceData,
  CashPositionData,
  DashboardQuery,
  ExecutiveSummaryData,
  MonthlyTrendsData,
  ReconciliationHealthData,
  RevenueVsExpenseData,
} from '../types';

export const useAccountingDashboardStore = defineStore('accounting-dashboard', {
  state: () => ({
    loading: false as boolean,
    loaded: false as boolean,
    error: null as string | null,
    executiveSummary: null as ExecutiveSummaryData | null,
    revenueVsExpense: null as RevenueVsExpenseData | null,
    cashPosition: null as CashPositionData | null,
    reconciliationHealth: null as ReconciliationHealthData | null,
    branchPerformance: null as BranchPerformanceData | null,
    monthlyTrends: null as MonthlyTrendsData | null,
  }),

  actions: {
    async load(params?: DashboardQuery) {
      this.loading = true;
      this.error = null;
      try {
        const [executiveSummary, revenueVsExpense, cashPosition, reconciliationHealth, branchPerformance, monthlyTrends] =
          await Promise.all([
            fetchExecutiveSummary(params),
            fetchRevenueVsExpense(params),
            fetchCashPosition(params),
            fetchReconciliationHealth(params),
            fetchBranchPerformance(params),
            fetchMonthlyTrends(params),
          ]);

        this.executiveSummary = executiveSummary;
        this.revenueVsExpense = revenueVsExpense;
        this.cashPosition = cashPosition;
        this.reconciliationHealth = reconciliationHealth;
        this.branchPerformance = branchPerformance;
        this.monthlyTrends = monthlyTrends;
        this.loaded = true;
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo cargar el tablero contable.';
      } finally {
        this.loading = false;
      }
    },
  },
});

