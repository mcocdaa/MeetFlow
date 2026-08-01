import { defineComponent } from 'vue'
import { render, screen } from '@testing-library/vue'
import { afterEach, expect, it, vi } from 'vitest'

import PluginSlot from '../components/PluginSlot.vue'
import { registerPluginSlot } from '../plugins/registry'


it('renders a fixed plugin slot with bounded context', () => {
  const component = defineComponent({
    props: ['context'],
    template: '<output data-testid="slot-context">{{ context.slot }} · {{ context.targetId }}</output>',
  })
  registerPluginSlot('test.slot.context', component)

  render(PluginSlot, {
    props: { slot: 'test.slot.context', targetType: 'meeting', targetId: 'm1', metadata: { safe: true } },
  })

  expect(screen.getByTestId('slot-context')).toHaveTextContent('test.slot.context · m1')
})


it('isolates a plugin slot component that throws during render', () => {
  const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  const broken = defineComponent({ render() { throw new Error('broken slot') } })
  const healthy = defineComponent({ template: '<span>healthy slot</span>' })
  registerPluginSlot('test.slot.isolated', broken)
  registerPluginSlot('test.slot.isolated', healthy)

  render(PluginSlot, {
    props: { slot: 'test.slot.isolated', targetType: 'home', targetId: 'home' },
  })

  expect(screen.getByText('healthy slot')).toBeVisible()
  error.mockRestore()
})

afterEach(() => vi.restoreAllMocks())
