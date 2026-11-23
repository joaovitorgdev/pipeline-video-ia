import pytest

from pipeline.cenas import Cena


def ws(texto):
    return [{'text': w, 'start': i * 0.5, 'end': i * 0.5 + 0.4} for i, w in enumerate(texto.split())]


def test_cena_papel_sincroniza_peca_com_palavra():
    c = {'narracao': 'levar a capital para o interior', 'fundo': {'tipo': 'papel'},
         'fx': [{'em': 'interior', 'tipo': 'chip', 'texto': 'INTERIOR <b>'}]}
    cn = Cena('c04', c, ws(c['narracao']), 4.0, {}, video='nao-usado')
    out = cn.monta(0.0)
    assert 'data-composition-id="c04"' in out
    assert 'Kit.E.chip(tl, "#c04-f1", 2.440);' in out  # 6ª palavra (2,5 s) com desl padrão de -0,06 s
    assert 'INTERIOR &lt;b&gt;' in out  # texto do roteiro escapado
    assert cn.sons == [(2.44, 'pop', 0.42)]


def test_peca_nova_no_mesmo_slot_tira_a_anterior():
    c = {'narracao': 'um dois tres', 'fundo': {'tipo': 'papel'},
         'fx': [{'em': 'um', 'tipo': 'chip', 'texto': 'A'}, {'em': 'tres', 'tipo': 'chip', 'texto': 'B'}]}
    out = Cena('c01', c, ws(c['narracao']), 2.0, {}, video='x').monta(0.0)
    assert 'Kit.E.sai(tl, "#c01-f1"' in out


def test_peca_de_mapa_sem_mapa_falha_com_mensagem():
    c = {'narracao': 'aqui', 'fundo': {'tipo': 'papel'}, 'fx': [{'em': 'aqui', 'tipo': 'pin', 'lnglat': [0, 0]}]}
    with pytest.raises(SystemExit, match='sem fundo de mapa'):
        Cena('c01', c, ws('aqui'), 1.0, {}, video='x').monta(0.0)
