/**
 * Shared form-validation rules for Quasar `:rules` prop.
 *
 * Usage:
 *   import { rules } from 'src/shared/validators';
 *   <q-input :rules="[rules.required]" />
 *   <q-input :rules="[rules.email]" />
 */

type ValidationRule = (val: unknown) => true | string;

function str(val: unknown): string {
  if (val == null) return '';
  if (typeof val === 'string') return val;
  if (typeof val === 'number' || typeof val === 'boolean') return `${val}`;
  return '';
}

// ---------------------------------------------------------------------------
// Primitive rules
// ---------------------------------------------------------------------------

/** Field must not be empty / blank. */
export const required: ValidationRule = (val) =>
  !!str(val).trim() || 'Requerido';

/** Value must be a syntactically valid e-mail (if non-empty). */
export const email: ValidationRule = (val) => {
  const s = str(val).trim();
  if (!s) return true; // allow empty — combine with `required` if mandatory
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s) || 'Email inválido';
};

/** Value must be numeric (integer or decimal). */
export const numeric: ValidationRule = (val) => {
  const s = str(val).trim();
  if (!s) return true;
  return /^-?\d+(\.\d+)?$/.test(s) || 'Solo números';
};

/** Value must satisfy a minimum length. */
export function minLength(min: number): ValidationRule {
  return (val) => {
    const s = str(val);
    return s.length >= min || `Mínimo ${min} caracteres`;
  };
}

/** Value must satisfy a maximum length. */
export function maxLength(max: number): ValidationRule {
  return (val) => {
    const s = str(val);
    return s.length <= max || `Máximo ${max} caracteres`;
  };
}

// ---------------------------------------------------------------------------
// Composite / factory rules
// ---------------------------------------------------------------------------

/**
 * Build a "must match" rule — useful for password confirmation fields.
 * @param getRef callback that returns the reference value at validation time
 * @param msg    custom error message
 */
export function mustMatch(getRef: () => unknown, msg = 'Los valores no coinciden'): ValidationRule {
  return (val) => val === getRef() || msg;
}

// ---------------------------------------------------------------------------
// Convenience re-export as namespace
// ---------------------------------------------------------------------------

export const rules = {
  required,
  email,
  numeric,
  minLength,
  maxLength,
  mustMatch,
} as const;
