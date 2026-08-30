"""Русские надписи кластера выбора картины."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера выбора.

    🔴 Ключ - ЦЕЛАЯ фраза с именованными подстановками, а не склейка кусков. Русское
    значение держит свою форму числа и свой порядок слов внутри себя, английское -
    свои. Поэтому «спросили ... - беру» и голое «беру» тут два разных ключа, а не общая
    голова, приклеенная к общему хвосту: голова у одного языка глагол, у другого
    оборот, и склейка ломала бы один из них.
    """
    return {
        "choice.quoted": "«{it}»",
        "choice.series_mark": ", сериал",
        "choice.no_part_mark": ", без номера части",
        "choice.remote_command": "пульт: {command}",
        "choice.pick_out_of_range": "подходит картин: {total}, номера {pick} нет",
        "choice.pick_moved": (
            "под номером {pick} в таблице «{asked}» была «{was}», а сейчас под ним "
            "«{now}» - это не та картина; свежие номера: cast releases {asked}"
        ),
        "choice.playing_pick": "играю «{picture}» - пункт {pick}, названный флагом --pick",
        "choice.single_no_menu": "подходит картин: 1 - «{picture}», меню не нужно",
        "choice.blind_refusal": (
            "подходит картин: {total}, а терминала нет - вслепую не выбираю; назови "
            "картину точно (например «{example}») или её номер (--pick N), либо "
            "запусти cast в терминале"
        ),
        "choice.question": "Что смотрим?",
        "choice.absent_part": (
            "«{name}»: первой части в выдаче нет; беру первую живую из найденных - "
            "«{picture}»; всего подошло картин {total}; остальные: cast {asked} --menu"
        ),
        "choice.default": "Enter - «{picture}», пункт {number} из {total}",
        "choice.note_instead": "беру «{mine}», а не «{other}»",
        "choice.note_instead_asked": "спросили «{asked}» - беру «{mine}», а не «{other}»",
        "choice.note_instead_why": "беру «{mine}», а не «{other}»: {why}",
        "choice.note_instead_asked_why": (
            "спросили «{asked}» - беру «{mine}», а не «{other}»: {why}"
        ),
        "choice.note_namesake": (
            "беру «{mine}»: под этим именем есть ещё {others} - другая картина"
        ),
        "choice.note_namesake_asked": (
            "спросили «{asked}» - беру «{mine}»: под этим именем есть ещё {others} - другая картина"
        ),
        "choice.note_season": (
            "беру «{mine}»: спрошен {season} сезон, а в выдаче его нет - у неё часть {part}"
        ),
        "choice.note_season_asked": (
            "спросили «{asked}» - беру «{mine}»: спрошен {season} сезон, а в выдаче его "
            "нет - у неё часть {part}"
        ),
        "choice.why_other_kind": "спросили серию, а это другой тип",
        "choice.why_nothing_playable": "играть у неё нечем - ни одной годной раздачи",
        "choice.why_dead_swarm": "рой у неё мёртв - сидов {seeds}",
        "choice.why_no_hd": "живого HD у неё нет - одно старьё",
        "choice.why_single_release": "у неё всего одна раздача, а тут их {taken}",
        "choice.last_hope_episode": (
            "живой раздачи серии {want} без HEVC нет - беру HEVC последней надеждой"
        ),
        "choice.last_hope_picture": (
            "живой раздачи картины без HEVC нет - беру HEVC последней надеждой"
        ),
        "choice.lone_other_part": (
            "«{name}»: первой части в выдаче нет, и другую часть сам не включаю - есть "
            "«{picture}», спроси её номером «{name} {part}»"
        ),
        "choice.named_unplayable": (
            "«{name}» - это {whom}; не играет: {why}; вместо неё другую картину "
            "(«{taken}») сам не включаю - вот что есть, назови номер"
        ),
        "choice.named_not_default": (
            "«{name}» - это {whom}, а дефолтом встаёт другая картина - «{taken}» "
            "(первая живая по хронологии); какую из них смотреть, сам не решаю - вот "
            "что есть, назови номер"
        ),
        "choice.named_taken_alive": (
            "«{name}» - это {whom}; беру самую живую из них - «{took}»; всего подошло "
            "картин {total}; другая: cast {asked} --menu"
        ),
        "choice.named_taken_unplayable": (
            "«{name}» - это {whom}, но не играет: {why}; беру самую живую - «{took}»; "
            "всего подошло картин {total}; другая: cast {asked} --menu"
        ),
        "choice.namesake_taken": (
            "беру «{picture}» - самая живая из одноимённых, у лучшей её раздачи сидов "
            "{seeds}; других картин под этим именем: {others}, их список: cast {asked} "
            "--menu"
        ),
        "choice.namesake_two": (
            "«{title}» ({year}): под этим именем и годом картин две - справка знает ещё "
            "«{other}», развести их по имени и году нечем"
        ),
        "choice.part_one_absent": (
            "«{name}»: первой части в выдаче нет, и вместо неё другую часть сам не "
            "включаю - вот что есть, назови номер"
        ),
        "choice.part_one_dead": (
            "«{picture}» не играет; вместо неё другую часть сам не включаю - вот что "
            "есть, назови номер"
        ),
        "choice.part_one_dead_why": (
            "«{picture}» не играет: {why}; вместо неё другую часть сам не включаю - вот "
            "что есть, назови номер"
        ),
        "choice.taken": (
            "беру «{picture}» - подошло картин {total}; другая: cast releases {asked} и --pick N"
        ),
        "choice.understudy": (
            "«{failed}» - играть нечем ({why}); ухожу к «{spare}»: раздач {releases}"
        ),
        "choice.mark_recode_all": "перекодирую целиком",
        "choice.mark_not_taken": "не берём",
        "choice.mark_heavy": "тяжёлый",
        "choice.mark_recode_parts": "перекодируем",
        "choice.year_note": (
            "беру «{title}» {year} года, но справка знает эту картину как {known}"
        ),
        "choice.year_note_asked": (
            "спросили «{asked}» - беру «{title}» {year} года, но справка знает эту "
            "картину как {known}"
        ),
    }
