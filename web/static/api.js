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

  async play(body) {
    return TCApi._post('/api/play', body);
  },

  async toTv() {
    return TCApi._post('/api/to-tv', {});
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

  async _post(url, body) {
    try {
      const said = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!said.ok) return null;
      return await said.json();
    } catch (error) {
      return null;
    }
  },
};

window.TCApi = TCApi;
