// Обёртки над сеткой: страница вызывает только их, никогда не голый fetch.
// Соседние маршруты (/api/history, /api/shelves, /api/card/*) ещё строят другие
// заходы - падать на 404 или на разрыве сети нельзя, а надо тихо вернуть пустышку
// того же вида, что и настоящий ответ, и дать экрану показать штатное «пусто».
'use strict';

const TCApi = {
  async phrases(lang) {
    const query = lang ? '?lang=' + encodeURIComponent(lang) : '';
    return TCApi._get('/api/phrases' + query, {});
  },

  async state() {
    return TCApi._get('/api/state', null);
  },

  async history() {
    const said = await TCApi._get('/api/history', null);
    return Array.isArray(said && said.items) ? said.items : [];
  },

  // Полки на холодном старте ещё собирает фон, и сервер метит такой ответ заголовком
  // ``X-Torrcast-Partial`` (та же метка, что у карточки): ``partial: true`` значит
  // «переспроси позже», и решает это тот, кто звал, - сама обёртка не ждёт.
  async shelves() {
    const blank = { fresh: [], popular: [], partial: false };
    try {
      const said = await fetch('/api/shelves');
      if (!said.ok) return blank;
      const data = await said.json();
      return {
        fresh: Array.isArray(data && data.fresh) ? data.fresh : [],
        popular: Array.isArray(data && data.popular) ? data.popular : [],
        partial: said.headers.get('X-Torrcast-Partial') === '1',
      };
    } catch (error) {
      return blank;
    }
  },

  // Число включённых источников для «Ищем в N источниках…» (§4.2); нет ответа - ноль,
  // а не выдуманное число.
  async sources() {
    const said = await TCApi._get('/api/web/sources', null);
    return typeof (said && said.count) === 'number' ? said.count : 0;
  },

  async search(query) {
    const said = await TCApi._post('/api/search', { query });
    return Array.isArray(said && said.results) ? said.results : [];
  },

  // Поиск с показом по мере прихода (TC-1126): та же метка ``X-Torrcast-Partial``, что
  // и у карточки (см. `card()` ниже) - `true` значит «список ещё растёт».
  async searchProgress(query) {
    try {
      const said = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, progressive: true }),
      });
      if (!said.ok) return { results: [], partial: false };
      const data = await said.json();
      const results = Array.isArray(data && data.results) ? data.results : [];
      return { results, partial: said.headers.get('X-Torrcast-Partial') === '1' };
    } catch (error) {
      return { results: [], partial: false };
    }
  },

  // Карточка иногда приходит частями (заголовок ``X-Torrcast-Partial``): её самой
  // читает card.js, который и решает, звать ли следующий заход через 2 с.
  async card(key, query) {
    const params = query ? '?query=' + encodeURIComponent(query) : '';
    const url = '/api/card/' + encodeURIComponent(key) + params;
    try {
      const said = await fetch(url);
      if (!said.ok) return { data: null, partial: false };
      const data = await said.json();
      return { data, partial: said.headers.get('X-Torrcast-Partial') === '1' };
    } catch (error) {
      return { data: null, partial: false };
    }
  },

  // Успешный запуск переводит страницу в плеер: до сих пор эту дверь не открывал никто
  // (ни card.js, ни сам api.js), и «Играть» било по продукту, никуда не приводя экран.
  async play(body) {
    // Ящик, лежащий в эту секунду, заказу не принадлежит: показ перепишет его сам,
    // когда поднимется (`player-box.js`), а до тех пор вкладке играть нечего.
    await TCPlayerBox.holdStale();
    const said = await TCApi._post('/api/play', body);
    if (said) TCRouter.go('/play');
    else TCPlayerBox.dropStale();
    return said;
  },

  // Что человек видит на экране (`warm.js`). Ответ странице не нужен: эти плитки она
  // уже нарисовала, а сколько кругов взял прогрев - его дело.
  async seen(tiles) {
    return TCApi._post('/api/seen', { tiles });
  },

  async toTv() {
    return TCApi._post('/api/to-tv', {});
  },

  async toWeb() {
    return TCApi._post('/api/to-web', {});
  },

  async box() {
    return TCApi._get('/api/web/box', {});
  },

  async control(cmd, arg) {
    return TCApi._post('/api/control', arg === undefined ? { cmd } : { cmd, arg });
  },

  // Тело - серия, которую вкладка ДОИГРАЛА: ею сервер отличает запоздавший зов
  // (сторож юнита уже сам доиграл сериал, и повторный переход перепрыгивал бы серию)
  // от настоящей просьбы. Пустое тело - старый зов без имени серии.
  async next(ended) {
    return TCApi._post('/api/next', ended || {});
  },

  // Код ответа, а не тело: 409 ``stale_key`` (второй показ подменил ящик) - решение,
  // которое плееру надо ОТЛИЧИТЬ от сетевого сбоя, а не одинаково проглотить ``null``.
  async position(body) {
    try {
      const said = await fetch('/api/web/position', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return said.status;
    } catch (error) {
      return 0;
    }
  },

  // Слово «ухожу» (TC-1124): та же дверь, что и у обычной позиции, но её обязаны взять
  // и тогда, когда вкладка уже наполовину выгружена (закрытие, переход на другой сайт) -
  // `fetch` там не гарантирован, а `sendBeacon` для этого и сделан. Ответа у него нет, и
  // спрашивать тут нечего: сказано - и вкладки, считай, уже нет.
  left(body) {
    const payload = JSON.stringify(body);
    if (navigator.sendBeacon) {
      navigator.sendBeacon('/api/web/position', new Blob([payload], { type: 'application/json' }));
      return;
    }
    // Старый браузер без `sendBeacon` - `keepalive` держит запрос живым по ту же цену.
    fetch('/api/web/position', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
    }).catch(() => {});
  },

  async _get(url, fallback) {
    try {
      const said = await fetch(url);
      if (!said.ok) return fallback;
      return await said.json();
    } catch (error) {
      return fallback;
    }
  },

  // 🔴 Пустое тело - это «сделано, сказать нечего» (204), а не отказ. `said.json()` на
  // пустом теле бросает всегда, ошибка уезжала в общий `catch`, и `null` от сделанного
  // дела был неотличим от разрыва сети. На этом молча ломалась кнопка «На ТВ»: сервер
  // звал приёмник и отвечал 204, а вкладка читала отказ и не гасила свой звук - показ шёл
  // в двух местах разом.
  async _post(url, body) {
    try {
      const said = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!said.ok) return null;
      const text = await said.text();
      return text ? JSON.parse(text) : {};
    } catch (error) {
      return null;
    }
  },
};

window.TCApi = TCApi;
