export type DashboardScope = {
  company_id: number | null;
  branch_id: number | null;
};

export type DashboardMeta = {
  contract_version: string;
  report_code: string;
  generated_at: string;
  scope: DashboardScope;
  cache_hit?: boolean;
  cache_ttl_seconds?: number;
};

export type DashboardEnvelope<TSummary, TResult> = {
  meta: DashboardMeta;
  summary: TSummary;
  results: TResult;
  pagination: Record<string, number>;
};

export type DashboardQuery = {
  year?: number;
  month?: number;
  dateFrom?: string;
  dateTo?: string;
  asOf?: string;
  months?: number;
  refresh?: boolean;
};

export type ExecutiveSummaryData = DashboardEnvelope<
  {
    period: { date_from: string; date_to: string };
    revenue: string;
    expense: string;
    net_income: string;
    assets: string;
    liabilities_plus_equity: string;
  },
  {
    pnl_totals: Record<string, string>;
    balance_sheet_totals: Record<string, string>;
  }
>;

export type RevenueVsExpenseData = DashboardEnvelope<
  {
    period: { date_from: string; date_to: string };
  },
  Array<{ metric: string; value: string }>
>;

export type CashPositionData = DashboardEnvelope<
  {
    as_of: string;
    total_cash_position: string;
  },
  {
    cash_on_hand: string;
    bank_accounts: string;
    total: string;
  }
>;

export type ReconciliationHealthData = DashboardEnvelope<
  {
    period: { date_from: string; date_to: string };
    operational_events: number;
    linked_events: number;
    pending_events: number;
    linkage_ratio: number;
  },
  {
    by_event_type: Array<Record<string, unknown>>;
  }
>;

export type BranchPerformanceData = DashboardEnvelope<
  {
    period: { date_from: string; date_to: string };
    branches: number;
    entries: number;
  },
  Array<{ branch_id: number | null; entries: number; debit_total: string; credit_total: string }>
>;

export type MonthlyTrendsData = DashboardEnvelope<
  {
    months: number;
    as_of: string;
  },
  Array<{ year: number; month: number; revenue: string; expense: string; net_income: string }>
>;

