"""Mapas: fundo de satélite costurado de tiles (Web Mercator) e projeção lon/lat -> pixel da tela 1920x1080.

Camadas com licença compatível com uso comercial:
  bm  = NASA Blue Marble com relevo e batimetria (GIBS, domínio público), até zoom 8 (país/região)
  s2  = Sentinel-2 cloudless 2016 da EOX (CC BY 4.0, exige crédito), até zoom 14 (estado/cidade)
Contornos de UF/município/meso/microrregião: API de malhas do IBGE.

A imagem sai em 2x (3840x2160) para a câmera poder dar zoom de até 2x sem borrar.
Tiles e GeoJSON ficam em cache local (PIPELINE_CACHE, padrão ./cache): cada tile é baixado uma vez só.
"""
import json
import math
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .config import CACHE, UA

CAMADAS = {
    'bm': ('https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/'
           'GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg', 8, 'NASA Blue Marble (GIBS)'),
    # 2016 = CC BY 4.0. As edições 2018+ do s2cloudless são CC BY-NC-SA (não comercial): não usar.
    's2': ('https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg', 14,
           'Sentinel-2 cloudless 2016 by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016), CC BY 4.0'),
}
W, H, ESCALA = 1920, 1080, 2  # tela e fator da imagem de fundo
OCEANO = (14, 30, 52)  # cor do mar aberto onde a camada não tem tile
TILE_VAZIO = 1000  # bytes: abaixo disso o servidor devolveu tile sem imagem
UF = {'RO': 11, 'AC': 12, 'AM': 13, 'RR': 14, 'PA': 15, 'AP': 16, 'TO': 17, 'MA': 21, 'PI': 22, 'CE': 23, 'RN': 24, 'PB': 25,
      'PE': 26, 'AL': 27, 'SE': 28, 'BA': 29, 'MG': 31, 'ES': 32, 'RJ': 33, 'SP': 35, 'PR': 41, 'SC': 42, 'RS': 43, 'MS': 50,
      'MT': 51, 'GO': 52, 'DF': 53}


