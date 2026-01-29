import { STORAGE_KEYS } from './keys';

export type StoredSyncDevice = {
  deviceId: string | null;
  publicKeyB64: string | null;
  secretKeyB64: string | null;
  companyId: string | null;
  branchId: string | null;
  lastSequence: number;
};

export function readSyncDevice(): StoredSyncDevice {
  const last = Number(localStorage.getItem(STORAGE_KEYS.SYNC_LAST_SEQUENCE) || '0');
  return {
    deviceId: localStorage.getItem(STORAGE_KEYS.SYNC_DEVICE_ID),
    publicKeyB64: localStorage.getItem(STORAGE_KEYS.SYNC_PUBLIC_KEY_B64),
    secretKeyB64: localStorage.getItem(STORAGE_KEYS.SYNC_SECRET_KEY_B64),
    companyId: localStorage.getItem(STORAGE_KEYS.SYNC_COMPANY_ID),
    branchId: localStorage.getItem(STORAGE_KEYS.SYNC_BRANCH_ID),
    lastSequence: Number.isFinite(last) ? last : 0,
  };
}

export function writeSyncDevice(data: {
  deviceId: string;
  publicKeyB64: string;
  secretKeyB64: string;
  companyId: string;
  branchId: string | null;
  lastSequence?: number;
}) {
  localStorage.setItem(STORAGE_KEYS.SYNC_DEVICE_ID, data.deviceId);
  localStorage.setItem(STORAGE_KEYS.SYNC_PUBLIC_KEY_B64, data.publicKeyB64);
  localStorage.setItem(STORAGE_KEYS.SYNC_SECRET_KEY_B64, data.secretKeyB64);
  localStorage.setItem(STORAGE_KEYS.SYNC_COMPANY_ID, data.companyId);
  if (data.branchId) localStorage.setItem(STORAGE_KEYS.SYNC_BRANCH_ID, data.branchId);
  else localStorage.removeItem(STORAGE_KEYS.SYNC_BRANCH_ID);
  if (typeof data.lastSequence === 'number') {
    localStorage.setItem(STORAGE_KEYS.SYNC_LAST_SEQUENCE, String(data.lastSequence));
  }
}

export function writeSyncLastSequence(seq: number) {
  localStorage.setItem(STORAGE_KEYS.SYNC_LAST_SEQUENCE, String(seq));
}

export function clearSyncDevice() {
  localStorage.removeItem(STORAGE_KEYS.SYNC_DEVICE_ID);
  localStorage.removeItem(STORAGE_KEYS.SYNC_PUBLIC_KEY_B64);
  localStorage.removeItem(STORAGE_KEYS.SYNC_SECRET_KEY_B64);
  localStorage.removeItem(STORAGE_KEYS.SYNC_COMPANY_ID);
  localStorage.removeItem(STORAGE_KEYS.SYNC_BRANCH_ID);
  localStorage.removeItem(STORAGE_KEYS.SYNC_LAST_SEQUENCE);
}
