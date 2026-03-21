<template>
  <div ref="chartEl" class="interactive-chart" :style="{ height }" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent } from 'echarts/components';
import { init, use, type EChartsType } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

use([BarChart, LineChart, GridComponent, CanvasRenderer]);

const props = withDefaults(
  defineProps<{
    option: Record<string, unknown>;
    height?: string;
  }>(),
  {
    height: '360px',
  },
);

const emit = defineEmits<{
  (event: 'point-click', payload: Record<string, unknown>): void;
}>();

const chartEl = ref<HTMLDivElement | null>(null);
let instance: EChartsType | null = null;

function resize() {
  instance?.resize();
}

function render() {
  if (!chartEl.value) return;
  if (!instance) {
    instance = init(chartEl.value);
    instance.on('click', (params: unknown) => {
      emit('point-click', {
        name: (params as { name?: string }).name,
        value: (params as { value?: unknown }).value,
        seriesName: (params as { seriesName?: string }).seriesName,
        data: (params as { data?: unknown }).data,
      });
    });
  }
  instance.setOption(props.option, true);
}

onMounted(() => {
  render();
  window.addEventListener('resize', resize);
});

watch(
  () => props.option,
  () => {
    render();
  },
  { deep: true },
);

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize);
  if (instance) {
    instance.dispose();
    instance = null;
  }
});
</script>

<style scoped>
.interactive-chart {
  width: 100%;
  min-height: 280px;
}
</style>
