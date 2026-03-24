import { mount } from '@vue/test-utils';
import { defineComponent } from 'vue';
import { describe, expect, it, vi } from 'vitest';

import { useRetailShortcuts } from './useRetailShortcuts';

describe('useRetailShortcuts', () => {
  it('maps F2 and Enter to the configured handlers', () => {
    const focusSearch = vi.fn();
    const confirm = vi.fn();

    const Harness = defineComponent({
      setup() {
        useRetailShortcuts({ focusSearch, confirm });
        return () => null;
      },
    });

    const wrapper = mount(Harness);

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'F2' }));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));

    expect(focusSearch).toHaveBeenCalledTimes(1);
    expect(confirm).toHaveBeenCalledTimes(1);

    wrapper.unmount();
  });

  it('ignores shortcuts when suspended', () => {
    const focusSearch = vi.fn();
    const cancel = vi.fn();

    const Harness = defineComponent({
      setup() {
        useRetailShortcuts({
          focusSearch,
          cancel,
          isSuspended: () => true,
        });
        return () => null;
      },
    });

    const wrapper = mount(Harness);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'F2' }));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));

    expect(focusSearch).not.toHaveBeenCalled();
    expect(cancel).toHaveBeenCalledTimes(1);

    wrapper.unmount();
  });
});
