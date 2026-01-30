import type { AxiosInstance } from 'axios';

import { readContext } from 'src/core/storage/context';
import { readSyncDevice, writeSyncDevice } from 'src/core/storage/sync_device';

import { generateEd25519Keypair } from './signing';

export type EnrollResult = {
  device_id: string;
  device_status: string;
  company_id: number;
  branch_id: number | null;
  server_time?: string;
  policy?: {
    max_commands_per_batch: number;
    max_payload_bytes: number;
    max_device_clock_skew_seconds: number;
    seq_tolerant: boolean;
  };
};

export function getSyncDeviceOrNull() {
  const d = readSyncDevice();
  if (!d.deviceId || !d.secretKeyB64 || !d.publicKeyB64) return null;
  return d;
}

export function assertSyncDeviceForActiveContext() {
  const ctx = readContext();
  const d = getSyncDeviceOrNull();
  if (!d) {
    throw new Error('SyncDeviceNotEnrolled: missing device_id/keys');
  }
  if (d.companyId && ctx.companyId && d.companyId !== ctx.companyId) {
    throw new Error(
      `SyncDeviceScopeMismatch: device.company=${d.companyId} ctx.company=${ctx.companyId}`,
    );
  }
  if (d.branchId && ctx.branchId && d.branchId !== ctx.branchId) {
    throw new Error(
      `SyncDeviceScopeMismatch: device.branch=${d.branchId} ctx.branch=${ctx.branchId}`,
    );
  }
  return d;
}

export async function enrollSyncDevice(
  api: AxiosInstance,
  input: { enrollmentCode: string; label?: string },
) {
  const ctx = readContext();
  if (!ctx.companyId) {
    throw new Error('ContextMissing: X-Company-Id is required to enroll device');
  }

  const kp = generateEd25519Keypair();

  const { data } = await api.post<EnrollResult>('/sync/enroll/', {
    enrollment_code: input.enrollmentCode,
    public_key_b64: kp.publicKeyB64,
    label: input.label ?? '',
  });

  writeSyncDevice({
    deviceId: data.device_id,
    publicKeyB64: kp.publicKeyB64,
    secretKeyB64: kp.secretKeyB64,
    companyId: String(data.company_id),
    branchId: data.branch_id == null ? null : String(data.branch_id),
    lastSequence: 0,
  });

  return data;
}
