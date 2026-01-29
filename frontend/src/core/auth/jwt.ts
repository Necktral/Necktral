export type JwtPayload = Record<string, unknown>;

function base64UrlDecode(input: string): string {
  const normalized = input.replace(/-/g, '+').replace(/_/g, '/');
  const pad = normalized.length % 4 === 0 ? '' : '='.repeat(4 - (normalized.length % 4));
  const b64 = normalized + pad;
  // atob maneja base64 estándar
  return atob(b64);
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split('.');
    if (parts.length < 2) return null;
    const payloadPart = parts[1];
    if (!payloadPart) return null;
    const json = base64UrlDecode(payloadPart);
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export function getJwtUserId(token: string | null | undefined): string | number | null {
  if (!token) return null;
  const p = decodeJwtPayload(token);
  if (!p) return null;

  // SimpleJWT suele usar user_id
  const userId = p['user_id'];
  if (typeof userId === 'string' || typeof userId === 'number') return userId;

  // fallback común
  const sub = p['sub'];
  if (typeof sub === 'string' || typeof sub === 'number') return sub;

  return null;
}
