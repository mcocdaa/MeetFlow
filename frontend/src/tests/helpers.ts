/**
 * Test rendering helper for Naive UI components.
 *
 * Popovers, drawers, dialogs and dropdowns teleport to `document.body`: query them with
 * the global `screen` helpers, never with the render result `container`.
 *
 * `n-data-table` reports zero width under jsdom: do not enable fixed columns or virtual
 * scrolling, and assert pagination through request parameters/`itemCount`, not scrolling.
 */

import { render, type RenderOptions, type RenderResult } from '@testing-library/vue'
import { NConfigProvider, NDialogProvider, NMessageProvider, dateZhCN, zhCN } from 'naive-ui'
import { defineComponent, h, type Component } from 'vue'

import { naiveThemeOverrides } from '../theme/naive'

export function renderWithProviders<C>(
  component: C,
  options: RenderOptions<C> = {},
): RenderResult {
  const { props, ...renderOptions } = options
  const Wrapper = defineComponent({
    name: 'TestProviders',
    setup() {
      return () =>
        h(
          NConfigProvider,
          { themeOverrides: naiveThemeOverrides, locale: zhCN, dateLocale: dateZhCN },
          {
            default: () =>
              h(NMessageProvider, null, {
                default: () =>
                  h(NDialogProvider, null, {
                    default: () => h(component as Component, props as Record<string, unknown>),
                  }),
              }),
          },
        )
    },
  })

  return render(Wrapper, renderOptions as RenderOptions<typeof Wrapper>)
}
