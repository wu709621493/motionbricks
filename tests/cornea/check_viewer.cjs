// Dependency-free script/geometry checks. This is not a real-browser layout test.
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const file = path.resolve(__dirname, '../../docs/cornea/generated/index.html');
const html = fs.readFileSync(file, 'utf8');
const data = JSON.parse(html.match(/<script id="cornea-data" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const script = html.match(/<\/script><script>([\s\S]*?)<\/script>/)[1];
let commands = 0;
const nodes = {};
const ctx = new Proxy({}, {get: (_, key) => (...args) => {
  for (const n of args) if (typeof n === 'number') assert(Number.isFinite(n), key+' has nonfinite coordinate');
  commands++;
}, set: () => true});
for (const id of ['cornea-data','healthy','keratoconus','healthy-map','keratoconus-map','section',
                  'healthy-stats','keratoconus-stats','surface','exag','exag-value','oblique','front','side','reset']) {
  assert(html.includes('id="'+id+'"'), 'missing markup '+id);
  nodes[id] = {value: id === 'surface' ? 'shell' : '1', textContent: id === 'cornea-data' ? JSON.stringify(data) : '',
    clientWidth: 520, clientHeight: id === 'section' ? 265 : 300,
    handlers: {}, getContext: () => ctx, setPointerCapture: () => {},
    addEventListener(name, fn) {this.handlers[name] = fn;}};
}
const sandbox = {document: {getElementById: id => nodes[id], querySelector: () => ({})},
  window: {devicePixelRatio: 1}, ResizeObserver: class {observe() {}}, console};
vm.createContext(sandbox);vm.runInContext(script, sandbox, {timeout: 15000});
const lab = sandbox.window.corneaLab;
let maxError=0;
for (const m of data.models) {
  const n=m.surface_vertex_count;
  for (let i=0;i<n;i++) {
    const [x,y,z]=m.vertices_mm[i], s=lab.sample(m.parameters,x,y);
    maxError=Math.max(maxError,Math.abs(z-s[0]),Math.abs(m.vertices_mm[i+n][2]-s[1]),
      Math.abs(m.axial_thickness_um[i]/1000-s[2]));
  }
}
assert(maxError < 1e-10, 'Python/JavaScript geometry mismatch');
for (const id of ['front','side','oblique']) {nodes[id].onclick();assert(commands>0);}
nodes.surface.value='posterior';nodes.surface.onchange();
nodes.surface.value='anterior';nodes.surface.onchange();
nodes.exag.oninput({target: {value: '2'}});assert.equal(nodes['exag-value'].value,'2.0×');
nodes.reset.onclick();assert.equal(nodes.surface.value,'shell');assert.equal(nodes.exag.value,'1');
nodes.healthy.handlers.pointerdown({clientX:10,clientY:10,pointerId:1});
nodes.healthy.handlers.pointermove({clientX:70,clientY:35});
nodes.healthy.handlers.pointerup();
assert(vm.runInContext('yaw !== 0.35 && tilt !== 0.85',sandbox), 'drag did not update shared view');
assert(!/\bfetch\s*\(|XMLHttpRequest|WebSocket|<script[^>]+src=/.test(html),'external runtime dependency');
console.log(JSON.stringify({status:'PASS', max_python_javascript_error_mm:maxError,
  canvas_commands_checked:commands, real_browser_test:false}));
