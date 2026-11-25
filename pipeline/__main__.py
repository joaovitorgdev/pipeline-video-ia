"""CLI: python -m pipeline <comando> ...

Os módulos pesados (Whisper, edge-tts, Pillow, numpy) só são importados dentro de cada comando,
então `--help` e `validar` funcionam sem eles instalados.
"""
import argparse
import json
import sys


def _validar(a):
    from .roteiro import carregar

    R = carregar(a.roteiro)
    print(f'ok: {len(R["cenas"])} cenas, {sum(len(c["narracao"].split()) for c in R["cenas"])} palavras')


def _gerar(a):
    import os

    try:
        from .gerar import ErroGeracao, gerar
    except ImportError:
        raise SystemExit('o comando gerar precisa do SDK: pip install anthropic')
    try:
        R = gerar(a.tema, modelo=a.modelo)
    except ErroGeracao as e:
        raise SystemExit(f'gerar: {e}')
    destino = os.path.join(a.pasta, 'roteiro.json')
    os.makedirs(a.pasta, exist_ok=True)
    try:
        with open(destino, 'x', encoding='utf8') as f:  # 'x' nunca sobrescreve um roteiro existente
            json.dump(R, f, ensure_ascii=False, indent=2)
    except FileExistsError:
        raise SystemExit(f'{destino} já existe; escolha outra pasta')
    print(f'ok: {destino} com {len(R["cenas"])} cenas (revise antes de rodar montar)')


def _montar(a):
    from . import montar

    montar.main(a.pasta, sfx_dir=a.sfx, musica_dir=a.musica)


def _midia(a):
    from . import midia

    midia.main(a.acao, a.pasta, a.arquivo)


def _render(a):
    from . import render

    render.main(a.pasta, a.bloco)


def parser():
    p = argparse.ArgumentParser(prog='python -m pipeline', description='Pipeline de Vídeo com IA: roteiro.json -> narração -> legendas -> mapas -> MP4.')
    sub = p.add_subparsers(dest='comando', required=True)

    s = sub.add_parser('validar', help='confere o roteiro.json sem rede nem GPU')
    s.add_argument('roteiro')
    s.set_defaults(fn=_validar)

    s = sub.add_parser('gerar', help='escreve <pasta>/roteiro.json a partir de um tema (API do Claude, precisa de ANTHROPIC_API_KEY)')
    s.add_argument('tema')
    s.add_argument('pasta')
    s.add_argument('--modelo', default='claude-opus-5-5', help='modelo do Claude (padrão claude-opus-5-5)')
    s.set_defaults(fn=_gerar)

    s = sub.add_parser('montar',help='narração + Whisper + mapas + composições HyperFrames em <pasta>/video')
    s.add_argument('pasta', help='pasta com roteiro.json (saídas vão para tmp/, video/ e tempos.json dentro dela)')
    s.add_argument('--sfx', help='pasta com efeitos .mp3 (pop, click, whoosh...); padrão <pasta>/sfx; opcional')
    s.add_argument('--musica', help='pasta com as músicas citadas em "musicas"; padrão <pasta>/musica; opcional')
    s.set_defaults(fn=_montar)

    s = sub.add_parser('midia', help='busca/baixa fotos e vídeos de licença livre no Wikimedia Commons')
    s.add_argument('acao', choices=['busca', 'baixa'])
    s.add_argument('pasta')
    s.add_argument('arquivo', help='buscas.json ou escolhas.json')
    s.set_defaults(fn=_midia)

    s = sub.add_parser('render', help='renderiza <pasta>/video em blocos e junta em <pasta>/final.mp4')
    s.add_argument('pasta')
    s.add_argument('--bloco', type=float, default=90.0, help='segundos por bloco (padrão 90)')
    s.set_defaults(fn=_render)
    return p


def main(argv=None):
    a = parser().parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
