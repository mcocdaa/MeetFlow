import '@testing-library/jest-dom/vitest'

import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/vue'

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// Naive UI relies on browser APIs that jsdom does not implement. Keep these stubs
// global so individual tests do not need to patch the environment themselves.
globalThis.ResizeObserver = ResizeObserverStub

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  configurable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false,
  }),
})

Object.defineProperty(Element.prototype, 'scrollTo', {
  writable: true,
  configurable: true,
  value: () => {},
})

afterEach(() => cleanup())
