import { describe, expect, it } from 'vitest';

import {
  DEFAULT_PAGE_SIZE,
  DEFAULT_ROWS_PER_PAGE,
  ALL_ROWS_LIMIT,
  computeLimit,
  PAGINATION,
} from 'src/shared/constants';

describe('shared constants', () => {
  describe('pagination defaults', () => {
    it('has sensible defaults', () => {
      expect(DEFAULT_PAGE_SIZE).toBe(50);
      expect(DEFAULT_ROWS_PER_PAGE).toBe(20);
      expect(ALL_ROWS_LIMIT).toBe(200);
    });
  });

  describe('computeLimit', () => {
    it('returns rowsPerPage when non-zero', () => {
      expect(computeLimit(25)).toBe(25);
      expect(computeLimit(100)).toBe(100);
    });

    it('returns ALL_ROWS_LIMIT when rowsPerPage is 0 (show all)', () => {
      expect(computeLimit(0)).toBe(ALL_ROWS_LIMIT);
    });
  });

  describe('PAGINATION namespace', () => {
    it('exposes grouped constants', () => {
      expect(PAGINATION.DEFAULT_PAGE_SIZE).toBe(50);
      expect(PAGINATION.computeLimit(0)).toBe(200);
    });
  });
});
