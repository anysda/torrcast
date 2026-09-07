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

  async shelves() {
    const said = await TCApi._get('/api/shelves', null);
    return {
      fresh: Array.isArray(said && said.fresh) ? said.fresh : [],
      popular: Array.isArray(said && said.popular) ? said.popular : [],
    };
  },

  async search(query) {
    const said = await TCApi._post('/api/search', { query });
    return Array.isArray(said && said.results) ? said.results : [];
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
    const said = await TCApi._post('/api/play', body);
    if (said) TCRouter.go('/play');
    return said;
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

  async next() {
    return TCApi._post('/api/next', {});
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
  // в двух местах разом (замер на стенде `.104` 07-09-2026, пункт 9 приёмки).
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
