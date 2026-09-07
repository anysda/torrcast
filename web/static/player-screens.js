// Экраны поверх плёнки (ТЗ §4.5, §7.1, §7.3): подготовка ящика, буферизация и потеря
// потока с «Повторить». Три состояния оверлея, ничего больше - ни опроса, ни hls.js;
// тем решает `player.js`, эти три только рисуют, что он решил.
'use strict';

const TCPlayerScreens = {
  clear(overlay) {
    if (overlay) overlay.replaceChildren();
  },

  //: Ящик ещё пуст. Продукт не отдаёт наружу оценку старта (``start_budget``,
  //: ``start_clock``) - это честный пробел, названный в отчёте, а не «Preparing…20 s»
  //: из воздуха: тут только слово, без числа и без имени источника.
  preparing(overlay) {
    const screen = document.createElement('div');
    screen.className = 'tc-preparing';
    for (const corner of ['tl', 'tr', 'bl', 'br']) {
      const bracket = document.createElement('div');
      bracket.className = 'tc-bracket tc-bracket--' + corner;
      screen.appendChild(bracket);
    }
    const body = document.createElement('div');
    body.className = 'tc-preparing-body';
    const title = document.createElement('div');
    title.className = 'tc-preparing-title';
    title.textContent = TC.say('web.player.preparing');
    const bar = document.createElement('div');
    bar.className = 'tc-preparing-bar is-indeterminate';
    bar.appendChild(document.createElement('i'));
    body.append(title, bar);
    screen.appendChild(body);
    overlay.replaceChildren(screen);
  },

  buffering(overlay) {
    const screen = document.createElement('div');
    screen.className = 'tc-buffering-screen';
    const spinner = document.createElement('div');
    spinner.className = 'tc-spinner';
    const label = document.createElement('div');
    label.className = 'tc-buffering';
    label.textContent = TC.say('web.player.buffering');
    screen.append(spinner, label);
    overlay.replaceChildren(screen);
  },

  //: После трёх неудач - экран ошибки с «Повторить» (§4.5); ``onRetry`` кладёт плеер.
  lost(overlay, code, onRetry) {
    const screen = document.createElement('div');
    screen.className = 'tc-lost';
    const title = document.createElement('div');
    title.className = 'tc-lost-title';
    const said = TC.say('web.player.lost');
    title.textContent = said;
    for (let i = 0; i < 2; i += 1) {
      const span = document.createElement('span');
      span.textContent = said;
      title.appendChild(span);
    }
    const note = document.createElement('div');
    note.className = 'tc-lost-code';
    note.textContent = TC.say('web.player.lost_code', { code });
    const actions = document.createElement('div');
    actions.className = 'tc-lost-actions';
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'tc-btn tc-btn--primary';
    retry.textContent = TC.say('web.player.retry');
    retry.tabIndex = 0;
    retry.dataset.tcFocusable = '1';
    retry.dataset.tcGroup = 'lost';
    retry.addEventListener('click', onRetry);
    actions.appendChild(retry);
    screen.append(title, note, actions);
    overlay.replaceChildren(screen);
    retry.focus();
  },
};

window.TCPlayerScreens = TCPlayerScreens;
