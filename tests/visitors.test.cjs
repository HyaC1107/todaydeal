const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('templates/visitors.js', 'utf8');

async function run({storage = new Map(), hostname = 'hyac1107.github.io',
  pathname = '/todaydeal/', count = '1,234', ok = true, blocked = false,
  failedPixel = false, brokenStorage = false, now = '2026-09-17T14:59:00Z'} = {}) {
  let pixels = 0, requests = 0;
  const output = {};
  const box = {dataset: {counterCode: 'example'}, hidden: true, querySelector: () => output};
  const context = {
    location: {hostname, pathname},
    Date: class extends Date {static now() {return Date.parse(now);}},
    document: {
      querySelector: () => box, visibilityState: 'visible',
      addEventListener() {}, removeEventListener() {},
      createElement: () => ({dataset: {}}),
      head: {appendChild(script) {
        context.window.goatcounter = {filter: () => blocked, url: () => 'https://example.goatcounter.com/count'};
        script.onload();
      }},
    },
    window: {}, navigator: {}, AbortSignal,
    localStorage: {
      getItem: k => {if (brokenStorage) throw Error('blocked'); return storage.get(k);},
      setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k),
    },
    fetch: async () => {requests++; return {ok, json: async () => ({count})};},
    Image: class {set src(value) {pixels++; queueMicrotask(() => failedPixel ? this.onerror() : this.onload());}},
    setTimeout, clearTimeout,
  };
  vm.runInNewContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  return {pixels, requests, box, output, storage};
}

test('shared daily marker suppresses refresh and category navigation; resets at KST midnight', async () => {
  const first = await run();
  assert.equal(first.pixels, 1);
  assert.equal(first.output.textContent, '1,234회');
  assert.equal(first.box.hidden, false);
  assert.equal((await run({storage: first.storage})).pixels, 0);
  assert.equal((await run({storage: first.storage, pathname: '/todaydeal/c/kitchen.html'})).pixels, 0);
  assert.equal((await run({storage: first.storage, now: '2026-09-17T15:00:00Z'})).pixels, 1);
});
test('local previews and other sites are excluded', async () => {
  assert.equal((await run({hostname: 'localhost'})).requests, 0);
  assert.equal((await run({pathname: '/'})).pixels, 0);
});
test('API errors and invalid data never display made-up numbers', async () => {
  assert.equal((await run({ok: false})).box.hidden, true);
  assert.equal((await run({count: '<script>'})).box.hidden, true);
});
test('unsent visits are not marked; storage restrictions fail closed', async () => {
  assert.equal((await run({failedPixel: true})).storage.size, 0);
  assert.equal((await run({blocked: true})).pixels, 0);
  assert.equal((await run({brokenStorage: true})).pixels, 0);
});
