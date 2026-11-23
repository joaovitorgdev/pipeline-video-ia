import math

import pytest

from pipeline.mapas import Vista, aneis, caixa, caminho, mundo, tile, tiles_cobertos, url_ibge


def tile_osm(lon, lat, z):
    """Fórmula de referência do OpenStreetMap (slippy map), independente da implementação."""
    n = 2 ** z
    lat_r = math.radians(lat)
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(lat_r)) / math.pi) / 2 * n)


def test_mundo_origem_e_centro():
    assert mundo(-180, 85.0511, 0) == pytest.approx((0, 0), abs=0.01)
    assert mundo(0, 0, 0) == pytest.approx((128, 128))
    assert mundo(0, 0, 1) == pytest.approx((256, 256))


@pytest.mark.parametrize('lon,lat,z', [(-47.9, -15.8, 8), (-43.2, -22.9, 12), (2.35, 48.85, 5), (151.2, -33.9, 14), (10.0, 10.0, 3)])
def test_tile_bate_com_formula_osm(lon, lat, z):
    assert tile(lon, lat, z) == tile_osm(lon, lat, z)


def test_latitude_extrema_e_limitada():
    assert mundo(0, 89.9, 2)[1] == pytest.approx(0, abs=0.01)
    assert mundo(0, -89.9, 2)[1] == pytest.approx(1024, abs=0.01)


def test_vista_centro_cai_no_meio_da_tela():
    v = Vista('teste', (-52, -14), 4.6)
    assert v.proj(-52, -14) == (960.0, 540.0)
    assert v.proj(-40, -14)[0] > 960  # leste fica à direita
    assert v.proj(-52, -5)[1] < 540  # norte fica acima


def test_tiles_cobertos_descarta_linhas_fora_do_mundo():
    ts = tiles_cobertos(-10, -10, 300, 300, 0)
    assert all(ty == 0 for _, ty in ts)
    assert {tx for tx, _ in ts} == {-1, 0, 1}  # x dá a volta no mundo (o download usa tx % n)


def test_aneis_de_feature_collection_e_multipolygon():
    quad = [[0, 0], [1, 0], [1, 1], [0, 0]]
    fc = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [quad, [[0.2, 0.2]]]}},
        {'type': 'Feature', 'geometry': {'type': 'MultiPolygon', 'coordinates': [[quad], [quad]]}},
    ]}
    assert aneis(fc) == [quad, quad, quad]  # só os anéis externos
    assert aneis({'type': 'Point', 'coordinates': [0, 0]}) == []


def test_caminho_simplifica_pontos_proximos_e_fecha():
    v = Vista('t', (0, 0), 2)
    d = caminho(v, [[[0, 0], [0.0001, 0], [10, 0], [10, 10]]])
    assert d.startswith('M960.0 540.0') and d.endswith(' Z')
    assert d.count(' L') == 2  # o ponto a menos de 1,2 px do primeiro foi descartado
    assert not caminho(v, [[[0, 0], [10, 0]]], fecha=False).endswith('Z')


def test_caixa_e_centro():
    v = Vista('t', (0, 0), 3)
    (x0, y0, x1, y1), (cx, cy) = caixa(v, [[[-1, -1], [1, 1]]])
    assert x0 < x1 and y0 < y1
    assert (cx, cy) == pytest.approx((960, 540), abs=0.1)


def test_url_ibge():
    assert url_ibge('uf:DF').split('?')[0].endswith('/estados/53')
    assert '/municipios/3304557?' in url_ibge('mun:3304557')
    assert 'intrarregiao=UF' in url_ibge('br')
    with pytest.raises(ValueError):
        url_ibge('pais:XX')
