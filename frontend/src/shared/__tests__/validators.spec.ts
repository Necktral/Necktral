import { describe, expect, it } from 'vitest';

import {
  required,
  email,
  numeric,
  minLength,
  maxLength,
  mustMatch,
  rules,
} from 'src/shared/validators';

describe('shared validators', () => {
  // -----------------------------------------------------------------------
  // required
  // -----------------------------------------------------------------------
  describe('required', () => {
    it('rejects empty string', () => {
      expect(required('')).toBe('Requerido');
    });

    it('rejects whitespace-only string', () => {
      expect(required('   ')).toBe('Requerido');
    });

    it('rejects null / undefined', () => {
      expect(required(null)).toBe('Requerido');
      expect(required(undefined)).toBe('Requerido');
    });

    it('accepts non-empty string', () => {
      expect(required('hello')).toBe(true);
    });

    it('accepts numbers', () => {
      expect(required(42)).toBe(true);
      expect(required(0)).toBe(true);
    });
  });

  // -----------------------------------------------------------------------
  // email
  // -----------------------------------------------------------------------
  describe('email', () => {
    it('accepts empty string (combine with required if mandatory)', () => {
      expect(email('')).toBe(true);
    });

    it('accepts null (empty)', () => {
      expect(email(null)).toBe(true);
    });

    it('accepts valid emails', () => {
      expect(email('user@example.com')).toBe(true);
      expect(email('a+b@sub.domain.co')).toBe(true);
    });

    it('rejects invalid emails', () => {
      expect(email('not-an-email')).toBe('Email inválido');
      expect(email('@missing-local.com')).toBe('Email inválido');
      expect(email('no-domain@')).toBe('Email inválido');
    });
  });

  // -----------------------------------------------------------------------
  // numeric
  // -----------------------------------------------------------------------
  describe('numeric', () => {
    it('accepts empty (non-mandatory)', () => {
      expect(numeric('')).toBe(true);
    });

    it('accepts integers', () => {
      expect(numeric('123')).toBe(true);
      expect(numeric('-7')).toBe(true);
    });

    it('accepts decimals', () => {
      expect(numeric('3.14')).toBe(true);
    });

    it('rejects non-numeric', () => {
      expect(numeric('abc')).toBe('Solo números');
      expect(numeric('12a')).toBe('Solo números');
    });
  });

  // -----------------------------------------------------------------------
  // minLength / maxLength
  // -----------------------------------------------------------------------
  describe('minLength', () => {
    const rule = minLength(5);

    it('rejects short strings', () => {
      expect(rule('abc')).toBe('Mínimo 5 caracteres');
    });

    it('accepts long-enough strings', () => {
      expect(rule('abcde')).toBe(true);
      expect(rule('longer')).toBe(true);
    });
  });

  describe('maxLength', () => {
    const rule = maxLength(3);

    it('rejects long strings', () => {
      expect(rule('abcd')).toBe('Máximo 3 caracteres');
    });

    it('accepts short-enough strings', () => {
      expect(rule('ab')).toBe(true);
      expect(rule('abc')).toBe(true);
    });
  });

  // -----------------------------------------------------------------------
  // mustMatch
  // -----------------------------------------------------------------------
  describe('mustMatch', () => {
    it('passes when values match', () => {
      const rule = mustMatch(() => 'secret');
      expect(rule('secret')).toBe(true);
    });

    it('fails when values differ', () => {
      const rule = mustMatch(() => 'secret');
      expect(rule('other')).toBe('Los valores no coinciden');
    });

    it('supports custom message', () => {
      const rule = mustMatch(() => 'a', 'Must be equal');
      expect(rule('b')).toBe('Must be equal');
    });
  });

  // -----------------------------------------------------------------------
  // rules namespace
  // -----------------------------------------------------------------------
  describe('rules namespace', () => {
    it('exposes all validators', () => {
      expect(rules.required).toBe(required);
      expect(rules.email).toBe(email);
      expect(rules.numeric).toBe(numeric);
      expect(rules.minLength).toBe(minLength);
      expect(rules.maxLength).toBe(maxLength);
      expect(rules.mustMatch).toBe(mustMatch);
    });
  });
});
