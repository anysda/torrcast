// Настоящий `api.js`: отчёт позиции обязан дойти до fetch, а не попасть в catch
// до сети из-за перекрытого имени параметра.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'static', 'api.js'), 'utf8');
const calls = [];
const ctx = {
  console,
  JSON,
  document: { createElement: () => ({ canPlayType: () => '' }), cookie: '' },
  fetch: async (url, init) => {
    calls.push({ url, method: init.method, body: JSON.parse(init.body) });
    return { status: 200, json: async () => ({ finish: 2587.512 }) };
  },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(source, ctx, { filename: 'api.js' });

(async () => {
  const position = { key: 'show-key', phase: 'playing', pos: 41.25, dur: 2587.512 };
  const answer = await vm.runInContext(`TCApi.position(${JSON.stringify(position)})`, ctx);
  process.stdout.write(JSON.stringify({ calls, answer }) + '\n');
})().catch((error) => { process.stderr.write(String(error.stack || error)); process.exitCode = 1; });
