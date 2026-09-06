// Плашка автоперехода (ТЗ §4.5, §11 п.8): за секунду до конца серии - десять секунд
// на «Смотреть»/«Отмена», сама играет счётчик. Плеер решает, КОГДА её показать; сама
// плашка решает только, что делать по истечении счётчика или по клику.
'use strict';

const TCPlayerNext = {
  //: Сколько секунд ждать до автоматического перехода; число из ТЗ, а не из воздуха.
  SECONDS: 10,

  // ``onPlay`` зовётся и по истечении счётчика, и по клику «Смотреть» - ровно одна
  // дверь в ``POST /api/next`` (:mod:`torrcast.usecases` дальше сам не дублируется).
  mount(root, onPlay, onCancel) {
    const card = document.createElement('div');
    card.className = 'tc-next';
    card.dataset.tcNextEpisode = '1';

    const art = document.createElement('div');
    art.className = 'tc-next-art';
    card.appendChild(art);

    const body = document.createElement('div');
    body.className = 'tc-next-body';

    const badge = document.createElement('div');
    badge.className = 'tc-next-badge';
    body.appendChild(badge);

    const title = document.createElement('div');
    title.className = 'tc-next-title';
    title.textContent = TC.say('web.player.next_episode');
    body.appendChild(title);

    const buttons = document.createElement('div');
    buttons.className = 'tc-next-buttons';

    const now = document.createElement('button');
    now.type = 'button';
    now.className = 'tc-btn tc-btn--primary tc-next-now';
    now.textContent = TC.say('web.player.play_now');
    now.tabIndex = 0;
    now.dataset.tcFocusable = '1';
    now.dataset.tcGroup = 'next';
    const fill = document.createElement('i');
    now.appendChild(fill);

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'tc-btn tc-btn--secondary';
    cancel.textContent = TC.say('web.player.cancel');
    cancel.tabIndex = 0;
    cancel.dataset.tcFocusable = '1';
    cancel.dataset.tcGroup = 'next';

    buttons.append(now, cancel);
    body.appendChild(buttons);
    card.appendChild(body);
    root.appendChild(card);
    now.focus();

    let left = TCPlayerNext.SECONDS;
    const paint = () => {
      badge.textContent = TC.say('web.player.next_in', { n: left });
      fill.style.width = (100 * (TCPlayerNext.SECONDS - left)) / TCPlayerNext.SECONDS + '%';
    };
    paint();
    const timer = setInterval(() => {
      left -= 1;
      if (left <= 0) {
        clearInterval(timer);
        onPlay();
        return;
      }
      paint();
    }, 1000);

    const stop = () => {
      clearInterval(timer);
      card.remove();
    };
    now.addEventListener('click', () => {
      stop();
      onPlay();
    });
    cancel.addEventListener('click', () => {
      stop();
      onCancel();
    });
    return stop;
  },
};

window.TCPlayerNext = TCPlayerNext;
