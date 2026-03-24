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
  workspace_code?: string;
  widget_code?: string;
  warnings?: string[];
};

export type DashboardEnvelope<TSummary, TResult> = {
  meta: DashboardMeta;
  summary: TSummary;
  results: TResult;
  pagination: Record<string, number>;
};

export type DashboardCatalogEntry = {
  workspace_code: string;
  title: string;
  description: string;
  widget_count: number;
  intercompany_enabled: boolean;
  widgets: string[];
};

export type DashboardWorkspaceWidget = {
  widget_code: string;
  title: string;
  report_code: string;
  domain: string;
  visual: string;
  description: string;
  default_metrics: string[];
  default_group_by: string[];
  allowed_drill_paths: string[];
};

export type DashboardWorkspace = {
  workspace_code: string;
  title: string;
  description: string;
  intercompany_enabled: boolean;
  widgets: DashboardWorkspaceWidget[];
};

export type DashboardQueryParams = {
  widget_code?: string;
  filters?: Record<string, unknown>;
  group_by?: string[];
  metrics?: string[];
  sort?: Array<Record<string, unknown>>;
  cursor?: Record<string, unknown> | string;
  comparison?: Record<string, unknown>;
  drill_path?: string[];
  time_window?: Record<string, unknown>;
  run_async?: boolean;
  use_cache?: boolean;
  company_ids?: number[];
  branch_id?: number | null;
};

export type DashboardQueryWidgetResult = {
  workspace_code: string;
  widget_code: string;
  widget_title: string;
  visual: string;
  domain: string;
  report_code: string;
  company_id: number;
  branch_id: number | null;
  execution_id: string;
  status: string;
  row_count: number;
  duration_ms: number;
  warnings: string[];
  meta: Record<string, unknown>;
  rows: Array<Record<string, unknown>>;
};

export type DashboardQueryResult = {
  widgets: DashboardQueryWidgetResult[];
  query: {
    filters: Record<string, unknown>;
    group_by: string[];
    metrics: string[];
    sort: Array<Record<string, unknown>>;
    comparison: Record<string, unknown>;
    drill_path: string[];
  };
};

export type DashboardDrilldownResult = {
  drilldown: DashboardQueryWidgetResult[];
};

export type DashboardCatalogResponse = DashboardEnvelope<
  { workspace_count: number },
  DashboardCatalogEntry[]
>;

export type DashboardWorkspaceResponse = DashboardEnvelope<
  { workspace_code: string; title: string; widget_count: number },
  DashboardWorkspace
>;

export type DashboardQueryResponse = DashboardEnvelope<
  {
    workspace_code: string;
    workspace_title: string;
    widget_count: number;
    execution_count: number;
    intercompany_requested: boolean;
    company_count: number;
  },
  DashboardQueryResult
>;

export type DashboardDrilldownResponse = DashboardEnvelope<
  {
    workspace_code: string;
    widget_code: string;
    drill_path: string[];
    execution_count: number;
    intercompany_requested: boolean;
  },
  DashboardDrilldownResult
>;

export type DashboardEmbedTokenPayload = {
  workspace_code: string;
  company_ids?: number[];
  branch_id?: number | null;
  theme?: string;
  locale?: string;
  ttl_seconds?: number;
};

export type DashboardEmbedTokenResult = {
  workspace_code: string;
  token_type: string;
  token: string;
  issued_at: string;
  expires_at: string;
  ttl_seconds: number;
  embed_url: string;
  scope: DashboardScope;
  targets: Array<{ company_id: number; branch_id: number | null }>;
};

export type DashboardEmbedTokenResponse = DashboardEnvelope<
  { workspace_code: string; ttl_seconds: number },
  DashboardEmbedTokenResult
>;
