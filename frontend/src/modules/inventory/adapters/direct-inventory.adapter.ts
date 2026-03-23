import type { InventoryCommandGateway } from 'src/modules/inventory/contracts/command-gateway';
import { postInventoryCommandBatch, type InventoryBatchCommand } from 'src/services/inventory.service';

export const directInventoryAdapter: InventoryCommandGateway = {
  async submitBatch(commands: InventoryBatchCommand[]) {
    return postInventoryCommandBatch(commands);
  },
};
