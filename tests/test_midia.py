import pytest

from pipeline.midia import filtra, licenca_livre


@pytest.mark.parametrize('nome', ['Public domain', 'PD', 'CC0', 'CC BY 4.0', 'cc by 2.0', 'CC BY 3.0 BR', 'CC BY 3.0 IGO', 'CC BY'])
def test_licencas_livres(nome):
    assert licenca_livre(nome)


@pytest.mark.parametrize('nome', ['CC BY-SA 4.0', 'CC BY-NC 2.0', 'CC BY-ND 3.0', 'CC BY-NC-SA 4.0', 'GFDL', 'All rights reserved', ''])
def test_licencas_rejeitadas(nome):
    assert not licenca_livre(nome)


def pagina(idx, lic, w=1920, h=1080, titulo='x.jpg'):
    return {'index': idx, 'title': 'File:' + titulo, 'imageinfo': [{
        'width': w, 'height': h, 'thumburl': 't', 'url': 'u',
        'extmetadata': {'LicenseShortName': {'value': lic}, 'Artist': {'value': '<a href="#">Fulano</a>'}}}]}


def test_filtra_licenca_tamanho_orientacao_e_ordem():
    pags = [pagina(3, 'CC BY 4.0', titulo='c.jpg'), pagina(1, 'CC BY-SA 4.0', titulo='a.jpg'),
            pagina(2, 'CC0', titulo='b.jpg'), pagina(4, 'CC0', w=600, titulo='pequena.jpg'),
            pagina(5, 'CC0', w=1000, h=2000, titulo='em-pe.jpg')]
    out = filtra(pags, 'img')
    assert [c['titulo'] for c in out] == ['b.jpg', 'c.jpg']
    assert out[0]['autor'] == 'Fulano'  # HTML removido do campo de autor


def test_filtra_video_nao_exige_paisagem_e_respeita_n():
    pags = [pagina(i, 'CC0', w=400, h=800, titulo=f'{i}.webm') for i in range(5)]
    assert len(filtra(pags, 'video', n=3)) == 3
