import { api } from 'src/boot/axios';

export type CursorPage<T> = {
  next: string | null;
  previous: string | null;
  results: T[];
};

// Nota: el backend usa `event_id` (UUID) como identificador.
export type AuditEventRow = {
  event_id: string;
  schema_version: number;

  module: string | null;
  event_type: string;
  reason_code: string | null;

  partition_key: string;
  timestamp_server: string;

  actor_user: number | null;
  device_id: string | null;
  ip_server_seen: string | null;
  offline_mode: boolean;

  path: string;
  method: string;

  subject_type: string | null;
  subject_id: string | null;

  metadata?: Record<string, unknown>;
};

export type AuditEventDetail = {
  event_id: string;
  schema_version?: number;

  module: string | null;
  event_type: string;
  reason_code: string | null;

  timestamp_server: string;

  actor_user: number | null;
  device_id: string | null;
  ip_server_seen: string | null;
  offline_mode: boolean;

  path: string;
  method: string;

  subject_type: string | null;
  subject_id: string | null;

  metadata?: Record<string, unknown>;
  integrity?: Record<string, unknown>;
};

export type AuditListParams = {
  cursor?: string;

  // filtros (mapea 1:1 a query params del backend)
  event_type?: string;
  reason_code?: string;
  module?: string;
  method?: string;

  actor_user_id?: number | string;
  subject_type?: string;
  subject_id?: string;

  device_id?: string;
  ip?: string;
  path_contains?: string;

  offline_mode?: boolean;

  // rango de fechas (ISO o YYYY-MM-DD)
  after?: string;
  before?: string;

  // tuning
  page_size?: number;

  // si quieres que devuelva info extra en la lista
  include_integrity?: boolean;
};

export async function listAuditEvents(params: AuditListParams = {}) {
  const { data } = await api.get<CursorPage<AuditEventRow>>('/audit/bitacora/', { params });
  return data;
}

export async function getAuditEvent(eventId: string) {
  const { data } = await api.get<AuditEventDetail>(`/audit/events/${eventId}/`);
  return data;
}
