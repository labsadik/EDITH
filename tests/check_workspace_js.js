// Execute the real login script with a deliberately slow network.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../dashboard/static/login.html'), 'utf8');
const code = html.split('<script>')[1].split('</script>')[0];
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {value: '', style: {}, textContent: '',
    focus() {}, addEventListener() {}, classList: {add() {}, remove() {}}});
  return elements.get(id);
}
const saved = new Map();
let requests = 0, release;
const context = vm.createContext({
  document: {getElementById: element},
  localStorage: {getItem: () => null, removeItem() {}},
  sessionStorage: {setItem: (key, value) => saved.set(key, value)},
  location: {href: '', replace() {}},
  fetch: () => {requests++; return new Promise(resolve => {release = resolve;});},
});
vm.runInContext(code, context);
(async () => {
  element('key').value = 'ABC234';
  const first = vm.runInContext('doLogin()', context);
  const duplicate = vm.runInContext('doLogin()', context);
  assert.equal(requests, 1, 'double-click must not submit two pairing requests');
  assert.equal(element('connect-btn').disabled, true);
  release({json: async () => ({ok: false})});
  await Promise.all([first, duplicate]);
  assert.equal(element('connect-btn').disabled, false);
  assert.equal(element('err').textContent, 'Invalid or expired key');
  element('key').value = 'ABC234';
  const retry = vm.runInContext('doLogin()', context);
  release({json: async () => ({ok: true, token: 'test-only'})});
  await retry;
  assert.equal(saved.get('jarvis_token'), 'test-only');
  assert.equal(context.location.href, '/');
  console.log('Workspace login JS: pending, double-click guard, error recovery, successful pairing PASS');
})().catch(error => {console.error(error); process.exitCode = 1;});
