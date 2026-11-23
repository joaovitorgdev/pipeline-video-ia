import pytest

from pipeline.render import blocos, duracao_ffprobe


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


def test_duracao_pelo_json_do_ffprobe_independe_da_ordem():
    saida = '{"streams": [{"nb_read_packets": "2700", "r_frame_rate": "30/1"}]}'
    assert duracao_ffprobe(saida) == 90.0
    saida_ntsc = '{"streams": [{"r_frame_rate": "30000/1001", "nb_read_packets": "2997"}]}'
    assert abs(duracao_ffprobe(saida_ntsc) - 99.9999) < 1e-3
