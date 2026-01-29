import nacl from 'tweetnacl';

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i] as number);
  }
  return btoa(binary);
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) {
    out[i] = bin.charCodeAt(i);
  }
  return out;
}

export function canonJson(obj: unknown): string {
  // Emula python json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)
  const t = typeof obj;
  if (obj === null || t === 'number' || t === 'boolean' || t === 'string') {
    return JSON.stringify(obj);
  }

  if (Array.isArray(obj)) {
    return `[${obj.map((x) => canonJson(x)).join(',')}]`;
  }

  if (t === 'object') {
    const rec = obj as Record<string, unknown>;
    const keys = Object.keys(rec).sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonJson(rec[k])}`).join(',')}}`;
  }

  // undefined / function / symbol no son JSON: los normalizamos a null
  return 'null';
}

export async function sha256Hex(input: string): Promise<string> {
  const enc = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-256', enc);
  const bytes = new Uint8Array(digest);
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export function occurredAtCanonical(date: Date): string {
  // Canonical a UTC con microsegundos (6 dígitos), siguiendo apps/sync_engine/signing.py
  const pad2 = (n: number) => String(n).padStart(2, '0');
  const pad3 = (n: number) => String(n).padStart(3, '0');

  const y = date.getUTCFullYear();
  const m = pad2(date.getUTCMonth() + 1);
  const d = pad2(date.getUTCDate());
  const hh = pad2(date.getUTCHours());
  const mm = pad2(date.getUTCMinutes());
  const ss = pad2(date.getUTCSeconds());
  const ms = pad3(date.getUTCMilliseconds());
  const micros = `${ms}000`;

  return `${y}-${m}-${d}T${hh}:${mm}:${ss}.${micros}Z`;
}

export function buildCommandSigningMessage(input: {
  command_id: string;
  command_type: string;
  company_id: number;
  branch_id: number | null;
  occurred_at: string;
  sequence: number | null;
  payload_hash: string;
  prev_hash: string;
}): Uint8Array {
  const b = input.branch_id == null ? '' : String(input.branch_id);
  const s = input.sequence == null ? '' : String(input.sequence);
  const msg = `${input.command_id}|${input.command_type}|${input.company_id}|${b}|${input.occurred_at}|${s}|${input.payload_hash}|${input.prev_hash}`;
  return new TextEncoder().encode(msg);
}

export function generateEd25519Keypair(): { publicKeyB64: string; secretKeyB64: string } {
  const kp = nacl.sign.keyPair();
  return {
    publicKeyB64: bytesToBase64(kp.publicKey),
    secretKeyB64: bytesToBase64(kp.secretKey),
  };
}

export function signEd25519Detached(params: { secretKeyB64: string; message: Uint8Array }): string {
  const sk = base64ToBytes(params.secretKeyB64);
  const sig = nacl.sign.detached(params.message, sk);
  return bytesToBase64(sig);
}
