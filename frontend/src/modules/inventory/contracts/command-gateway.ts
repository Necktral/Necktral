import type {
  InventoryBatchCommand,
  InventoryBatchCommandResult,
  InventoryBatchResponse,
} from 'src/services/inventory.service';

export type InventoryCommandGateway = {
  submitBatch(commands: InventoryBatchCommand[]): Promise<InventoryBatchResponse>;
};

export function findBatchResultByCommandId(
  results: InventoryBatchCommandResult[],
  commandId: string,
): InventoryBatchCommandResult | null {
  return results.find((row) => row.command_id === commandId) ?? null;
}
