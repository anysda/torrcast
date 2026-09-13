// Память страницы о виденных экранах (TC-1240): уходя с экрана, его узлы снимаются
// сюда ЦЕЛИКОМ и живут до возврата. Обложки и прокрутка полок остаются при СВОИХ
// узлах, поэтому вернувшийся человек видит готовый экран, а не новый сбор со скелетами
// и перезаказом каждой картинки. Свежесть доезжает тихим добором самих экранов
// (`card.js`, `home.js`): тело подменяется, только когда правда изменилось.
'use strict';

const TCKept = {
  // Сколько экранов помнить: узлы каждого живут своей жизнью, и страница - не склад.
  // Дальше этого числа первым уходит самый давно виденный.
  _MAX: 8,
  _screens: new Map(),

  // Экран называет корню, ЧЬЁ тело на нём стоит: адрес как он есть (path + search).
  mark(root, at) {
    root.dataset.tcKept = at;
  },

  // Снять прежний экран в память: маршрутизатор зовёт это до смены, пока узлы живы.
  // Неготовый экран (скелеты, отказ, пустая загрузка) не помнится вовсе - возврат
  // соберёт его заново, как в первый раз.
  stash(root) {
    const at = root.dataset.tcKept || '';
    root.dataset.tcKept = '';
    if (!at || !root.childNodes.length) return;
    const screen = at.startsWith('/card/') ? TCCard
      : at === '/' || at.startsWith('/?') ? TCHome : null;
    if (!screen || !screen.ready(root)) return;
    TCKept._screens.delete(at);
    // Ленивая картинка, снятая с экрана, при возврате заказывается ЗАНОВО, хотя кадр
    // у неё уже есть: снятая становится «нетерпеливой», и возврат не ведёт её в сеть
    // второй раз. Не начатая остаётся ленивой - греть невидимое возврат не должен.
    root.querySelectorAll('img[loading="lazy"]').forEach((img) => {
      if (img.complete && img.currentSrc) img.loading = 'eager';
    });
    // У снятого узла нет бокса, и прокрутка его лент умирает в ноль: она помнится
    // числами и ставится назад при возврате, по тем же узлам в том же порядке.
    const marks = Array.from(root.querySelectorAll('.tc-row, .tc-episodes'))
      .map((line) => [line.scrollLeft, line.scrollTop]);
    TCKept._screens.set(at, { nodes: Array.from(root.childNodes), y: window.scrollY, marks });
    while (TCKept._screens.size > TCKept._MAX) {
      TCKept._screens.delete(TCKept._screens.keys().next().value);
    }
  },

  // Точка возврата: узлы экрана или ничего. Взятый экран считается свежим по счёту.
  take(at) {
    const kept = TCKept._screens.get(at);
    if (!kept) return null;
    TCKept._screens.delete(at);
    TCKept._screens.set(at, kept);
    return kept;
  },

  // Поставить снятые узлы назад на корень и вернуть странице её прокрутку: документ
  // теряет высоту в миг смены экрана, и прокрутка падает в ноль до возврата узлов.
  resume(root, kept) {
    root.replaceChildren(...kept.nodes);
    const lines = root.querySelectorAll('.tc-row, .tc-episodes');
    if (kept.marks) {
      // Мгновенно, а не плавно: это возврат того, что уже стояло, а не прокрутка.
      kept.marks.forEach(([left, top], index) => {
        if (lines[index]) lines[index].scrollTo({ left, top, behavior: 'instant' });
      });
    }
    if (kept.y) requestAnimationFrame(() => window.scrollTo(0, kept.y));
  },
};

window.TCKept = TCKept;
