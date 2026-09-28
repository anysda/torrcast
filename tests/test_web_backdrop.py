"""Сторож: подложка карточки рисуется без размытия.

Подложка карточки - плавный градиент во весь экран. `filter: blur` над ним ничего не
меняет глазу (кадр с размытием и без расходится не больше чем на 1/255 на канал), но
растеризатор платит за размытие каждого пикселя экрана: без видеокарты это около
250 мс до первого кадра карточки, то есть весь бюджет прямой ссылки. Проверяется
само правило, порога тут нет.
"""

from __future__ import annotations

import re
from pathlib import Path

STYLE = Path(__file__).resolve().parents[1] / "web" / "static" / "style.css"

#: Тело правила подложки карточки.
BACKDROP = re.compile(r"\.tc-detail-blur\s*\{([^}]*)\}")


def test_the_card_backdrop_is_not_blurred() -> None:
    rules = BACKDROP.findall(STYLE.read_text(encoding="utf-8"))
    assert rules, "в style.css нет правила .tc-detail-blur - сторож стережёт пустоту"
    blurred = [body for body in rules if re.search(r"blur\s*\(", body)]
    assert not blurred, "подложка карточки снова размыта: это ~250 мс растеризации на кадр"
