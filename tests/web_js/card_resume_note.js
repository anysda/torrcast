// Слот под кнопками карточки (закладка ушла / нет озвучки / место продолжения):
// настоящий `card.js` в node поверх игрушечного DOM (`page.js`), сюда приезжает только
// то, что встало в ЕДИНСТВЕННЫЙ слот. Решает `tests/test_card_resume_note.py`.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const { Document } = require('./page.js');

const KEY = 'movie:интерстеллар:2014';

function card(doc) {
  const context = {
    document: doc,
    location: { pathname: '/card/' + KEY, search: '' },
    sessionStorage: { getItem: () => null, setItem: () => {} },
    history: { back: () => {} },
    window: {},
    URLSearchParams, JSON, Date, setTimeout, Promise, console,
    // Сторож смотрит на КЛЮЧ фразы, а не на её текст: слова строки на решении владельца
    // (TC-1376) и могут смениться без ведома этого сторожа.
    TC: { say: (name) => name },
    TCTime: { clock: (seconds) => 'clock:' + seconds },
    TCKept: { mark: () => {}, take: () => null },
    TCRouter: { _card: KEY, _picture: '' },
    TCApi: {},
  };
  vm.createContext(context);
  const source = fs.readFileSync(
    path.join(__dirname, '..', '..', 'web', 'static', 'card.js'), 'utf8'
  );
  vm.runInContext(source, context);
  return vm.runInContext('TCCard', context);  // `const` живёт в лексике вставки
}

const BASE = { releases_count: 5, searching: false, voices: [], tv: false };
const SERIES = { label: 's1e2', seasons: [{ n: 1, episodes: [{ n: 2, pos: 30 }] }] };

function slot(data) {
  const row = card(new Document())._buttons({ ...BASE, ...data }, KEY, '', false);
  const el = row.querySelector('.tc-resumes') || row.querySelector('.tc-norel');
  return el ? el.textContent : null;
}

process.stdout.write(JSON.stringify({
  nothing: slot({}),
  noReleases: slot({ releases_count: 0 }),
  resumeSeries: slot({ resumable: true, ...SERIES }),
  resumeMovie: slot({ resumable: true, pos: 612 }),
  movieResumableNoPos: slot({ resumable: true, pos: 0 }),
  bookmarkGoneOverSeriesResume: slot({ resumable: true, ...SERIES, bookmark_gone: true }),
  bookmarkGoneOverMovieResume: slot({ resumable: true, pos: 612, bookmark_gone: true }),
  voiceFallbackOverMovieResume: slot({ resumable: true, pos: 612, voice_fallback: true }),
  bookmarkGoneOverVoiceFallback: slot({ bookmark_gone: true, voice_fallback: true }),
  voiceFallbackAlone: slot({ voice_fallback: true }),
}) + '\n');
