import pytest

from pipeline.legendas import LIGACAO, acha, alinha, esc, grupos, legendas_html, norm


def palavras(texto, passo=0.3, pausa_em=()):
    out, t = [], 0.0
    for i, w in enumerate(texto.split()):
        out.append({'text': w, 'start': round(t, 3), 'end': round(t + passo - 0.05, 3)})
        t += passo + (0.5 if i in pausa_em else 0)
    return out


def test_norm_tira_acento_caixa_e_pontuacao():
    assert norm('Brasília,') == 'brasilia'
    assert norm('CONSTITUIÇÃO!') == 'constituicao'
    assert norm('—') == ''


def test_esc_escapa_html_e_destaca():
    assert esc('a <b> **c**') == 'a &lt;b&gt; <b>c</b>'


def test_alinha_casa_por_posicao_e_interpola_faltantes():
    ouvidas = [('O', 0.0, 0.2), ('Brasil', 0.2, 0.6), ('capital', 1.4, 1.9)]  # o Whisper não ouviu "mudou a"
    ws = alinha('o Brasil mudou a capital', ouvidas)
    assert [w['text'] for w in ws] == ['o', 'Brasil', 'mudou', 'a', 'capital']
    assert ws[1] == {'text': 'Brasil', 'start': 0.2, 'end': 0.6}
    assert ws[2]['start'] == 0.6 and ws[3]['end'] == 1.4  # interpolado entre "Brasil" e "capital"
    assert ws[2]['end'] == ws[3]['start']


def test_alinha_sem_vizinha_a_direita_usa_passo_fixo():
    ws = alinha('um dois tres', [('um', 0.0, 0.3)])
    assert ws[1]['start'] == 0.3 and ws[2]['end'] == pytest.approx(1.0)


def test_acha_enesima_ocorrencia_e_erro():
    ws = palavras('o rio e o rio de janeiro')
    assert acha(ws, 'rio') == ws[1]['start']
    assert acha(ws, 'Rio de') == ws[4]['start']
    assert acha(ws, 'rio', n=1) == ws[4]['start']
    with pytest.raises(SystemExit):
        acha(ws, 'brasilia')


def test_grupos_maximo_4_e_quebra_em_pontuacao():
    ws = palavras('Um dois tres quatro cinco seis. Sete oito')
    gs = grupos(ws)
    assert all(1 <= len(g) <= 4 for g in gs)
    assert [i for g in gs for i in g] == list(range(len(ws)))  # cobre tudo, em ordem
    assert any(g[-1] == 5 for g in gs)  # "seis." fecha grupo


def test_grupos_cinco_vira_3_mais_2():
    assert [len(g) for g in grupos(palavras('aa bb cc dd ee'))] == [3, 2]


def test_grupos_nao_termina_em_palavra_de_ligacao():
    ws = palavras('mudou a capital do Rio de Janeiro para o meio do cerrado')
    for g in grupos(ws)[:-1]:
        assert norm(ws[g[-1]]['text']) not in LIGACAO


def test_grupos_quebra_em_pausa():
    ws = palavras('aa bb cc dd', pausa_em=(1,))
    assert grupos(ws)[0] == [0, 1]


def test_legendas_html_tem_um_grupo_por_legenda():
    ws = palavras('Uma frase curta. Outra')
    out = legendas_html(ws, 5.0)
    assert out.count('class="grupo"') == len(grupos(ws))
    assert 'window.__timelines["legendas"]' in out
