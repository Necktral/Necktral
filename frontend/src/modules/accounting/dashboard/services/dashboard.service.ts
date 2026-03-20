import { api } from 'src/boot/axios';

import type {
  BranchPerformanceData,
  CashPositionData,
  DashboardQuery,
  ExecutiveSummaryData,
  MonthlyTrendsData,
  ReconciliationHealthData,
  RevenueVsExpenseData,
} from '../types';

function queryParams(input?: DashboardQuery): Record<string, string | number | boolean> {
  if (!input) return {};
  const params: Record<string, string | number | boolean> = {};
  if (typeof input.year === 'number') params.year = input.year;
  if (typeof input.month === 'number') params.month = input.month;
  if (typeof input.dateFrom === 'string' && input.dateFrom) params.date_from = input.dateFrom;
  if (typeof input.dateTo === 'string' && input.dateTo) params.date_to = input.dateTo;
  if (typeof input.asOf === 'string' && input.asOf) params.as_of = input.asOf;
  if (typeof input.months === 'number') params.months = input.months;
  if (typeof input.refresh === 'boolean') params.refresh = input.refresh;
  return params;
}

export async function fetchExecutiveSummary(params?: DashboardQuery): Promise<ExecutiveSummaryData> {
  const { data } = await api.get<ExecutiveSummaryData>('/backend/accounting/dashboard/executive-summary/', {
    params: queryParams(params),
  });
  return data;
}

export async function fetchRevenueVsExpense(params?: DashboardQuery): Promise<RevenueVsExpenseData> {
  const { data } = await api.get<RevenueVsExpenseData>('/backend/accounting/dashboard/revenue-vs-expense/', {
    params: queryParams(params),
  });
  return data;
}

export async function fetchCashPosition(params?: DashboardQuery): Promise<CashPositionData> {
  const { data } = await api.get<CashPositionData>('/backend/accounting/dashboard/cash-position/', {
    params: queryParams(params),
  });
  return data;
}

export async function fetchReconciliationHealth(params?: DashboardQuery): Promise<ReconciliationHealthData> {
  const { data } = await api.get<ReconciliationHealthData>('/backend/accounting/dashboard/reconciliation-health/', {
    params: queryParams(params),
  });
  return data;
}

export async function fetchBranchPerformance(params?: DashboardQuery): Promise<BranchPerformanceData> {
  const { data } = await api.get<BranchPerformanceData>('/backend/accounting/dashboard/branch-performance/', {
    params: queryParams(params),
  });
  return data;
}

export async function fetchMonthlyTrends(params?: DashboardQuery): Promise<MonthlyTrendsData> {
  const { data } = await api.get<MonthlyTrendsData>('/backend/accounting/dashboard/monthly-trends/', {
    params: queryParams(params),
  });
  return data;
}

