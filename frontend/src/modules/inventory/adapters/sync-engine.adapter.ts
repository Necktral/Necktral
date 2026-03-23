import type { InventoryCommandGateway } from 'src/modules/inventory/contracts/command-gateway';
import type { InventoryBatchCommand, InventoryBatchResponse } from 'src/services/inventory.service';

export const syncEngineInventoryAdapter: InventoryCommandGateway = {
  submitBatch(commands: InventoryBatchCommand[]): Promise<InventoryBatchResponse> {
    void commands;
    return Promise.reject(new Error('SYNC_ENGINE_ADAPTER_NOT_IMPLEMENTED'));
  },
};
