"""(Opcional) Publica um vídeo no TikTok Studio com Playwright (o upload pelo navegador não tem o limite
de tamanho de integrações que enviam o arquivo pela API).

Nenhuma credencial é guardada pelo script: na primeira execução você faz login na janela do navegador e
a sessão fica no perfil local indicado por PUBLICAR_PERFIL (padrão ~/.pipeline-video-ia/perfil-tiktok),
fora do repositório. Os textos procurados na tela são os do Studio em português.

Uso:
    python publicar/tiktok.py <video.mp4> "<legenda>" [--ia] [--yes]

--ia   liga o rótulo "Conteúdo gerado por IA"
--yes  publica sem a confirmação no terminal
"""
import argparse
import os

PERFIL = os.environ.get('PUBLICAR_PERFIL', os.path.join(os.path.expanduser('~'), '.pipeline-video-ia', 'perfil-tiktok'))
UPLOAD = 'https://www.tiktok.com/tiktokstudio/upload'
UPLOAD_TIMEOUT_MS = 10 * 60 * 1000


def main():
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('video')
    ap.add_argument('legenda')
    ap.add_argument('--ia', action='store_true')
    ap.add_argument('--yes', action='store_true')
    a = ap.parse_args()
    video = os.path.abspath(a.video)
    if not os.path.exists(video):
        raise SystemExit(f'vídeo não existe: {video}')

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(PERFIL, headless=False, channel='chrome', viewport={'width': 1440, 'height': 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(UPLOAD)
        if page.get_by_text('Fazer login', exact=False).count() or 'login' in page.url:
            input('Primeira vez: faça login na janela que abriu e, com a tela de upload visível, aperte Enter aqui... ')
            page.goto(UPLOAD)

        page.locator('input[type=file]').set_input_files(video)
        print('Enviando vídeo...')
        page.get_by_text('Enviado', exact=False).wait_for(timeout=UPLOAD_TIMEOUT_MS)

        page.locator('[contenteditable="true"]').first.click()
        page.keyboard.press('Control+A')
        page.keyboard.type(a.legenda)

        mais = page.get_by_text('Exibir mais', exact=False)
        if mais.count():
            mais.click()
        if a.ia:
            linha = page.get_by_text('Conteúdo gerado por IA', exact=False).first.locator('..')
            toggle = linha.locator('input, [role=switch]').first
            if toggle.count() and toggle.get_attribute('aria-checked') != 'true':
                toggle.click()

        if not a.yes:
            input('Confira a tela do navegador. Enter para publicar (ou feche a janela para cancelar)... ')
        page.get_by_role('button', name='Publicar').click()
        page.wait_for_timeout(3000)
        print('Publicado.')
        ctx.close()


if __name__ == '__main__':
    main()
