import { describe, expect, it } from 'vitest';

import { findBatchResultByCommandId } from 'src/modules/inventory/contracts/command-gateway';

describe('inventory command gateway helpers', () => {
  it('returns the matching command result by command_id', () => {
    const row = findBatchResultByCommandId(
      [
        { command_id: 'a', status: 'APPLIED' },
        { command_id: 'b', status: 'REJECTED', error_code: 'X' },
      ],
      'b',
    );

    expect(row).toBeTruthy();
    expect(row?.status).toBe('REJECTED');
  });

  it('returns null when command_id does not exist', () => {
    const row = findBatchResultByCommandId([{ command_id: 'a', status: 'APPLIED' }], 'z');
    expect(row).toBeNull();
  });
});
