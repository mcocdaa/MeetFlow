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
import { defineComponent, h, nextTick, shallowRef, type Component } from 'vue'

import { naiveThemeOverrides } from '../theme/naive'

export function renderWithProviders<C>(
  component: C,
  options: RenderOptions<C> = {},
): RenderResult {
  const { props: initialProps, attrs, ...renderOptions } = options
  // `rerender(newProps)` replaces the props passed to the wrapped component, because
  // testing-library's own rerender would target the provider wrapper instead.
  // `attrs` (event listeners and fallthrough attributes) belong to the wrapped component too.
  const componentProps = shallowRef<Record<string, unknown> | undefined>({
    ...(initialProps as Record<string, unknown> | undefined),
    ...(attrs as Record<string, unknown> | undefined),
  })
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
                    default: () => h(component as Component, componentProps.value),
                  }),
              }),
          },
        )
    },
  })

  const result = render(Wrapper, renderOptions as RenderOptions<typeof Wrapper>)
  return Object.assign(result, {
    rerender: (newProps?: object) => {
      componentProps.value = newProps as Record<string, unknown> | undefined
      return nextTick()
    },
  })
}
