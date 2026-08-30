"""Разговор с приёмником: LOAD, чистое приложение, чья сессия на экране и ожидание кадра.

Наследует его :class:`ChromecastReceiver`; занятия показа зовут эти ручки, и их же
подменяют на стенде - поэтому они и стоят одним слоем, а не по своим файлам."""

from __future__ import annotations

import contextlib

from torrcast.adapters.chromecast.cast.hls_hints import HLS_TYPE, hls_hints
from torrcast.adapters.chromecast.cast.receiver_link import _Link
from torrcast.adapters.chromecast.cast.while_connecting import _while_connecting
from torrcast.ports.journal.slot import journal


class _Talk(_Link):
    """Загрузка, чужая сессия и ожидание картинки: всё, о чём спрашивают приёмник."""

    def _load(self, at: float = 0.0, paused: bool = False) -> None:
        controller = self._device().media_controller
        self._error_code = None  # новый LOAD - новая причина, старую приписывать ему нельзя
        # ``paused=True`` - LOAD без автостарта: сессия возвращается на закладку и ждёт
        # зрителя, снявшего паузу с пульта; готовность её - слово ``PAUSED`` (:meth:`_settle`).
        self._paused = paused
        # BUFFERED, а не LIVE: манифест VOD знает длительность целиком, и ресивер
        # рисует шкалу с общим временем - перемотка пультом работает.
        #
        # 🔴 Через :func:`_while_connecting`, а не напрямую: сокет 8009 живёт дольше одной
        # серии, и на стыке он вправе оказаться в переподключении. Прямой вызов отвечал на
        # это необработанным ``NotConnected`` - юнит показа кончался кодом 1 при живом ТВ
        # (замер на стенде 30-08-2026). Ждать нечего у :meth:`block_until_active` ниже: он
        # ничего приёмнику не шлёт, а сидит на событии своей же сессии.
        _while_connecting(
            self,
            "LOAD",
            lambda: controller.play_media(
                self._url,
                HLS_TYPE,
                title=self._title,
                stream_type="BUFFERED",
                media_info=hls_hints(self.segment_container),
                current_time=at,
                autoplay=not paused,
            ),
        )
        controller.block_until_active(timeout=30)
        # Чья сессия на приёмнике - запоминаем здесь: по ней :meth:`_ours` отличит наш
        # показ от чужого, когда придёт пора закрывать приложение.
        self._session = getattr(self._cast.status, "session_id", "") or ""

    def _restart_app(self) -> None:
        """Закрыть приложение приёмника **и своё соединение** — следующий LOAD уходит в
        чистое с обеих сторон.

        ⚠️ Одного `quit_app` мало, замерено трижды подряд: приложение честно
        закрывается (``app_id`` становится ``None``), следующий LOAD по ТОМУ ЖЕ сокету
        поднимает его обратно — и показ не начинается, приёмник стоит в IDLE до самой
        смерти юнита. При этом новый процесс с новым соединением на том же ТВ поднимает
        картинку за 3 с. Значит, чинить надо не только приёмник, но и свою сессию.
        """
        print("приёмник залип - закрываю приложение и соединение, гружу заново", flush=True)
        # Пустой экран после этого - наша работа, и волей зрителя он не считается
        # (:func:`torrcast.adapters.chromecast.cast.viewer_closed._viewer_closed`).
        self._we_quit = True
        if self._cast is not None:
            with contextlib.suppress(Exception):
                self._cast.quit_app()
            with contextlib.suppress(Exception):
                self._cast.disconnect()
        self._cast = None  # следующий _device() поднимет соединение заново
        self.clock.sleep(self.LOAD_PAUSE)

    def _ours(self) -> bool:
        """Наша ли сессия сейчас на приёмнике — по трём признакам подряд.

        ⚠️ Статус берётся **кэшированный**: ``update_status`` на закрытом приёмнике
        поднимает пустой Default Media Receiver обратно (известная особенность приёмника,
        см. :meth:`_status`), а нам здесь именно закрывать. Кэш держится свежим сам:
        приёмник шлёт ``RECEIVER_STATUS`` в наш живой сокет на каждое изменение.

        * приложение не наше (``app_id`` пустой или чужой) — трогать нечего;
        * приложение то же, но сессию поднял кто-то другой — это чужой показ;
        * сессия та же, но играет не наш URL — значит, в наше приложение загрузился
          другой сендер (чужие сендеры делают ровно это, ``session_id`` при этом
          не меняется).
        """
        status = getattr(self._cast, "status", None)
        if getattr(status, "app_id", None) != self.MEDIA_APP:
            return False
        session = getattr(status, "session_id", "") or ""
        if self._session and session and session != self._session:
            return False
        playing = getattr(self._cast.media_controller.status, "content_id", "") or ""
        return not playing or not self._url or playing == self._url

    def _free(self) -> bool:
        """Свободен ли приёмник под воскрешение нашего показа.

        Свободен - это либо пустой экран (приложения нет вовсе или на нём заставка:
        ровно так выглядит ТВ, бросивший наш показ), либо всё ещё наша собственная сессия
        (:meth:`_ours`). Чужое приложение, чужая сессия в том же Default Media Receiver и
        чужой ``content_id`` в нашей - это чужой показ, и он неприкосновенен.

        Статус берётся кэшированный по той же причине, что и в :meth:`_ours`:
        ``update_status`` на закрытом приёмнике поднимает пустой Default Media Receiver
        обратно, а нам здесь именно **смотреть**, занят ли экран.
        """
        app = getattr(getattr(self._cast, "status", None), "app_id", None)
        if not app or app == self.BACKDROP_APP:
            return True
        return self._ours()

    def _settle(self, budget: float) -> bool:
        """Дождаться, пока приёмник действительно заиграет; отказ LOAD - повторить LOAD.

        ``IDLE`` без причины - это «ещё грузится», его терпим до конца ``budget``: ресивер
        сперва тянет манифест и первый сегмент. А вот причина говорит, что LOAD не взяли,
        и ждать бессмысленно:

        * ``ERROR`` - ресивер не смог начать;
        * ``IDLE`` дольше :data:`STUCK_SECONDS` - LOAD не взяли молча. Такое ловилось
          после перепаковки: приёмник стоял в IDLE при живых сегментах.

        Повтор LOAD - один счётчик на весь показ (:attr:`_reloads`), и потолок ему ставит
        профиль приёмника (:attr:`torrcast.domain.profile.Profile.load_retries`), а не бюджет
        ожидания: лестница ожидания не имеет права плодить свои попытки. Иначе счёт вёлся
        бы временем, и на неигравшем релизе в приёмник уходил бы десяток LOAD подряд, всё
        глубже загоняя его, пока прогон висит перед пустым экраном. Исчерпав повторы, честно
        возвращаем ``False`` - зовущий назовёт причину строкой, а не оставит человека в
        бесконечной петле LOAD. Каждый повтор ложится в след
        (:func:`torrcast.adapters.filesystem.trace_journal.reload`).

        ⚠️ ``INTERRUPTED`` поводом для повтора НЕ является: так ресивер отчитывается о
        КОНЦЕ ПРЕЖНЕЙ сессии, которую оборвал наш же новый LOAD. Повтор на него сбивает
        только что принятый LOAD - проверено живьём, показ на этом и умер.

        Любая повторная попытка идёт в чистое приложение: залипший Default Media Receiver
        молчит на все LOAD подряд, а `quit_app` лечит сразу.

        LOAD без автостарта (:attr:`_paused`) готов не картинкой, а словом ``PAUSED``:
        сессия вернулась на закладку и ждёт зрителя. Приёмник вправе такой LOAD не
        удержать и начать показ сам - тогда паузу возвращаем мы: ставил её зритель,
        и снимает тоже он.
        """
        deadline = self.clock.monotonic() + budget
        tried = self.clock.monotonic()
        ready = ("PAUSED",) if self._paused else ("PLAYING", "BUFFERING")
        hushed = False
        while self.clock.monotonic() < deadline:
            self.clock.sleep(1.0)
            status = self._status()
            if status.player_state in ready:
                return True
            if self._paused and status.player_state == "PLAYING" and not hushed:
                # autoplay=False проигнорирован, приёмник начал сам - вернуть паузу
                # зрителя наша работа, а не его.
                hushed = True
                with contextlib.suppress(Exception):
                    self._device().media_controller.pause()
                continue
            waited = self.clock.monotonic() - tried
            refused = status.idle_reason == "ERROR" and waited >= self.LOAD_PAUSE
            if refused or waited >= self.STUCK_SECONDS:
                if self._reloads >= self.profile.load_retries:
                    return False  # повторы LOAD исчерпаны - показ не начался, гаснем честно
                self._reloads += 1
                journal().reload(pos=self._peak, tries=self._reloads)
                tried = self.clock.monotonic()
                print(
                    f"LOAD не взяли ({self._why()}) - повтор {self._reloads} "
                    f"из {self.profile.load_retries}",
                    flush=True,
                )
                self._restart_app()
                self._load(self._at, paused=self._paused)
        return False
