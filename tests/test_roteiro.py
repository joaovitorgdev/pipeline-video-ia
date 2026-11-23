import json
import os

from pipeline.legendas import acha
from pipeline.roteiro import validar

EXEMPLO = os.path.join(os.path.dirname(__file__), '..', 'exemplos', 'roteiro-exemplo.json')


def exemplo():
    with open(EXEMPLO, encoding='utf8') as f:
        return json.load(f)


def test_exemplo_valido():
    assert validar(exemplo()) == []


def test_ancoras_do_exemplo_existem_na_narracao():
    for c in exemplo()['cenas']:
        ws = [{'text': w, 'start': float(i), 'end': i + 0.5} for i, w in enumerate(c['narracao'].split())]
        for fx in c.get('fx', []):
            if isinstance(fx.get('em'), str) and fx['em'] != '^':
                acha(ws, fx['em'], fx.get('n', 0))  # SystemExit se a âncora não existir


def test_erros_legiveis():
    R = {'vistas': {'v': {'centro': [0, 0], 'zoom': 3, 'camada': 'google'}},
         'musicas': [{'de': 'c09', 'arq': 'm.mp3'}],
         'cenas': [{'narracao': '', 'fundo': {'tipo': 'mapa', 'vista': 'nao-existe'}},
                   {'narracao': 'oi', 'fundo': {'tipo': 'papel'},
                    'fx': [{'tipo': 'pin'}, {'tipo': 'explosao'}, {'tipo': 'chip', 'pos': 'lua'}]}]}
    texto = '\n'.join(validar(R))
    for trecho in ('camada', 'c01: "narracao"', "vista 'nao-existe'", "fx 'pin' só funciona", "fx 'explosao'", "pos 'lua'", 'c09'):
        assert trecho in texto, trecho


def test_sem_cenas():
    assert validar({}) == ['"cenas" deve ser uma lista não vazia']
