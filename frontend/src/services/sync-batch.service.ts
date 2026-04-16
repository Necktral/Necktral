import { api } from 'src/boot/axios';
import { buildRequestSigningMessage, canonJson, signEd25519Pkcs8 } from 'src/services/sync-device-crypto';
import {
  getActiveSyncDeviceIdentity,
  type StoredSyncDeviceIdentity,
} from 'src/services/sync-device-storage';

export type SyncV2BatchCommand = {
  command_id: string;
  type: string;
  scope: {
    company_id: number;
    branch_id?: number | null;
  };
  occurred_at: string;
  payload: Record<string, unknown>;
  payload_hash?: string;
  sequence?: number | null;
  prev_hash?: string;
  command_sig?: string;
};

export type SyncV2BatchResponse = {
  batch_id: string;
  device_id: string;
  device_status: string;
  summary: {
    received: number;
    applied: number;
    rejected: number;
    duplicate: number;
  };
  results: Array<{
    command_id: string;
    status: 'APPLIED' | 'REJECTED' | 'DUPLICATE';
    reason?: string;
    refs?: Record<string, unknown>;
  }>;
  trace?: {
    request_id?: string;
    channel?: string;
  };
};

function randomUuid(): string {
  const g = globalThis as unknown as { crypto?: { randomUUID?: () => string } };
  if (g.crypto?.randomUUID) return g.crypto.randomUUID();

  // Fallback RFC4122 v4 para entornos sin crypto.randomUUID.
  let d = Date.now();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (d + Math.random() * 16) % 16 | 0;
    d = Math.floor(d / 16);
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function nowUnixSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

function randomNonce(): string {
  const raw = randomUuid().replace(/-/g, '');
  return `inv-${raw.slice(0, 24)}`;
}

export async function submitSyncV2Batch(options: {
  commands: SyncV2BatchCommand[];
  deviceIdentity?: StoredSyncDeviceIdentity | null;
}): Promise<SyncV2BatchResponse> {
  const identity = options.deviceIdentity ?? (await getActiveSyncDeviceIdentity());
  if (!identity) {
    throw new Error('No hay dispositivo enrolado para sincronización offline.');
  }

  const ts = nowUnixSeconds();
  const nonce = randomNonce();
  const payload = {
    protocol_version: '2',
    device_id: identity.deviceId,
    ts,
    nonce,
    auth: { scheme: 'ed25519', signature: '' },
    batch_id: randomUuid(),
    batch: options.commands,
  };

  const canonicalBodyPayload = JSON.parse(JSON.stringify(payload)) as Parameters<typeof canonJson>[0];
  const canonicalBody = new TextEncoder().encode(canonJson(canonicalBodyPayload));
  const message = await buildRequestSigningMessage({
    ts,
    nonce,
    canonicalBodyBytes: canonicalBody,
  });
  payload.auth.signature = await signEd25519Pkcs8(identity.privateKeyPkcs8B64, message);

  const { data } = await api.post<SyncV2BatchResponse>('/sync/batch/', payload, {
    headers: { 'X-Device-Id': identity.deviceId },
  });
  return data;
}
