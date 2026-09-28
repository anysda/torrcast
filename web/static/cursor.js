// Курсор страницы (TC-1319): прячется на ЛЮБОМ экране через 10 с без движения мыши и
// сразу по любому нажатию клавиши, возвращается движением мыши. Место одно на всю
// страницу - класс на <html>, а не копия таймера в каждом экране. Панель плеера
// (кнопки, прогресс и всё остальное) ходит с курсором в один миг: её прячет тот же
// класс из `player.css`, без подписок и без второго таймера.
'use strict';

const TCCursor = {
  // Срок покоя мыши. Ровно с ним уходит и панель плеера - своего таймера у показа
  // больше нет.
  IDLE_MS: 10000,
  _timer: null,

  init() {
    document.addEventListener('pointermove', TCCursor._moved, { passive: true });
    // Нажатие мыши - та же рука: разбудить курсор и перевзвести срок, как будил
    // плеер своим `click` до единого таймера на страницу.
    document.addEventListener('pointerdown', TCCursor._moved, { passive: true });
    // 🔴 Окно в фазе перехвата, а не документ: на показе стрелки и пробел забирает
    // себе слушатель плеера на документе в перехвате и гасит дальше всё
    // `stopImmediatePropagation` (`player.js`). Фаза идёт снаружи внутрь, и окно
    // слышит клавишу раньше ЛЮБОГО слушателя документа - иначе курсор не прятался
    // бы именно от тех клавиш, что сами управляют показом.
    window.addEventListener('keydown', TCCursor._pressed, true);
    TCCursor._moved();
  },

  // Движение мыши: курсор виден, и срок покоя отсчитывается заново от этого мига.
  _moved() {
    document.documentElement.classList.remove('tc-cursor-idle');
    clearTimeout(TCCursor._timer);
    TCCursor._timer = setTimeout(() => {
      document.documentElement.classList.add('tc-cursor-idle');
    }, TCCursor.IDLE_MS);
  },

  // Любая клавиша прячет курсор сразу и не взводит срок обратно: до движения мыши
  // он не вернётся, сколько бы клавиш ни нажали после этой.
  _pressed() {
    clearTimeout(TCCursor._timer);
    document.documentElement.classList.add('tc-cursor-idle');
  },
};

window.TCCursor = TCCursor;
