import pytest

from pipeline.render import blocos


def test_blocos_de_90s_cobrem_tudo_sem_buraco():
    bs = blocos(527, 90)
    assert bs[0] == (0.0, 90.0) and bs[-1] == (450.0, 527)
    assert len(bs) == 6
    assert all(a[1] == b[0] for a, b in zip(bs, bs[1:]))


def test_blocos_video_curto_e_exato():
    assert blocos(30, 90) == [(0.0, 30)]
    assert blocos(180, 90) == [(0.0, 90.0), (90.0, 180.0)]


def test_blocos_invalido():
    with pytest.raises(ValueError):
        blocos(0)
