<template>
  <AppContainer>
    <AppPageHeader
      :title="isEdit ? labels.inventory + ' · Editar ítem' : labels.inventory + ' · Nuevo ítem'"
      subtitle="Item Master P0 local multisucursal con validación por pasos y guardado final."
    >
      <template #actions>
        <q-btn flat icon="arrow_back" label="Volver" class="inventory-touch-target" @click="goBack" />
      </template>
    </AppPageHeader>

    <q-banner v-if="!canReadCatalogs" class="q-mt-md" dense rounded>
      Requiere permiso `inventory.item.read` para cargar catálogos.
    </q-banner>

    <q-banner v-else-if="!canSubmit" class="q-mt-md" dense rounded>
      No tienes permiso para {{ isEdit ? 'editar' : 'crear' }} ítems.
    </q-banner>

    <q-card v-else class="app-card q-mt-md">
      <q-card-section>
        <div class="row items-center q-col-gutter-sm q-mb-sm">
          <div class="col-auto">
            <q-chip color="primary" text-color="white" dense>Stepper 6 pasos</q-chip>
          </div>
          <div class="col">
            <span class="text-caption app-muted">Atajos: Ctrl/Cmd+Enter guardar, Tab/Shift+Tab navegación.</span>
          </div>
        </div>

        <q-stepper v-model="step" flat animated color="primary" header-nav>
          <q-step :name="1" title="Identidad comercial" icon="badge" :done="step > 1">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-4">
                <q-input
                  v-model="form.sku"
                  outlined
                  label="SKU *"
                  maxlength="64"
                  :error="Boolean(fieldErrors.sku)"
                  :error-message="fieldErrors.sku"
                  @blur="validateSkuAsync"
                />
              </div>
              <div class="col-12 col-md-8">
                <q-input
                  v-model="form.name"
                  outlined
                  label="Nombre *"
                  maxlength="160"
                  :error="Boolean(fieldErrors.name)"
                  :error-message="fieldErrors.name"
                />
              </div>

              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.item_type"
                  outlined
                  label="Tipo de ítem *"
                  :options="itemTypeOptions"
                  emit-value
                  map-options
                  :error="Boolean(fieldErrors.item_type)"
                  :error-message="fieldErrors.item_type"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.status"
                  outlined
                  label="Estado *"
                  :options="statusOptions"
                  emit-value
                  map-options
                  :error="Boolean(fieldErrors.status)"
                  :error-message="fieldErrors.status"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.category_id"
                  outlined
                  label="Categoría *"
                  :options="categoryOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                  :error="Boolean(fieldErrors.category_id)"
                  :error-message="fieldErrors.category_id"
                />
              </div>

              <div class="col-12 col-md-4">
                <q-input v-model="form.short_name" outlined label="Nombre corto" maxlength="80" />
              </div>
              <div class="col-12 col-md-4">
                <q-input v-model="form.invoice_name" outlined label="Nombre para factura" maxlength="160" />
              </div>
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.brand_id"
                  outlined
                  clearable
                  label="Marca"
                  :options="brandOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                />
              </div>

              <div class="col-12 col-md-6">
                <q-select
                  v-model="form.subcategory_id"
                  outlined
                  clearable
                  label="Subcategoría"
                  :options="subcategoryOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                  :disable="!form.category_id"
                  :error="Boolean(fieldErrors.subcategory_id)"
                  :error-message="fieldErrors.subcategory_id"
                />
              </div>
              <div class="col-12 col-md-6">
                <q-input v-model="form.description" outlined type="textarea" autogrow label="Descripción" maxlength="500" />
              </div>
            </div>
          </q-step>

          <q-step :name="2" title="Identificación y clasificación" icon="qr_code" :done="step > 2">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-4">
                <q-input
                  v-model="form.barcode"
                  outlined
                  label="Código de barras"
                  maxlength="64"
                  :error="Boolean(fieldErrors.barcode)"
                  :error-message="fieldErrors.barcode"
                  @blur="validateBarcodeAsync"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.barcode_type"
                  outlined
                  clearable
                  label="Tipo de código"
                  :options="barcodeTypeOptions"
                  emit-value
                  map-options
                  :disable="!form.barcode.trim()"
                  :error="Boolean(fieldErrors.barcode_type)"
                  :error-message="fieldErrors.barcode_type"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-input v-model="form.alternate_code" outlined label="Código alterno" maxlength="64" />
              </div>

              <div class="col-12">
                <q-select
                  v-model="form.search_tags"
                  outlined
                  use-input
                  use-chips
                  multiple
                  hide-dropdown-icon
                  new-value-mode="add-unique"
                  label="Tags de búsqueda"
                  hint="Hasta 15 tags, entre 2 y 24 caracteres."
                  :error="Boolean(fieldErrors.search_tags)"
                  :error-message="fieldErrors.search_tags"
                />
              </div>

              <div class="col-12 col-md-3">
                <q-toggle v-model="form.purchase_enabled" label="Se compra" />
              </div>
              <div class="col-12 col-md-3">
                <q-toggle v-model="form.sales_enabled" label="Se vende" />
              </div>
              <div class="col-12 col-md-3">
                <q-toggle v-model="form.controls_stock" label="Controla stock" :disable="isService" />
              </div>
              <div class="col-12 col-md-3">
                <q-toggle v-model="form.transfer_enabled" label="Permite transferencias" :disable="!form.controls_stock" />
              </div>

              <div class="col-12 col-md-3">
                <q-toggle v-model="form.allow_returns" label="Permite devoluciones" />
              </div>
            </div>
          </q-step>

          <q-step :name="3" title="Unidades y conversiones" icon="straighten" :done="step > 3">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.uom_base"
                  outlined
                  label="Unidad base *"
                  :options="uomOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                  :error="Boolean(fieldErrors.uom_base)"
                  :error-message="fieldErrors.uom_base"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.uom_purchase"
                  outlined
                  label="Unidad de compra *"
                  :options="uomOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                  :error="Boolean(fieldErrors.uom_purchase)"
                  :error-message="fieldErrors.uom_purchase"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.uom_sale"
                  outlined
                  label="Unidad de venta *"
                  :options="uomOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                  :error="Boolean(fieldErrors.uom_sale)"
                  :error-message="fieldErrors.uom_sale"
                />
              </div>
            </div>

            <div v-if="showConversions" class="q-mt-md">
              <div class="row items-center justify-between q-mb-sm">
                <div class="text-subtitle2">Conversiones</div>
                <q-btn flat icon="add" label="Agregar conversión" class="inventory-touch-target" @click="addConversionRow" />
              </div>
              <div v-if="fieldErrors.uom_conversions" class="text-negative text-caption q-mb-sm">{{ fieldErrors.uom_conversions }}</div>
              <div
                v-for="(row, idx) in form.uom_conversions"
                :key="'conv-' + idx"
                class="row q-col-gutter-sm q-mb-sm items-center"
              >
                <div class="col-12 col-md-6">
                  <q-select
                    v-model="row.to_uom"
                    outlined
                    label="Unidad destino"
                    :options="uomOptions"
                    emit-value
                    map-options
                    option-label="label"
                    option-value="value"
                  />
                </div>
                <div class="col-10 col-md-4">
                  <q-input v-model="row.factor" outlined label="Factor (> 0)" />
                </div>
                <div class="col-2 col-md-2 text-right">
                  <q-btn flat icon="delete" color="negative" class="inventory-touch-target" @click="removeConversionRow(idx)" />
                </div>
              </div>
            </div>

            <div class="row q-col-gutter-md q-mt-sm">
              <div class="col-12 col-md-3" v-if="!isService">
                <q-toggle v-model="form.allow_fraction" label="Permite fracción" />
              </div>
              <div class="col-12 col-md-3" v-if="form.controls_stock">
                <q-input
                  v-model="form.min_qty"
                  outlined
                  label="Cantidad mínima"
                  :error="Boolean(fieldErrors.min_qty)"
                  :error-message="fieldErrors.min_qty"
                />
              </div>
              <div class="col-12 col-md-3" v-if="form.allow_fraction">
                <q-input
                  v-model="form.rounding_increment"
                  outlined
                  label="Incremento de redondeo"
                  :error="Boolean(fieldErrors.rounding_increment)"
                  :error-message="fieldErrors.rounding_increment"
                />
              </div>
            </div>
          </q-step>

          <q-step :name="4" title="Inventario y sucursales" icon="store" :done="step > 4">
            <q-banner v-if="!form.controls_stock" dense rounded class="q-mb-md">
              Este ítem no controla stock. Paso 4 no aplica.
            </q-banner>

            <div v-else class="row q-col-gutter-md">
              <div class="col-12 col-md-6">
                <q-select
                  v-model="form.enabled_branch_ids"
                  outlined
                  multiple
                  label="Sucursales habilitadas *"
                  :options="branchOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                  :error="Boolean(fieldErrors.enabled_branch_ids)"
                  :error-message="fieldErrors.enabled_branch_ids"
                />
              </div>
              <div class="col-12 col-md-3">
                <q-select
                  v-model="form.default_branch_id"
                  outlined
                  label="Sucursal por defecto *"
                  :options="enabledBranchOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                  :error="Boolean(fieldErrors.default_branch_id)"
                  :error-message="fieldErrors.default_branch_id"
                />
              </div>
              <div class="col-12 col-md-3">
                <q-select
                  v-model="form.default_warehouse_id"
                  outlined
                  label="Almacén por defecto *"
                  :options="warehouseOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                  :loading="warehousesLoading"
                  :error="Boolean(fieldErrors.default_warehouse_id)"
                  :error-message="fieldErrors.default_warehouse_id"
                />
              </div>

              <div class="col-12 col-md-3">
                <q-input
                  v-model="form.min_stock"
                  outlined
                  label="Stock mínimo *"
                  :error="Boolean(fieldErrors.min_stock)"
                  :error-message="fieldErrors.min_stock"
                />
              </div>
              <div class="col-12 col-md-3">
                <q-input
                  v-model="form.max_stock"
                  outlined
                  label="Stock máximo"
                  :error="Boolean(fieldErrors.max_stock)"
                  :error-message="fieldErrors.max_stock"
                />
              </div>
              <div class="col-12 col-md-3">
                <q-input
                  v-model="form.reorder_point"
                  outlined
                  label="Punto de reorden *"
                  :error="Boolean(fieldErrors.reorder_point)"
                  :error-message="fieldErrors.reorder_point"
                />
              </div>
              <div class="col-12 col-md-3">
                <q-input
                  v-model="form.reorder_qty"
                  outlined
                  label="Cantidad de reorden *"
                  :error="Boolean(fieldErrors.reorder_qty)"
                  :error-message="fieldErrors.reorder_qty"
                />
              </div>

              <div class="col-12 col-md-3">
                <q-toggle v-model="form.allow_negative_stock" label="Permite stock negativo" />
              </div>
              <div class="col-12 col-md-3">
                <q-toggle v-model="form.reserve_enabled" label="Permite reserva" />
              </div>
              <div class="col-12 col-md-6">
                <q-input v-model="form.internal_location" outlined label="Ubicación interna" maxlength="64" />
              </div>
            </div>
          </q-step>

          <q-step :name="5" title="Costos, compras y ventas" icon="payments" :done="step > 5">
            <q-banner v-if="!form.controls_stock" dense rounded class="q-mb-md">
              Costeo de inventario no aplica porque `controls_stock=false`.
            </q-banner>

            <div v-else class="row q-col-gutter-md">
              <div class="col-12 col-md-3">
                <q-input v-model="form.costing_method" outlined readonly label="Método de costo" />
              </div>
              <div class="col-12 col-md-3">
                <q-input
                  v-model="form.initial_cost"
                  outlined
                  label="Costo inicial *"
                  :error="Boolean(fieldErrors.initial_cost)"
                  :error-message="fieldErrors.initial_cost"
                />
              </div>
              <div class="col-12 col-md-3">
                <q-input
                  v-model="form.standard_cost"
                  outlined
                  label="Costo estándar *"
                  :error="Boolean(fieldErrors.standard_cost)"
                  :error-message="fieldErrors.standard_cost"
                />
              </div>
              <div class="col-12 col-md-3">
                <q-input
                  v-model="form.currency"
                  outlined
                  label="Moneda *"
                  maxlength="3"
                  :error="Boolean(fieldErrors.currency)"
                  :error-message="fieldErrors.currency"
                />
              </div>
              <div class="col-12 col-md-3">
                <q-input
                  v-model="form.last_known_cost"
                  outlined
                  label="Último costo conocido"
                  :error="Boolean(fieldErrors.last_known_cost)"
                  :error-message="fieldErrors.last_known_cost"
                />
              </div>
            </div>

            <div v-if="form.purchase_enabled" class="q-mt-md">
              <div class="text-subtitle2 q-mb-sm">Compras</div>
              <div class="row q-col-gutter-md">
                <div class="col-12 col-md-3">
                  <q-input v-model.number="form.preferred_supplier_id" outlined type="number" label="Proveedor preferido (ID)" />
                </div>
                <div class="col-12 col-md-3">
                  <q-input v-model="form.supplier_item_code" outlined label="Código proveedor" maxlength="64" />
                </div>
                <div class="col-12 col-md-2">
                  <q-input
                    v-model.number="form.lead_time_days"
                    outlined
                    type="number"
                    label="Lead time días"
                    :error="Boolean(fieldErrors.lead_time_days)"
                    :error-message="fieldErrors.lead_time_days"
                  />
                </div>
                <div class="col-12 col-md-2">
                  <q-input
                    v-model="form.purchase_moq"
                    outlined
                    label="MOQ compra"
                    :error="Boolean(fieldErrors.purchase_moq)"
                    :error-message="fieldErrors.purchase_moq"
                  />
                </div>
                <div class="col-12 col-md-2">
                  <q-input
                    v-model="form.purchase_multiple"
                    outlined
                    label="Múltiplo compra"
                    :error="Boolean(fieldErrors.purchase_multiple)"
                    :error-message="fieldErrors.purchase_multiple"
                  />
                </div>
              </div>
            </div>

            <div v-if="form.sales_enabled" class="q-mt-md">
              <div class="text-subtitle2 q-mb-sm">Ventas</div>
              <div class="row q-col-gutter-md">
                <div class="col-12 col-md-3">
                  <q-input v-model="form.suggested_price" outlined label="Precio sugerido" />
                </div>
                <div class="col-12 col-md-3">
                  <q-input
                    v-model="form.min_sale_price"
                    outlined
                    label="Precio mínimo venta"
                    :error="Boolean(fieldErrors.min_sale_price)"
                    :error-message="fieldErrors.min_sale_price"
                  />
                </div>
                <div class="col-12 col-md-2">
                  <q-toggle v-model="form.allow_discount" label="Permite descuento" />
                </div>
                <div class="col-12 col-md-2">
                  <q-toggle v-model="form.visible_pos" label="Visible POS *" />
                  <div v-if="fieldErrors.visible_pos" class="text-negative text-caption">{{ fieldErrors.visible_pos }}</div>
                </div>
                <div class="col-12 col-md-2">
                  <q-toggle v-model="form.visible_quote" label="Visible cotización" />
                </div>
                <div class="col-12 col-md-2">
                  <q-toggle v-model="form.visible_invoice" label="Visible factura" />
                </div>
              </div>
            </div>
          </q-step>

          <q-step :name="6" title="Fiscal y trazabilidad" icon="policy">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.tax_profile_id"
                  outlined
                  label="Perfil fiscal *"
                  :options="taxProfileOptions"
                  emit-value
                  map-options
                  option-label="label"
                  option-value="value"
                  :error="Boolean(fieldErrors.tax_profile_id)"
                  :error-message="fieldErrors.tax_profile_id"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.tax_treatment"
                  outlined
                  label="Tratamiento fiscal *"
                  :options="taxTreatmentOptions"
                  emit-value
                  map-options
                  :error="Boolean(fieldErrors.tax_treatment)"
                  :error-message="fieldErrors.tax_treatment"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-input v-model="form.invoice_description" outlined label="Descripción para factura" maxlength="160" />
              </div>

              <template v-if="form.controls_stock">
                <div class="col-12 col-md-2">
                  <q-toggle v-model="form.use_lot" label="Usa lote" />
                </div>
                <div class="col-12 col-md-2">
                  <q-toggle v-model="form.use_serial" label="Usa serie" />
                </div>
                <div class="col-12 col-md-2">
                  <q-toggle v-model="form.use_expiry" label="Usa vencimiento" />
                </div>
                <div class="col-12 col-md-3" v-if="form.use_expiry">
                  <q-input
                    v-model.number="form.shelf_life_days"
                    outlined
                    type="number"
                    label="Vida útil (días) *"
                    :error="Boolean(fieldErrors.shelf_life_days)"
                    :error-message="fieldErrors.shelf_life_days"
                  />
                </div>
                <div class="col-12 col-md-3">
                  <q-toggle v-model="form.quality_control_required" label="Requiere control calidad" />
                </div>
                <div class="col-12 col-md-3">
                  <q-toggle v-model="form.allow_return_to_stock" label="Permite retorno a stock" />
                </div>
              </template>
            </div>
          </q-step>
        </q-stepper>
      </q-card-section>

      <q-separator />

      <q-card-section class="inventory-sticky-actionbar">
        <q-btn
          flat
          icon="arrow_back"
          label="Anterior"
          class="inventory-touch-target"
          :disable="step <= 1 || submitting || loading"
          @click="goPrev"
        />
        <q-btn
          flat
          icon-right="arrow_forward"
          label="Siguiente"
          class="inventory-touch-target"
          :disable="step >= 6 || submitting || loading"
          @click="goNext"
        />
        <q-space />
        <q-btn
          color="primary"
          icon="save"
          :label="isEdit ? 'Guardar cambios (Ctrl+Enter)' : 'Guardar ítem (Ctrl+Enter)'"
          class="inventory-touch-target"
          :loading="submitting"
          :disable="loading"
          @click="save"
          @keydown.ctrl.enter.prevent="save"
          @keydown.meta.enter.prevent="save"
        />
      </q-card-section>
    </q-card>
  </AppContainer>
