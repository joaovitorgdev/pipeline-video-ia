"""(Opcional) Publica um vídeo no YouTube Studio com Playwright, sem limite de tamanho de arquivo
(o input de arquivo é preenchido direto com o caminho no disco).

Nenhuma credencial é guardada pelo script: na primeira execução você faz login na janela do navegador e
a sessão fica no perfil local indicado por PUBLICAR_PERFIL (padrão ~/.pipeline-video-ia/perfil-youtube),
fora do repositório. Os textos procurados na tela são os do Studio em português.

Uso:
    python publicar/youtube.py <video.mp4> <titulo> <descricao.txt> [--thumb capa.png] [--privado] [--yes]

--thumb    miniatura (png/jpg)
--privado  publica como privado (para conferir antes)
--yes      pula a pausa de revisão final
"""
import argparse
import os

PERFIL = os.environ.get('PUBLICAR_PERFIL', os.path.join(os.path.expanduser('~'), '.pipeline-video-ia', 'perfil-youtube'))
UPLOAD_TIMEOUT_MS = 10 * 60 * 1000


def clica_visivel(page, texto, exato=False):
    """Clica na primeira ocorrência VISÍVEL do texto.

    get_by_text(...).first pega o primeiro nó do DOM que contém o texto. No Studio, para 'Público' esse nó era
    um tooltip invisível, e o click() ficava 30 s esperando até estourar o timeout. Filtrar por is_visible()
    chega no controle real.
    """
    for op in page.get_by_text(texto, exact=exato).all():
        if op.is_visible():
            op.click()
            return True
    return False


def preenche(page, campo, texto):
    campo.click()
    page.keyboard.press('Control+A')
    page.keyboard.type(texto)


def envia(page, a, descricao):
    page.get_by_role('button', name='Criar', exact=True).click()
    page.get_by_text('Enviar vídeos', exact=False).click()
    page.wait_for_timeout(1000)
    page.locator('input[type=file]').first.set_input_files(a.video)
    print('Enviando vídeo (demora com arquivo grande)...')
    page.wait_for_selector('#textbox', timeout=UPLOAD_TIMEOUT_MS)
    preenche(page, page.locator('#textbox').first, a.titulo)
    preenche(page, page.locator('#textbox').nth(1), descricao)
    if a.thumb:
        inputs = page.locator('input[type=file]')
        if inputs.count() > 1:
            inputs.nth(1).set_input_files(a.thumb)
    # "Feito para crianças?" e "Conteúdo alterado ou sintético?": marca as opções "Não" visíveis.
    # Revise na pausa final: se o vídeo usa mídia sintética realista, a resposta certa pode ser "Sim".
    for op in page.get_by_text('Não', exact=True).all():
        if op.is_visible():
            op.click()
    for _ in range(3):
        botao = page.get_by_role('button', name='Próxima')
        if botao.count():
            botao.click()
            page.wait_for_timeout(1500)
    clica_visivel(page, 'Privado' if a.privado else 'Público')


def main():
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('video')
    ap.add_argument('titulo')
    ap.add_argument('descricao', help='arquivo .txt com a descrição')
    ap.add_argument('--thumb')
    ap.add_argument('--privado', action='store_true')
    ap.add_argument('--yes', action='store_true')
    a = ap.parse_args()
    a.video = os.path.abspath(a.video)
    a.thumb = os.path.abspath(a.thumb) if a.thumb else None
    if not os.path.exists(a.video):
        raise SystemExit(f'vídeo não existe: {a.video}')
    with open(a.descricao, encoding='utf8') as f:
        descricao = f.read()

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PERFIL, headless=False, channel='chrome', viewport={'width': 1440, 'height': 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto('https://studio.youtube.com')
        try:
            page.wait_for_selector('text=Painel do canal', timeout=5000)
        except Exception:  # noqa: BLE001 - sem painel = ainda não logado
            print('Primeira vez: faça login na janela que abriu. No Painel do canal, clique "Resume" no Playwright Inspector.')
            page.pause()
            page.goto('https://studio.youtube.com')
        try:
            envia(page, a, descricao)
        except Exception as e:  # noqa: BLE001 - deixa a pessoa terminar à mão sem perder o upload
            print(f'Erro em algum passo: {e}')
            print('A janela ficou aberta: ajuste à mão e clique "Resume" para continuar, ou feche para cancelar.')
            page.pause()
        if not a.yes:
            print('Confira título, descrição, miniatura, "conteúdo alterado ou sintético" e visibilidade.')
            print('Clique "Resume" no Playwright Inspector para publicar, ou feche a janela para cancelar.')
            page.pause()
        for nome in ('Publicar', 'Salvar'):
            botao = page.get_by_role('button', name=nome)
            if botao.count():
                botao.click()
                break
        page.wait_for_timeout(3000)
        print('Feito.')
        ctx.close()


if __name__ == '__main__':
    main()