def mundo(lon, lat, z):
    """lon/lat -> pixel no mundo Web Mercator de tiles de 256 px no zoom z (z pode ser fracionário)."""
    n = 256 * 2 ** z
    lat = max(-85.0511, min(85.0511, lat))
    s = math.sin(math.radians(lat))
    return (lon + 180) / 360 * n, (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n


def tile(lon, lat, z):
    """Índice (x, y) do tile de 256 px que contém lon/lat no zoom inteiro z."""
    x, y = mundo(lon, lat, z)
    return int(x // 256), int(y // 256)


def tiles_cobertos(x0, y0, w, h, z):
    """Tiles (tx, ty) que cobrem o retângulo de pixels do mundo (x0, y0, w, h) no zoom z; ty fora do mundo é descartado."""
    n = 2 ** z
    return [(tx, ty) for tx in range(int(x0 // 256), int((x0 + w) // 256) + 1)
            for ty in range(int(y0 // 256), int((y0 + h) // 256) + 1) if 0 <= ty < n]


class Vista:
    """Enquadramento: centro (lon, lat) e zoom; proj() dá o pixel na tela 1920x1080."""

    def __init__(self, nome, centro, zoom, camada='bm'):
        self.nome, self.centro, self.zoom, self.camada = nome, centro, zoom, camada
        self.cx, self.cy = mundo(centro[0], centro[1], zoom)

    def proj(self, lon, lat):
        x, y = mundo(lon, lat, self.zoom)
        return round(x - self.cx + W / 2, 1), round(y - self.cy + H / 2, 1)

    def fundo(self, saida):
        """Costura os tiles e grava o JPEG 3840x2160 (pula se já existe com os mesmos parâmetros)."""
        from PIL import Image  # import tardio: os testes de projeção não precisam do Pillow

        assin = json.dumps([self.centro, self.zoom, self.camada, ESCALA])
        if os.path.exists(saida) and os.path.exists(saida + '.vista'):
            with open(saida + '.vista', encoding='utf8') as f:
                if f.read() == assin:
                    return saida
        url, zmax, _ = CAMADAS[self.camada]
        zf = self.zoom + math.log2(ESCALA)  # zoom efetivo da imagem 2x
        zi = min(zmax, math.ceil(zf - 1e-6))
        k = 2 ** (zi - zf)  # pixels de tile por pixel de saída
        cx, cy = mundo(self.centro[0], self.centro[1], zi)
        w, h = W * ESCALA * k, H * ESCALA * k
        x0, y0 = cx - w / 2, cy - h / 2
        n = 2 ** zi
        tiles = tiles_cobertos(x0, y0, w, h, zi)
        img = Image.new('RGB', (int(math.ceil(w)), int(math.ceil(h))), (5, 9, 20))

        def pega(t):
            tx, ty = t
            arq = os.path.join(CACHE, self.camada, str(zi), str(tx % n), f'{ty}.jpg')
            if os.path.exists(arq + '.vazio'):
                return t, None
            if not os.path.exists(arq):
                os.makedirs(os.path.dirname(arq), exist_ok=True)
                req = urllib.request.Request(url.format(z=zi, x=tx % n, y=ty), headers=UA)
                with urllib.request.urlopen(req, timeout=60) as r:
                    dado = r.read()
                if len(dado) < TILE_VAZIO:  # mar aberto sem imagem na camada: pinta de oceano e lembra no cache
                    open(arq + '.vazio', 'w').close()
                    return t, None
                with open(arq, 'wb') as f:
                    f.write(dado)
            return t, arq

        vazios = 0
        with ThreadPoolExecutor(6) as ex:
            for (tx, ty), arq in ex.map(pega, tiles):
                px, py = int(tx * 256 - x0), int(ty * 256 - y0)
                if arq is None:
                    vazios += 1
                    img.paste(OCEANO, (px, py, px + 256, py + 256))
                    continue
                img.paste(Image.open(arq).convert('RGB'), (px, py))
        if vazios > len(tiles) * 0.5:
            raise SystemExit(f'{self.nome}: {vazios} de {len(tiles)} tiles vazios em {self.camada}: confira camada/zoom')
        os.makedirs(os.path.dirname(saida) or '.', exist_ok=True)
        img.resize((W * ESCALA, H * ESCALA), Image.LANCZOS).save(saida, quality=92)
        with open(saida + '.vista', 'w', encoding='utf8') as f:
            f.write(assin)
        print(f'mapa {self.nome}: z{zi}, {len(tiles)} tiles -> {saida}')
        return saida

    def credito(self):
        return CAMADAS[self.camada][2]


def _baixa_json(url, arq):
    if not os.path.exists(arq):
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            dado = r.read()
        with open(arq, 'wb') as f:
            f.write(dado)
    with open(arq, encoding='utf8') as f:
        return json.load(f)


def url_ibge(ref):
    """URL da malha do IBGE. ref: 'uf:DF', 'mun:3304557', 'meso:2901', 'micro:29001', 'br' (todas as UFs)."""
    base = 'https://servicodados.ibge.gov.br/api/v3/malhas/'
    q = '?formato=application/vnd.geo+json&qualidade=intermediaria'
    tipo, _, cod = ref.partition(':')
    if tipo == 'uf':
        return f'{base}estados/{UF.get(cod, cod)}{q}'
    if tipo == 'br':
        return f'{base}paises/BR{q}&intrarregiao=UF'
    nivel = {'mun': 'municipios', 'meso': 'mesorregioes', 'micro': 'microrregioes'}.get(tipo)
    if not nivel:
        raise ValueError(f'referência geográfica inválida: {ref!r}')
    return f'{base}{nivel}/{cod}{q}'


def geo(ref):
    """GeoJSON do IBGE (com cache)."""
    return _baixa_json(url_ibge(ref), os.path.join(CACHE, 'ibge', ref.replace(':', '_') + '.json'))


def aneis(g):
    """Todos os anéis externos de uma FeatureCollection/Feature/geometria."""
    if g.get('type') == 'FeatureCollection':
        return [a for f in g['features'] for a in aneis(f)]
    if g.get('type') == 'Feature':
        return aneis(g['geometry'])
    if g['type'] == 'Polygon':
        return [g['coordinates'][0]]
    if g['type'] == 'MultiPolygon':
        return [p[0] for p in g['coordinates']]
    if g['type'] == 'LineString':
        return [g['coordinates']]
    return []


def caminho(vista, coords_lista, fecha=True, tol=1.2):
    """Anéis lon/lat -> atributo d de SVG na tela, descartando pontos a menos de tol px do anterior."""
    partes = []
    for anel in coords_lista:
        pts, ult = [], None
        for lon, lat in ((c[0], c[1]) for c in anel):
            p = vista.proj(lon, lat)
            if ult is None or abs(p[0] - ult[0]) + abs(p[1] - ult[1]) >= tol:
                pts.append(p)
                ult = p
        if len(pts) >= 2:
            partes.append('M' + ' L'.join(f'{x} {y}' for x, y in pts) + (' Z' if fecha else ''))
    return ' '.join(partes)


def caixa(vista, coords_lista):
    """Caixa (x0, y0, x1, y1) na tela e o centro dela."""
    ps = [vista.proj(c[0], c[1]) for anel in coords_lista for c in anel]
    xs, ys = [p[0] for p in ps], [p[1] for p in ps]
    return (min(xs), min(ys), max(xs), max(ys)), ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
