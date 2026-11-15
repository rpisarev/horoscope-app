// @vitest-environment node
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { expect, it } from 'vitest'

it('blocks GHSA-hmx5-qpq5-p643 prototype pollution even with an altered indexOf', () => {
  // The advisory's mutation runs in a disposable child, never the test runner.
  // This probes the installed package only; no server or external target is used.
  const output = execFileSync(process.execPath, ['--input-type=module', '-e', `
    import Swiper from 'swiper';
    const original = Array.prototype.indexOf;
    try {
      Array.prototype.indexOf = () => -1;
      Swiper.extendDefaults(JSON.parse('{"__proto__":{"stab029Polluted":true}}'));
      process.stdout.write(JSON.stringify({ polluted: ({}).stab029Polluted === true }));
    } finally {
      Array.prototype.indexOf = original;
      delete Object.prototype.stab029Polluted;
    }
  `], {
    cwd: fileURLToPath(new URL('../..', import.meta.url)),
    encoding: 'utf8',
    timeout: 5000,
  })
  expect(JSON.parse(output)).toEqual({ polluted: false })
})
