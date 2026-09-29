// Отказ карточки глазами настоящих `app.js` и `api.js`: ответ сервера приходит первым
// доводом (`{status, body}`), каталог страницы - вторым; наружу одной строкой JSON то, что
// `TCApi.card` отдал карточке, и строка, которую из этого нарисует `TC.say`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

async function main() {
  const answer = JSON.parse(process.argv[2]);
  const context = {
    fetch: async () => ({
      ok: answer.status >= 200 && answer.status < 300,
      status: answer.status,
      headers: { get: () => null },
      json: async () => answer.body,
    }),
    document: { addEventListener: () => {} },
    window: { addEventListener: () => {} },
    URLSearchParams, JSON, Promise, console,
  };
  vm.createContext(context);
  for (const name of ['app.js', 'api.js']) {
    const source = fs.readFileSync(path.join(__dirname, '..', '..', 'web', 'static', name), 'utf8');
    vm.runInContext(source, context);
  }
  const tc = vm.runInContext('TC', context);
  tc.phrases = JSON.parse(process.argv[3]);
  const api = vm.runInContext('TCApi', context);
  const said = await api.card('movie:test:2000', 'test', false, null, undefined, false);
  const reason = said.refused;
  process.stdout.write(JSON.stringify({
    refused: reason, whole: said.whole === true,
    text: reason ? tc.say(reason.key, reason.values) : null,
  }) + '\n');
}

main();
