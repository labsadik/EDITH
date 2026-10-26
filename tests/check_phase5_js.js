// Behavioral regression tests for the real inline EDITH phone dashboard JS.
// Runs with Node 20 built-ins only; no browser, model, microphone or tokens.
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(
  path.join(__dirname, '..', 'dashboard', 'static', 'app.html'), 'utf8'
);
const scripts = html.split('<script>').slice(1).map(s => s.split('</script>')[0]);
const code = scripts.find(x => x.includes('const _authToken'));
assert.ok(code, 'phone dashboard inline script not found');

const rows = [];
const elements = new Map();
function el(name) {
  if (!elements.has(name)) {
    const obj = {
      id: name, value: '', className: '', textContent: '', innerHTML: '',
      style: {}, classList: { add() {}, remove() {} },
      addEventListener() {}, querySelector() { return null; },
      appendChild() {}, setAttribute() {},
    };
    elements.set(name, obj);
  }
  return elements.get(name);
}
const feed = el('feed');
feed.children = rows;
feed.appendChild = child => { rows.push(child); };
feed.removeChild = child => { const i = rows.indexOf(child); if (i >= 0) rows.splice(i, 1); };
Object.defineProperty(feed, 'firstElementChild', {get() {return rows[0] || null;}});
feed.scrollHeight = 0;

const timers = new Map();
let nextTimer = 1;
const setTimer = fn => {const id = nextTimer++; timers.set(id, fn); return id;};
const clearTimer = id => {timers.delete(id);};
function flushTimers() {
  for (const [id, fn] of [...timers]) { timers.delete(id); fn(); }
}

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances = [];
  constructor(url) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;
    this.bufferedAmount = 0;
    this.sent = [];
    MockWebSocket.instances.push(this);
  }
  open() { this.readyState = MockWebSocket.OPEN; this.onopen?.(); }
  close(code = 1006) { this.readyState = MockWebSocket.CLOSED; this.onclose?.({code}); }
  message(message) { this.onmessage?.({data: JSON.stringify(message)}); }
  send(data) { this.sent.push(data); }
}

const storage = {jarvis_token: 'test-token', jarvis_key: 'test-key'};
const sessionStorage = {
  getItem(k) {return storage[k] || null;},
  removeItem(k) {delete storage[k];},
};
const requests = [];
let commandMode = 'ok';
const fetchMock = async (url, options) => {
  requests.push({url, options});
  if (url === '/api/session') return {ok:true, status:200, json:async()=>({ok:true})};
  if (url === '/api/command') {
    if (commandMode === 'error') throw new Error('network failed');
    if (commandMode === 'not-ready')
      return {ok:false, status:503, json:async()=>({ok:false})};
    return {ok:true, status:200, json:async()=>({ok:true})};
  }
  return {ok:true, status:200, json:async()=>({ok:true})};
};

const listeners = {};
const context = vm.createContext({
  console,
  URL, Blob, Uint8Array, Int16Array, Float32Array,
  sessionStorage, navigator: {onLine: true},
  location: {
    protocol: 'http:', host: '192.168.1.2:8000', origin:'http://192.168.1.2:8000',
    replace(url) { throw new Error('unexpected redirect: ' + url); },
  },
  document: {
    hidden: false,
    getElementById: el,
    createElement: () => ({
      className:'',textContent:'',innerHTML:'',style:{},
      classList:{add(){}, remove(){}},
      querySelector(){return null;},addEventListener(){}
    }),
    addEventListener(name, callback) {listeners['document:' + name] = callback;},
  },
  window: {
    addEventListener(name, callback) {listeners['window:' + name] = callback;},
  },
  WebSocket: MockWebSocket,
  fetch: fetchMock,
  setTimeout: setTimer, clearTimeout: clearTimer,
  setInterval: setTimer, clearInterval: clearTimer,
  btoa: s => Buffer.from(s, 'binary').toString('base64'),
  // CryptoJS intentionally absent to cover the current no-crypto fallback.
});
vm.runInContext(code, context, {filename:'app.html:inline'});

(async () => {
  assert.equal(MockWebSocket.instances.length, 1, 'must connect on page load');
  const original = MockWebSocket.instances[0];
  original.open();
  original.message({type:'sys', text:'Once only', event_id:'boot:1'});
  assert.equal(rows.filter(r => r.textContent === 'Once only').length, 1);

  original.close();
  flushTimers(); // includes the retry timer; no real network used
  assert.equal(MockWebSocket.instances.length, 2, 'lost WS reconnects automatically');
  const reconnected = MockWebSocket.instances[1];
  reconnected.open();
  reconnected.message({type:'sys', text:'Once only', event_id:'boot:1'});
  assert.equal(rows.filter(r => r.textContent === 'Once only').length, 1,
               'replayed history must not duplicate visible rows');
  reconnected.message({type:'sys', text:'New event', event_id:'boot:2'});
  assert.equal(rows.filter(r => r.textContent === 'New event').length, 1);

  const input = el('inp');
  input.value = 'keep this draft';
  commandMode = 'not-ready';
  await context.doSend();
  assert.equal(input.value, 'keep this draft', '503 must preserve the draft');

  commandMode = 'error';
  const before = requests.filter(r => r.url === '/api/command').length;
  await context.doSend();
  const after = requests.filter(r => r.url === '/api/command').length;
  assert.equal(after - before, 1, 'failed commands must not auto-retry');
  assert.equal(input.value, 'keep this draft', 'unknown delivery keeps draft');

  commandMode = 'ok';
  await context.doSend();
  assert.equal(input.value, '', 'acknowledged command clears draft');
  assert.ok(rows.some(r => r.innerHTML.includes('keep this draft')));

  const audioSocket = new MockWebSocket('audio');
  audioSocket.readyState = MockWebSocket.OPEN;
  audioSocket.bufferedAmount = 65537;
  context._sendVoicePacket(audioSocket, new ArrayBuffer(16));
  assert.equal(audioSocket.sent.length, 0, 'drop stale audio under backpressure');
  audioSocket.bufferedAmount = 0;
  context._sendVoicePacket(audioSocket, new ArrayBuffer(16));
  assert.equal(audioSocket.sent.length, 1, 'send audio when network recovers');

  console.log('Phase 5 phone JS: reconnect, replay, command ack, audio backpressure PASS');
})().catch(e => { console.error(e); process.exitCode = 1; });
