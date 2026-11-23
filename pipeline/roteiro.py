"""Leitura e validação do roteiro.json antes de gastar TTS, Whisper e download de tiles."""
import json

from .cenas import FUNDOS, PECAS_MAPA, SLOTS, TIPOS_FX
from .mapas import CAMADAS


def validar(R):
    """Lista de erros legíveis (vazia = roteiro ok)."""
    erros = []
    vistas = R.get('vistas', {})
    for nome, v in vistas.items():
        if not (isinstance(v.get('centro'), list) and len(v['centro']) == 2):
            erros.append(f'vista {nome}: "centro" deve ser [lon, lat]')
        elif not (-180 <= v['centro'][0] <= 180 and -85.06 <= v['centro'][1] <= 85.06):
            erros.append(f'vista {nome}: centro fora do mundo Web Mercator: {v["centro"]}')
        if not isinstance(v.get('zoom'), (int, float)):
            erros.append(f'vista {nome}: "zoom" numérico obrigatório')
        if v.get('camada', 'bm') not in CAMADAS:
            erros.append(f'vista {nome}: camada {v.get("camada")!r} desconhecida (use {", ".join(CAMADAS)})')
    cenas = R.get('cenas')
    if not isinstance(cenas, list) or not cenas:
        return erros + ['"cenas" deve ser uma lista não vazia']
    for i, c in enumerate(cenas):
        cid = f'c{i + 1:02d}'
        if not isinstance(c.get('narracao'), str) or not c['narracao'].strip():
            erros.append(f'{cid}: "narracao" obrigatória')
        f = c.get('fundo', {'tipo': 'papel'})
        if f.get('tipo') not in FUNDOS:
            erros.append(f'{cid}: fundo {f.get("tipo")!r} desconhecido (use {", ".join(sorted(FUNDOS))})')
        elif f['tipo'] == 'mapa' and f.get('vista') not in vistas:
            erros.append(f'{cid}: vista {f.get("vista")!r} não está em "vistas"')
        for fx in c.get('fx', []):
            tp = fx.get('tipo')
            if tp not in TIPOS_FX:
                erros.append(f'{cid}: fx {tp!r} desconhecido')
            elif tp in PECAS_MAPA - {'camera'} and f.get('tipo') != 'mapa':
                erros.append(f'{cid}: fx {tp!r} só funciona sobre fundo de mapa')
            pos = fx.get('pos')
            if isinstance(pos, str) and pos not in SLOTS:
                erros.append(f'{cid}: pos {pos!r} desconhecida (use {", ".join(SLOTS)})')
    ids = {f'c{i + 1:02d}' for i in range(len(cenas))}
    for m in R.get('musicas', []):
        if m.get('de') not in ids:
            erros.append(f'música {m.get("arq")!r}: "de" aponta para cena inexistente {m.get("de")!r}')
    return erros


def carregar(caminho):
    with open(caminho, encoding='utf8') as f:
        R = json.load(f)
    erros = validar(R)
    if erros:
        raise SystemExit('roteiro inválido:\n  ' + '\n  '.join(erros))
    return R
