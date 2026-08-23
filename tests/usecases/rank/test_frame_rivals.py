"""Знаменатель живости ступени 1080p."""

from tests.usecases.rank.releases import rel
from torrcast.usecases.rank.frame_rivals import frame_rivals


def test_a_full_hd_release_is_not_a_rival_of_another_full_hd_release() -> None:
    full = rel(name="1080p", quality="1080p", seeders=60)
    crowd = rel(name="толпа 1080p", quality="1080p", seeders=250)
    small = rel(name="720p", quality="720p", seeders=55)
    group = (0,)

    assert frame_rivals([full, crowd, small], {id(r): group for r in [full, crowd, small]}) == {
        group: 55
    }
