// Экраны поверх плёнки (ТЗ §4.5, §7.1, §7.3): подготовка ящика, отказ подъёма,
// буферизация и потеря потока с «Повторить». Состояния оверлея, ничего больше - ни
// опроса, ни hls.js; тем решает `player.js`, эти только рисуют, что он решил.
'use strict';

const TCPlayerScreens = {
  clear(overlay) {
    if (overlay) overlay.replaceChildren();
  },

  //: Подъём кончился отказом: человек читает об этом словами, а не смотрит на вечную
  //: подготовку. Строка - каталожная (``web.player.refused``); причину, которую продукт
  //: различает, пишет юнит словом-договором (:mod:`torrcast.domain.start_refusal`), и
  //: хвост по нему ищется в том же каталоге. Причины нет - строка остаётся короткой,
  //: без выдуманного двоеточия. Пересобирается экран один раз: ответы идут раз в две
  //: секунды, и рождённый заново текст мигал бы под руками.
  //:
  //: Выход с отказа - кнопка «Назад» самого экрана (``onBack``): панель под ним спрятана,
  //: её кнопкам без плёнки делать нечего, и раньше у отказа не было ни одной рабочей.
  refused(overlay, reason, onBack) {
    if (!overlay) return;
    if (overlay.querySelector('.tc-refused')) return;
    const screen = document.createElement('div');
    screen.className = 'tc-refused';
    const title = document.createElement('div');
    title.className = 'tc-refused-title';
    let line = TC.say('web.player.refused');
    const why = TC.phrases['web.player.refused_' + (reason || '')];
    if (why !== undefined) line += ': ' + why;
    title.textContent = line;
    const back = TCPlayerScreens._back(onBack);
    screen.append(title, TCPlayerScreens._actions(back));
    overlay.replaceChildren(screen);
    back.focus();
  },

  //: «Назад» экрана без плёнки: та же дверь, что у ✕ панели и Esc, и та же надпись.
  _back(onBack) {
    const back = document.createElement('button');
    back.type = 'button';
    back.className = 'tc-btn tc-btn--secondary';
    back.textContent = TC.say('web.player.back');
    back.tabIndex = 0;
    back.dataset.tcFocusable = '1';
    back.dataset.tcGroup = 'halt';
    back.addEventListener('click', onBack);
    return back;
  },

  _actions(...buttons) {
    const actions = document.createElement('div');
    actions.className = 'tc-halt-actions';
    actions.append(...buttons);
    return actions;
  },

  //: Ящик ещё пуст, и человек ждёт. Кроме слова тут идут срок и имя источника из поля
  //: ``start`` ответа продукта (:mod:`torrcast.usecases.start_progress`): срок там
  //: ИЗМЕРЕННЫЙ по прошлым подъёмам этой машины. Продукт срока не дал - строки нет
  //: вовсе и полоса бежит, как раньше: число, посчитанное тут «примерно», было бы
  //: ложью с точностью до секунды, а она хуже молчания.
  //: Подготовка тоже бывает долгой (прод: «Матрица», четыре минуты), и уйти с неё можно
  //: не только клавишей: «Назад» (``onBack``) стоит под полосой.
  preparing(overlay, start, onBack) {
    if (!overlay) return;
    let screen = overlay.querySelector('.tc-preparing');
    if (!screen) {
      screen = TCPlayerScreens._prepare(onBack);
      overlay.replaceChildren(screen);
    }
    TCPlayerScreens._prepared(screen, start || null);
  },

  _prepare(onBack) {
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
    const when = document.createElement('div');
    when.className = 'tc-preparing-when';
    const bar = document.createElement('div');
    bar.className = 'tc-preparing-bar is-indeterminate';
    bar.appendChild(document.createElement('i'));
    const note = document.createElement('div');
    note.className = 'tc-preparing-note';
    body.append(title, when, bar, note);
    screen.append(body, TCPlayerScreens._actions(TCPlayerScreens._back(onBack)));
    return screen;
  },

  //: Экран пересобирается не каждый ответ, а переписывается на месте: ответы идут раз в
  //: две секунды, и полоса, заново рождающаяся под руками, дёргалась бы вместо хода.
  //: Полоса идёт ПО ЗНАЧЕНИЮ, пока срок известен: ждём ``waited`` из ``waited + left``.
  //: Срок кончился (``left`` пуст) - это «больше не знаю», и полоса возвращается к
  //: бегущей, а не замирает на ста процентах, будто вот-вот.
  _prepared(screen, start) {
    const when = screen.querySelector('.tc-preparing-when');
    const note = screen.querySelector('.tc-preparing-note');
    const bar = screen.querySelector('.tc-preparing-bar');
    const left = (start && start.left) || 0;
    const waited = (start && start.waited) || 0;
    when.textContent = left > 0 ? TC.say('web.player.preparing_in', { seconds: left }) : '';
    note.textContent = start && start.source
      ? TC.say('web.player.packaging', { n: start.source, m: start.sources || start.source })
      : '';
    const whole = left > 0 ? waited + left : 0;
    bar.classList.toggle('is-indeterminate', whole <= 0);
    bar.firstElementChild.style.width = whole > 0
      ? Math.max(0, Math.min(100, (100 * waited) / whole)).toFixed(1) + '%'
      : '';
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
  //: Рядом «Назад» (``onBack``): поток, не вернувшийся и после повтора, иначе держал
  //: человека на экране, где единственная кнопка ведёт обратно в ту же буферизацию.
  lost(overlay, code, onRetry, onBack) {
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
    actions.append(retry, TCPlayerScreens._back(onBack));
    screen.append(title, note, actions);
    overlay.replaceChildren(screen);
    retry.focus();
  },
};

window.TCPlayerScreens = TCPlayerScreens;
