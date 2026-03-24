import { mount } from '@vue/test-utils';
import { defineComponent, h, ref } from 'vue';
import { describe, expect, it, vi } from 'vitest';

import { useRetailScannerInput } from './useRetailScannerInput';

describe('useRetailScannerInput', () => {
  it('emits a normalized scan when receiving wedge stream + enter', () => {
    const onScan = vi.fn();
    const enabled = ref(true);

    const Harness = defineComponent({
      setup() {
        useRetailScannerInput({
          enabled: () => enabled.value,
          onScan,
        });
        return () => null;
      },
    });

    const wrapper = mount(Harness);

    for (const key of ['7', '5', '0', '1', '2', '3']) {
      window.dispatchEvent(new KeyboardEvent('keydown', { key }));
    }
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));

    expect(onScan).toHaveBeenCalledTimes(1);
    expect(onScan.mock.calls[0]?.[0]?.normalized).toBe('750123');

    wrapper.unmount();
  });

  it('ignores input when scanner mode is disabled', () => {
    const onScan = vi.fn();
    const enabled = ref(false);

    const Harness = defineComponent({
      setup() {
        useRetailScannerInput({
          enabled: () => enabled.value,
          onScan,
        });
        return () => null;
      },
    });

    const wrapper = mount(Harness);
    for (const key of ['A', 'B', 'C', '1', '2', '3']) {
      window.dispatchEvent(new KeyboardEvent('keydown', { key }));
    }
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));

    expect(onScan).not.toHaveBeenCalled();

    wrapper.unmount();
  });

  it('does not capture manual typing on editable fields by default', () => {
    const onScan = vi.fn();

    const Harness = defineComponent({
      setup() {
        useRetailScannerInput({
          enabled: () => true,
          onScan,
        });
        return () => h('input', { 'data-test': 'manual-input' });
      },
    });

    const wrapper = mount(Harness);
    const input = wrapper.get('[data-test="manual-input"]');
    const inputEl = input.element as HTMLInputElement;
    inputEl.focus();

    for (const key of ['1', '2', '3', '4', '5', '6']) {
      inputEl.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    }
    inputEl.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(onScan).not.toHaveBeenCalled();

    wrapper.unmount();
  });
});
