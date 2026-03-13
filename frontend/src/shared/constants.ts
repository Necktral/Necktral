/**
 * Application-wide constants for pagination, limits and defaults.
 *
 * Usage:
 *   import { PAGINATION } from 'src/shared/constants';
 *   const limit = computeLimit(rowsPerPage);
 */

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

/** Default page size for paginated lists. */
export const DEFAULT_PAGE_SIZE = 50;

/** Default rows-per-page for Q-Table components. */
export const DEFAULT_ROWS_PER_PAGE = 20;

/** Limit used when "show all" (rowsPerPage === 0) is selected. */
export const ALL_ROWS_LIMIT = 200;

/**
 * Convert Q-Table `rowsPerPage` into an API `limit` value.
 *
 * When the user selects "All" (rowsPerPage === 0), we cap at ALL_ROWS_LIMIT
 * to avoid unbounded queries.
 */
export function computeLimit(rowsPerPage: number): number {
  return rowsPerPage === 0 ? ALL_ROWS_LIMIT : rowsPerPage;
}

// ---------------------------------------------------------------------------
// Pagination (grouped namespace for imports)
// ---------------------------------------------------------------------------

export const PAGINATION = {
  DEFAULT_PAGE_SIZE,
  DEFAULT_ROWS_PER_PAGE,
  ALL_ROWS_LIMIT,
  computeLimit,
} as const;