</template>

<script setup lang="ts">
import { isAxiosError } from 'axios';
import { Notify } from 'quasar';
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import type {
  BarcodeType,
  InventoryCategoryRow,
  InventoryItemRow,
  InventoryItemUpsertPayload,
  ItemStatus,
  ItemType,
  TaxTreatment,
  UomCode,
  WarehouseRow,
} from 'src/services/inventory.service';
import {
  createInventoryItem,
  getInventoryItem,
  listInventoryBrands,
  listInventoryCategories,
  listInventoryItems,
  listInventoryTaxProfiles,
  listInventoryUoms,
  listInventoryWarehouses,
  patchInventoryItem,
} from 'src/services/inventory.service';
import { BUSINESS_LABELS, UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';

type SelectOption<T> = {
  label: string;
  value: T;
};

type ConversionRow = {
  to_uom: UomCode | '';
  factor: string;
};

type ItemMasterForm = {
  sku: string;
  name: string;
  item_type: ItemType;
  status: ItemStatus;
  short_name: string;
  invoice_name: string;
  brand_id: number | null;
  category_id: number | null;
  subcategory_id: number | null;
  description: string;

  barcode: string;
  barcode_type: BarcodeType | '';
  alternate_code: string;
  search_tags: string[];
  purchase_enabled: boolean;
  sales_enabled: boolean;
  controls_stock: boolean;
  transfer_enabled: boolean;
  allow_returns: boolean;

  uom_base: UomCode;
  uom_purchase: UomCode;
  uom_sale: UomCode;
  uom_conversions: ConversionRow[];
  allow_fraction: boolean;
  min_qty: string;
  rounding_increment: string;

  enabled_branch_ids: number[];
  default_branch_id: number | null;
  default_warehouse_id: number | null;
  min_stock: string;
  max_stock: string;
  reorder_point: string;
  reorder_qty: string;
  allow_negative_stock: boolean;
  reserve_enabled: boolean;
  internal_location: string;

  costing_method: 'MOVING_WEIGHTED_AVG';
  initial_cost: string;
  standard_cost: string;
  currency: string;
  last_known_cost: string;
  preferred_supplier_id: number | null;
  supplier_item_code: string;
  lead_time_days: number | null;
  purchase_moq: string;
  purchase_multiple: string;
  suggested_price: string;
  min_sale_price: string;
  allow_discount: boolean;
  visible_pos: boolean;
  visible_quote: boolean;
  visible_invoice: boolean;

  tax_profile_id: number | null;
  tax_treatment: TaxTreatment;
  invoice_description: string;
  use_lot: boolean;
  use_serial: boolean;
  use_expiry: boolean;
  shelf_life_days: number | null;
  quality_control_required: boolean;
  allow_return_to_stock: boolean;
};

const props = withDefaults(
  defineProps<{
    mode: 'create' | 'edit';
    itemId?: number | null;
  }>(),
  {
    itemId: null,
  },
);

const labels = BUSINESS_LABELS;
const router = useRouter();
const acl = useAclStore();
const ctx = useContextStore();

const step = ref(1);
const loading = ref(false);
const submitting = ref(false);
const warehousesLoading = ref(false);

const fieldErrors = ref<Record<string, string>>({});
const loadedItemId = ref<number | null>(null);

const uomOptions = ref<Array<SelectOption<UomCode>>>([]);
const brandOptions = ref<Array<SelectOption<number>>>([]);
const categories = ref<InventoryCategoryRow[]>([]);
const taxProfileOptions = ref<Array<SelectOption<number>>>([]);
const warehouses = ref<WarehouseRow[]>([]);

const itemTypeOptions: Array<SelectOption<ItemType>> = [
  { label: 'Inventariable', value: 'INVENTARIABLE' },
  { label: 'No inventariable', value: 'NO_INVENTARIABLE' },
  { label: 'Servicio', value: 'SERVICIO' },
];

const statusOptions: Array<SelectOption<ItemStatus>> = [
  { label: 'Activo', value: 'ACTIVO' },
  { label: 'Inactivo', value: 'INACTIVO' },
  { label: 'Bloqueado', value: 'BLOQUEADO' },
];

const barcodeTypeOptions: Array<SelectOption<BarcodeType>> = [
  { label: 'EAN-13', value: 'EAN13' },
  { label: 'UPC-A', value: 'UPCA' },
  { label: 'Code 128', value: 'CODE128' },
  { label: 'Interno', value: 'INTERNO' },
];

const taxTreatmentOptions: Array<SelectOption<TaxTreatment>> = [
  { label: 'Gravado', value: 'GRAVADO' },
  { label: 'Exento', value: 'EXENTO' },
  { label: 'Exonerado', value: 'EXONERADO' },
];

function defaultForm(): ItemMasterForm {
  return {
    sku: '',
    name: '',
    item_type: 'INVENTARIABLE',
    status: 'ACTIVO',
    short_name: '',
    invoice_name: '',
    brand_id: null,
    category_id: null,
    subcategory_id: null,
    description: '',

    barcode: '',
    barcode_type: '',
    alternate_code: '',
    search_tags: [],
    purchase_enabled: true,
    sales_enabled: true,
    controls_stock: true,
    transfer_enabled: true,
    allow_returns: true,

    uom_base: 'UNIT',
    uom_purchase: 'UNIT',
    uom_sale: 'UNIT',
    uom_conversions: [],
    allow_fraction: false,
    min_qty: '0.0000',
    rounding_increment: '0.0000',

    enabled_branch_ids: [],
    default_branch_id: null,
    default_warehouse_id: null,
    min_stock: '0.0000',
    max_stock: '',
    reorder_point: '0.0000',
    reorder_qty: '1.0000',
    allow_negative_stock: false,
    reserve_enabled: false,
    internal_location: '',

    costing_method: 'MOVING_WEIGHTED_AVG',
    initial_cost: '0.000000',
    standard_cost: '0.000000',
    currency: 'NIO',
    last_known_cost: '',
    preferred_supplier_id: null,
    supplier_item_code: '',
    lead_time_days: null,
    purchase_moq: '',
    purchase_multiple: '',
    suggested_price: '',
    min_sale_price: '',
    allow_discount: true,
    visible_pos: true,
    visible_quote: true,
    visible_invoice: true,

    tax_profile_id: null,
    tax_treatment: 'GRAVADO',
    invoice_description: '',
    use_lot: false,
    use_serial: false,
    use_expiry: false,
    shelf_life_days: null,
    quality_control_required: false,
    allow_return_to_stock: true,
  };
}

const form = reactive<ItemMasterForm>(defaultForm());

const isEdit = computed(() => props.mode === 'edit' && Number(props.itemId) > 0);
const companyId = computed(() => ctx.activeCompanyId);
const numericCompanyId = computed(() => Number(companyId.value || '0'));
const currentItemId = computed(() => (isEdit.value ? Number(props.itemId) : null));

const canReadCatalogs = computed(() => {
  if (!companyId.value) return false;
  return acl.hasPermission(companyId.value, 'inventory.item.read');
});

const canCreate = computed(() => {
  if (!companyId.value) return false;
  return acl.hasPermission(companyId.value, 'inventory.item.create');
});

const canUpdate = computed(() => {
  if (!companyId.value) return false;
  return acl.hasPermission(companyId.value, 'inventory.item.update');
});

const canSubmit = computed(() => (isEdit.value ? canUpdate.value : canCreate.value));
const isService = computed(() => form.item_type === 'SERVICIO');
const showConversions = computed(() => form.uom_purchase !== form.uom_base || form.uom_sale !== form.uom_base);

const categoryOptions = computed<Array<SelectOption<number>>>(() =>
  categories.value
    .filter((row) => row.parent_id == null)
    .map((row) => ({ label: row.name, value: row.id })),
);

const subcategoryOptions = computed<Array<SelectOption<number>>>(() => {
  if (!form.category_id) return [];
  return categories.value
    .filter((row) => row.parent_id === form.category_id)
    .map((row) => ({ label: row.name, value: row.id }));
});

const branchOptions = computed<Array<SelectOption<number>>>(() => {
  const id = companyId.value;
  if (!id) return [];
  const company = acl.companies.find((row) => row.company_id === id);
  if (!company) return [];
  return company.branches.map((row) => ({
    label: row.branch_name,
    value: Number(row.branch_id),
  }));
});

const enabledBranchOptions = computed<Array<SelectOption<number>>>(() => {
  const enabled = new Set(form.enabled_branch_ids);
  return branchOptions.value.filter((row) => enabled.has(row.value));
});

const warehouseOptions = computed<Array<SelectOption<number>>>(() =>
  warehouses.value.map((row) => ({
    label: (row.code || '-') + ' · ' + row.name,
    value: row.id,
  })),
);

function normalizeSku(raw: string): string {
  return String(raw || '').trim().toUpperCase();
}

function toNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function decimalIsValid(value: string): boolean {
  return /^-?\d+(\.\d+)?$/.test(String(value).trim());
}

function decimalGE(value: string, min: number): boolean {
  if (!decimalIsValid(value)) return false;
  return Number(value) >= min;
}

function clearFieldError(key: string): void {
  if (!fieldErrors.value[key]) return;
  const next = { ...fieldErrors.value };
  delete next[key];
  fieldErrors.value = next;
}

function setFieldError(key: string, message: string): void {
  fieldErrors.value = { ...fieldErrors.value, [key]: message };
}

function addConversionRow(): void {
  form.uom_conversions.push({ to_uom: '', factor: '' });
}

function removeConversionRow(index: number): void {
  form.uom_conversions.splice(index, 1);
}

async function loadWarehousesByBranch(branchId: number | null): Promise<void> {
  if (!branchId || !numericCompanyId.value) {
    warehouses.value = [];
    form.default_warehouse_id = null;
    return;
  }
  warehousesLoading.value = true;
  try {
    const response = await listInventoryWarehouses({
      branch_id: branchId,
      is_active: true,
      limit: 200,
      offset: 0,
    });
    warehouses.value = response.results;
    const available = new Set(response.results.map((row) => row.id));
    if (form.default_warehouse_id && !available.has(form.default_warehouse_id)) {
      form.default_warehouse_id = null;
    }
  } finally {
    warehousesLoading.value = false;
  }
}

async function loadCatalogs(): Promise<void> {
  if (!canReadCatalogs.value) return;
  loading.value = true;
  try {
    const [uoms, brands, allCategories, taxProfiles] = await Promise.all([
      listInventoryUoms(),
      listInventoryBrands({ is_active: true, limit: 200, offset: 0 }),
      listInventoryCategories({ is_active: true, limit: 200, offset: 0 }),
      listInventoryTaxProfiles({ is_active: true, limit: 200, offset: 0 }),
    ]);

    uomOptions.value = uoms.map((row) => ({ label: row.code, value: row.code }));
    brandOptions.value = brands.results.map((row) => ({ label: row.name, value: row.id }));
    categories.value = allCategories.results;
    taxProfileOptions.value = taxProfiles.results.map((row) => ({
      label: row.code + ' · ' + row.name,
      value: row.id,
    }));
  } finally {
    loading.value = false;
  }
}

function mapItemToForm(item: InventoryItemRow): void {
  form.sku = item.sku;
  form.name = item.name;
  form.item_type = item.item_type;
  form.status = item.status;
  form.short_name = item.short_name || '';
  form.invoice_name = item.invoice_name || '';
  form.brand_id = item.brand_id ?? null;
  form.category_id = item.category_id ?? null;
  form.subcategory_id = item.subcategory_id ?? null;
  form.description = item.description || '';

  form.barcode = item.barcode || '';
  form.barcode_type = item.barcode_type || '';
  form.alternate_code = item.alternate_code || '';
  form.search_tags = Array.isArray(item.search_tags) ? item.search_tags.map((t) => String(t)) : [];
  form.purchase_enabled = item.purchase_enabled;
  form.sales_enabled = item.sales_enabled;
  form.controls_stock = item.controls_stock;
  form.transfer_enabled = item.transfer_enabled;
  form.allow_returns = item.allow_returns;

  form.uom_base = item.uom_base;
  form.uom_purchase = item.uom_purchase;
  form.uom_sale = item.uom_sale;
  form.uom_conversions = Array.isArray(item.uom_conversions)
    ? item.uom_conversions.map((row) => ({
        to_uom: (row.to_uom || '') as UomCode | '',
        factor: String(row.factor || ''),
      }))
    : [];
  form.allow_fraction = item.allow_fraction;
  form.min_qty = item.min_qty || '0.0000';
  form.rounding_increment = item.rounding_increment || '0.0000';

  form.enabled_branch_ids = Array.isArray(item.enabled_branch_ids)
    ? item.enabled_branch_ids.map((id) => Number(id)).filter((id) => Number.isFinite(id))
    : [];
  form.default_branch_id = item.default_branch_id ?? null;
  form.default_warehouse_id = item.default_warehouse_id ?? null;
  form.min_stock = item.min_stock || '0.0000';
  form.max_stock = item.max_stock || '';
  form.reorder_point = item.reorder_point || '0.0000';
  form.reorder_qty = item.reorder_qty || '1.0000';
  form.allow_negative_stock = item.allow_negative_stock;
  form.reserve_enabled = item.reserve_enabled;
  form.internal_location = item.internal_location || '';

  form.costing_method = 'MOVING_WEIGHTED_AVG';
  form.initial_cost = item.initial_cost || '0.000000';
  form.standard_cost = item.standard_cost || '0.000000';
  form.currency = item.currency || 'NIO';
  form.last_known_cost = item.last_known_cost || '';
  form.preferred_supplier_id = item.preferred_supplier_id ?? null;
  form.supplier_item_code = item.supplier_item_code || '';
  form.lead_time_days = item.lead_time_days ?? null;
  form.purchase_moq = item.purchase_moq || '';
  form.purchase_multiple = item.purchase_multiple || '';
  form.suggested_price = item.suggested_price || '';
  form.min_sale_price = item.min_sale_price || '';
  form.allow_discount = item.allow_discount;
  form.visible_pos = item.visible_pos;
  form.visible_quote = item.visible_quote;
  form.visible_invoice = item.visible_invoice;

  form.tax_profile_id = item.tax_profile_id ?? null;
  form.tax_treatment = item.tax_treatment;
  form.invoice_description = item.invoice_description || '';
  form.use_lot = item.use_lot;
  form.use_serial = item.use_serial;
  form.use_expiry = item.use_expiry;
  form.shelf_life_days = item.shelf_life_days ?? null;
  form.quality_control_required = item.quality_control_required;
  form.allow_return_to_stock = item.allow_return_to_stock;
}

function stringifyValidationValue(value: unknown): string {
  if (typeof value === 'string' && value.trim()) return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) {
    return stringifyValidationValue(value[0]);
  }
  if (value && typeof value === 'object') {
    const detail = (value as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
  }
  return 'Validación inválida.';
}

async function loadItemIfNeeded(): Promise<void> {
  if (!isEdit.value || !currentItemId.value) return;
  if (loadedItemId.value === currentItemId.value) return;
  loading.value = true;
  try {
    const item = await getInventoryItem(currentItemId.value);
    mapItemToForm(item);
    loadedItemId.value = currentItemId.value;
    await loadWarehousesByBranch(form.default_branch_id);
  } finally {
    loading.value = false;
  }
}

function validateBarcodeFormat(barcode: string, barcodeType: BarcodeType | ''): string | null {
  if (!barcode) return null;
  if (!barcodeType) return 'Tipo de código requerido cuando barcode existe.';

  if (barcodeType === 'EAN13' && !/^\d{13}$/.test(barcode)) return 'EAN13 inválido.';
  if (barcodeType === 'UPCA' && !/^\d{12}$/.test(barcode)) return 'UPCA inválido.';
  if (barcodeType === 'CODE128' && !/^[A-Za-z0-9\\-\\.\\$\\/\\+%\\s]{1,64}$/.test(barcode)) return 'CODE128 inválido.';
  if (barcodeType === 'INTERNO' && !/^[A-Za-z0-9._-]{3,64}$/.test(barcode)) return 'Código interno inválido.';
  return null;
}

function validateStep(stepToValidate: number): boolean {
  const nextErrors: Record<string, string> = { ...fieldErrors.value };
  const clear = (k: string) => {
    if (nextErrors[k]) delete nextErrors[k];
  };
  const fail = (k: string, msg: string) => {
    nextErrors[k] = msg;
  };

  if (stepToValidate === 1) {
    const sku = normalizeSku(form.sku);
    if (!/^[A-Z0-9._-]{3,64}$/.test(sku)) fail('sku', 'SKU inválido (A-Z 0-9 . _ -, 3-64).');
    else clear('sku');

    if (String(form.name || '').trim().length < 3 || String(form.name || '').trim().length > 160) {
      fail('name', 'Nombre requerido (3-160).');
    } else clear('name');

    if (!form.item_type) fail('item_type', 'Tipo de ítem requerido.');
    else clear('item_type');

    if (!form.status) fail('status', 'Estado requerido.');
    else clear('status');

    if (!form.category_id) fail('category_id', 'Categoría requerida.');
    else clear('category_id');

    if (form.subcategory_id) {
      const sub = categories.value.find((row) => row.id === form.subcategory_id);
      if (!sub || sub.parent_id !== form.category_id) {
        fail('subcategory_id', 'Subcategoría inválida para la categoría seleccionada.');
      } else clear('subcategory_id');
    } else clear('subcategory_id');
  }

  if (stepToValidate === 2) {
    const barcodeError = validateBarcodeFormat(String(form.barcode || '').trim(), form.barcode_type);
    if (barcodeError) fail('barcode', barcodeError);
    else clear('barcode');

    if (!form.barcode.trim()) clear('barcode_type');
    if (form.barcode.trim() && !form.barcode_type) fail('barcode_type', 'barcode_type requerido.');

    if ((form.search_tags || []).length > 15) fail('search_tags', 'Máximo 15 tags.');
    else if ((form.search_tags || []).some((tag) => String(tag).trim().length < 2 || String(tag).trim().length > 24)) {
      fail('search_tags', 'Cada tag debe tener entre 2 y 24 caracteres.');
    } else clear('search_tags');
  }

  if (stepToValidate === 3) {
    if (!form.uom_base) fail('uom_base', 'Unidad base requerida.');
    else clear('uom_base');
    if (!form.uom_purchase) fail('uom_purchase', 'Unidad de compra requerida.');
    else clear('uom_purchase');
    if (!form.uom_sale) fail('uom_sale', 'Unidad de venta requerida.');
    else clear('uom_sale');

    if (showConversions.value) {
      const seen = new Set<string>();
      let invalid = false;
      for (const row of form.uom_conversions) {
        const to = String(row.to_uom || '').trim();
        if (!to) {
          invalid = true;
          break;
        }
        if (seen.has(to)) {
          invalid = true;
          break;
        }
        seen.add(to);
        if (!decimalIsValid(row.factor) || Number(row.factor) <= 0) {
          invalid = true;
          break;
        }
      }
      if (invalid) fail('uom_conversions', 'Conversión inválida. factor > 0 y unidad destino sin duplicados.');
      else clear('uom_conversions');
    } else {
      clear('uom_conversions');
    }

    if (form.controls_stock && (!decimalIsValid(form.min_qty) || Number(form.min_qty) < 0)) {
      fail('min_qty', 'Debe ser >= 0.');
    } else clear('min_qty');

    if (form.allow_fraction && (!decimalIsValid(form.rounding_increment) || Number(form.rounding_increment) <= 0)) {
      fail('rounding_increment', 'Debe ser > 0.');
    } else clear('rounding_increment');
  }

  if (stepToValidate === 4 && form.controls_stock) {
    if (!form.enabled_branch_ids.length) fail('enabled_branch_ids', 'Selecciona al menos 1 sucursal activa.');
    else clear('enabled_branch_ids');

    if (!form.default_branch_id) fail('default_branch_id', 'Sucursal por defecto requerida.');
    else if (!form.enabled_branch_ids.includes(form.default_branch_id)) {
      fail('default_branch_id', 'Debe pertenecer a sucursales habilitadas.');
    } else clear('default_branch_id');

    if (!form.default_warehouse_id) fail('default_warehouse_id', 'Almacén por defecto requerido.');
    else clear('default_warehouse_id');

    if (!decimalGE(form.min_stock, 0)) fail('min_stock', 'Debe ser >= 0.');
    else clear('min_stock');

    if (form.max_stock.trim() && !decimalGE(form.max_stock, 0)) fail('max_stock', 'Debe ser >= 0.');
    else if (form.max_stock.trim() && Number(form.max_stock) < Number(form.min_stock)) {
      fail('max_stock', 'Debe ser >= min_stock.');
    } else clear('max_stock');

    if (!decimalGE(form.reorder_point, 0)) fail('reorder_point', 'Debe ser >= 0.');
    else if (form.max_stock.trim() && Number(form.reorder_point) > Number(form.max_stock)) {
      fail('reorder_point', 'Debe ser <= max_stock.');
    } else clear('reorder_point');

    if (!decimalIsValid(form.reorder_qty) || Number(form.reorder_qty) <= 0) fail('reorder_qty', 'Debe ser > 0.');
    else clear('reorder_qty');
  }

  if (stepToValidate === 5) {
    if (form.controls_stock) {
      if (!decimalGE(form.initial_cost, 0)) fail('initial_cost', 'Costo inicial inválido (>=0).');
      else clear('initial_cost');
      if (!decimalGE(form.standard_cost, 0)) fail('standard_cost', 'Costo estándar inválido (>=0).');
      else clear('standard_cost');
      if (!/^[A-Z]{3}$/.test(String(form.currency || '').trim().toUpperCase())) fail('currency', 'Moneda ISO-4217 inválida.');
      else clear('currency');
      if (form.last_known_cost.trim() && !decimalGE(form.last_known_cost, 0)) fail('last_known_cost', 'Debe ser >= 0.');
      else clear('last_known_cost');
    }

    if (form.purchase_enabled) {
      if (form.lead_time_days !== null && (form.lead_time_days < 0 || form.lead_time_days > 365)) {
        fail('lead_time_days', 'Debe estar entre 0 y 365.');
      } else clear('lead_time_days');

      if (form.purchase_moq.trim() && (!decimalIsValid(form.purchase_moq) || Number(form.purchase_moq) <= 0)) {
        fail('purchase_moq', 'Debe ser > 0.');
      } else clear('purchase_moq');

      if (
        form.purchase_multiple.trim() &&
        (!decimalIsValid(form.purchase_multiple) || Number(form.purchase_multiple) <= 0)
      ) {
        fail('purchase_multiple', 'Debe ser > 0.');
      } else clear('purchase_multiple');
    }

    if (form.sales_enabled) {
      if (form.suggested_price.trim() && !decimalGE(form.suggested_price, 0)) {
        fail('suggested_price', 'Debe ser >= 0.');
      } else clear('suggested_price');

      if (form.min_sale_price.trim() && !decimalGE(form.min_sale_price, 0)) {
        fail('min_sale_price', 'Debe ser >= 0.');
      } else if (
        form.suggested_price.trim() &&
        form.min_sale_price.trim() &&
        Number(form.min_sale_price) > Number(form.suggested_price)
      ) {
        fail('min_sale_price', 'Debe ser <= suggested_price.');
      } else clear('min_sale_price');

      if (typeof form.visible_pos !== 'boolean') fail('visible_pos', 'Campo requerido.');
      else clear('visible_pos');
    }
  }

  if (stepToValidate === 6) {
    if (!form.tax_profile_id) fail('tax_profile_id', 'Perfil fiscal requerido.');
    else clear('tax_profile_id');

    if (!form.tax_treatment) fail('tax_treatment', 'Tratamiento fiscal requerido.');
    else clear('tax_treatment');

    if (form.use_expiry && form.controls_stock) {
      if (!form.shelf_life_days || form.shelf_life_days <= 0) fail('shelf_life_days', 'Debe ser > 0.');
      else clear('shelf_life_days');
    } else clear('shelf_life_days');
  }

  fieldErrors.value = nextErrors;
  return Object.keys(nextErrors).filter((key) => nextErrors[key]).length === 0;
}

async function validateSkuAsync(): Promise<boolean> {
  clearFieldError('sku');
  const sku = normalizeSku(form.sku);
  form.sku = sku;
  if (!sku) return true;

  if (!/^[A-Z0-9._-]{3,64}$/.test(sku)) {
    setFieldError('sku', 'SKU inválido (A-Z 0-9 . _ -, 3-64).');
    return false;
  }

  const lookup = await listInventoryItems({ sku_exact: sku, limit: 2, offset: 0 });
  const duplicate = lookup.results.some((row) => row.id !== currentItemId.value);
  if (duplicate) {
    setFieldError('sku', 'SKU ya existe en la empresa activa.');
    return false;
  }
  return true;
}

async function validateBarcodeAsync(): Promise<boolean> {
  clearFieldError('barcode');
  clearFieldError('barcode_type');
  const barcode = String(form.barcode || '').trim();
  form.barcode = barcode;
  if (!barcode) return true;

  const formatError = validateBarcodeFormat(barcode, form.barcode_type);
  if (formatError) {
    setFieldError('barcode', formatError);
    return false;
  }

  const lookup = await listInventoryItems({ barcode_exact: barcode, limit: 2, offset: 0 });
  const duplicate = lookup.results.some((row) => row.id !== currentItemId.value);
  if (duplicate) {
    setFieldError('barcode', 'Barcode ya existe en la empresa activa.');
    return false;
  }
  return true;
}

function buildPayload(): InventoryItemUpsertPayload {
  const payload: InventoryItemUpsertPayload = {
    sku: normalizeSku(form.sku),
    name: String(form.name || '').trim(),
    item_type: form.item_type,
    status: form.status,
    short_name: String(form.short_name || '').trim(),
    invoice_name: String(form.invoice_name || '').trim(),
    brand_id: form.brand_id,
    category_id: form.category_id,
    subcategory_id: form.subcategory_id,
    description: String(form.description || '').trim(),

    barcode: String(form.barcode || '').trim(),
    barcode_type: form.barcode_type,
    alternate_code: String(form.alternate_code || '').trim(),
    search_tags: (form.search_tags || []).map((tag) => String(tag).trim()).filter(Boolean),
    purchase_enabled: Boolean(form.purchase_enabled),
    sales_enabled: Boolean(form.sales_enabled),
    controls_stock: Boolean(form.controls_stock),
    transfer_enabled: Boolean(form.controls_stock && form.transfer_enabled),
    allow_returns: Boolean(form.allow_returns),

    uom: form.uom_base,
    uom_base: form.uom_base,
    uom_purchase: form.uom_purchase,
    uom_sale: form.uom_sale,
    uom_conversions: form.uom_conversions
      .filter((row) => row.to_uom && row.factor.trim())
      .map((row) => ({
        to_uom: row.to_uom as UomCode,
        factor: row.factor.trim(),
      })),
    allow_fraction: Boolean(form.allow_fraction),
    min_qty: form.min_qty.trim() || '0.0000',
    rounding_increment: form.rounding_increment.trim() || '0.0000',

    enabled_branch_ids: form.enabled_branch_ids.map((v) => Number(v)),
    default_branch_id: toNullableNumber(form.default_branch_id),
    default_warehouse_id: toNullableNumber(form.default_warehouse_id),
    min_stock: form.min_stock.trim() || '0.0000',
    max_stock: form.max_stock.trim() || '0.0000',
    reorder_point: form.reorder_point.trim() || '0.0000',
    reorder_qty: form.reorder_qty.trim() || '0.0000',
    allow_negative_stock: Boolean(form.allow_negative_stock),
    reserve_enabled: Boolean(form.reserve_enabled),
    internal_location: String(form.internal_location || '').trim(),

    costing_method: 'MOVING_WEIGHTED_AVG',
    initial_cost: form.initial_cost.trim() || '0.000000',
    standard_cost: form.standard_cost.trim() || '0.000000',
    currency: String(form.currency || 'NIO').trim().toUpperCase(),
    last_known_cost: form.last_known_cost.trim() || '0.000000',
    preferred_supplier_id: toNullableNumber(form.preferred_supplier_id),
    supplier_item_code: String(form.supplier_item_code || '').trim(),
    lead_time_days: form.lead_time_days,
    purchase_moq: form.purchase_moq.trim() || '0.0000',
    purchase_multiple: form.purchase_multiple.trim() || '0.0000',
    suggested_price: form.suggested_price.trim() || '0.000000',
    min_sale_price: form.min_sale_price.trim() || '0.000000',
    allow_discount: Boolean(form.allow_discount),
    visible_pos: Boolean(form.visible_pos),
    visible_quote: Boolean(form.visible_quote),
    visible_invoice: Boolean(form.visible_invoice),

    tax_profile_id: toNullableNumber(form.tax_profile_id),
    tax_treatment: form.tax_treatment,
    invoice_description: String(form.invoice_description || '').trim(),
    use_lot: Boolean(form.use_lot),
    use_serial: Boolean(form.use_serial),
    use_expiry: Boolean(form.use_expiry),
    shelf_life_days: form.use_expiry ? toNullableNumber(form.shelf_life_days) : null,
    quality_control_required: Boolean(form.quality_control_required),
    allow_return_to_stock: Boolean(form.allow_return_to_stock),
    is_active: form.status === 'ACTIVO',
  };

  if (form.item_type === 'SERVICIO') {
    payload.controls_stock = false;
    payload.transfer_enabled = false;
    payload.enabled_branch_ids = [];
    payload.default_branch_id = null;
    payload.default_warehouse_id = null;
    payload.use_lot = false;
    payload.use_serial = false;
    payload.use_expiry = false;
    payload.shelf_life_days = null;
  }

  if (!form.purchase_enabled) {
    payload.preferred_supplier_id = null;
    payload.supplier_item_code = '';
    payload.lead_time_days = null;
    payload.purchase_moq = '0.0000';
    payload.purchase_multiple = '0.0000';
  }

  if (!form.sales_enabled) {
    payload.suggested_price = '0.000000';
    payload.min_sale_price = '0.000000';
    payload.visible_pos = false;
    payload.visible_quote = false;
    payload.visible_invoice = false;
  }

  return payload;
}

function mapBackendError(error: unknown): void {
  if (!isAxiosError(error)) return;
  const data = error.response?.data as
    | {
        code?: string;
        detail?: string;
        error?: {
          message?: string;
          details?: Record<string, unknown> & { code?: string; detail?: string };
        };
        [key: string]: unknown;
      }
    | undefined;

  const details = (data?.error?.details || {}) as Record<string, unknown> & { code?: string; detail?: string };
  const code = String(data?.code || details.code || '');
  const detailMessage = String(data?.detail || details.detail || data?.error?.message || '');
  if (code === 'INVENTORY_DUPLICATE_SKU') {
    setFieldError('sku', 'SKU ya existe en la empresa activa.');
    step.value = 1;
    return;
  }
  if (code === 'INVENTORY_DUPLICATE_BARCODE') {
    setFieldError('barcode', 'Barcode ya existe en la empresa activa.');
    step.value = 2;
    return;
  }
  if (code === 'VALIDATION_ERROR' || code === 'INVENTORY_VALIDATION_ERROR') {
    const payload = Object.keys(details).length ? details : (data || {});
    const keys = Object.keys(payload).filter((key) => key !== 'detail' && key !== 'code');
    if (keys.length) {
      const first = keys[0];
      if (!first) {
        Notify.create({ type: 'negative', message: 'Validación inválida.' });
        return;
      }
      const val = payload[first];
      const msg = stringifyValidationValue(val);
      setFieldError(first, msg);
      return;
    }
  }
  if (detailMessage) {
    Notify.create({ type: 'negative', message: detailMessage });
  }
}

async function goNext(): Promise<void> {
  const ok = validateStep(step.value);
  if (!ok) return;
  if (step.value === 1) {
    const unique = await validateSkuAsync();
    if (!unique) return;
  }
  if (step.value === 2 && form.barcode.trim()) {
    const unique = await validateBarcodeAsync();
    if (!unique) return;
  }
  if (step.value < 6) step.value += 1;
}

function goPrev(): void {
  if (step.value > 1) step.value -= 1;
}

async function save(): Promise<void> {
  if (!canSubmit.value) return;
  for (let i = 1; i <= 6; i += 1) {
    const ok = validateStep(i);
    if (!ok) {
      step.value = i;
      return;
    }
  }

  const skuUnique = await validateSkuAsync();
  if (!skuUnique) {
    step.value = 1;
    return;
  }

  if (form.barcode.trim()) {
    const barcodeUnique = await validateBarcodeAsync();
    if (!barcodeUnique) {
      step.value = 2;
      return;
    }
  }

  submitting.value = true;
  try {
    const payload = buildPayload();
    if (isEdit.value && currentItemId.value) {
      await patchInventoryItem(currentItemId.value, payload);
      Notify.create({
        type: 'positive',
        message: 'Ítem actualizado.',
      });
    } else {
      const created = await createInventoryItem(payload);
      Notify.create({
        type: 'positive',
        message:
          'Ítem creado. Sucursales habilitadas: ' +
          String(payload.enabled_branch_ids?.length || 0) +
          ' · Control stock: ' +
          (payload.controls_stock ? 'Sí' : 'No'),
      });
      await router.replace({
        path: `/inventario/items/${created.id}/editar`,
        query: { saved: '1' },
      });
    }
  } catch (error: unknown) {
    mapBackendError(error);
    if (!isAxiosError(error)) {
      Notify.create({ type: 'negative', message: error instanceof Error ? error.message : String(error) });
    }
  } finally {
    submitting.value = false;
  }
}

function goBack(): void {
  void router.push(UI_ROUTE_PATHS.inventoryItems);
}

function onKeydown(event: KeyboardEvent): void {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'enter') {
    event.preventDefault();
    void save();
  }
}

watch(
  () => form.item_type,
  (value) => {
    if (value === 'SERVICIO') {
      form.controls_stock = false;
      form.transfer_enabled = false;
    }
  },
);

watch(
  () => form.controls_stock,
  (enabled) => {
    if (!enabled) {
      form.transfer_enabled = false;
      form.enabled_branch_ids = [];
      form.default_branch_id = null;
      form.default_warehouse_id = null;
      form.use_lot = false;
      form.use_serial = false;
      form.use_expiry = false;
      form.shelf_life_days = null;
    }
  },
);

watch(
  () => form.category_id,
  () => {
    clearFieldError('category_id');
    const available = new Set(subcategoryOptions.value.map((row) => row.value));
    if (form.subcategory_id && !available.has(form.subcategory_id)) {
      form.subcategory_id = null;
    }
  },
);

watch(
  () => form.enabled_branch_ids.slice(),
  (ids) => {
    if (!ids.length) {
      form.default_branch_id = null;
      form.default_warehouse_id = null;
      return;
    }
    if (form.default_branch_id && !ids.includes(form.default_branch_id)) {
      form.default_branch_id = null;
      form.default_warehouse_id = null;
    }
  },
);

watch(
  () => form.default_branch_id,
  (branchId) => {
    void loadWarehousesByBranch(branchId);
  },
);

onMounted(() => {
  window.addEventListener('keydown', onKeydown);
  void loadCatalogs()
    .then(() => loadItemIfNeeded())
    .catch((error: unknown) => {
      Notify.create({
        type: 'negative',
        message: error instanceof Error ? error.message : 'No se pudieron cargar catálogos de inventario.',
      });
    });
});

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown);
});
</script>
