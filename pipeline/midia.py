"""Mídia real para os cortes: busca no Wikimedia Commons só com licença livre para uso comercial
(domínio público, CC0, CC BY; nunca SA/NC/ND), folha de miniaturas para escolher e download do trecho usado.

  python -m pipeline midia busca <pasta> buscas.json   -> <pasta>/midia/cand-<id>.jpg (+ candidatos.json)
  python -m pipeline midia baixa <pasta> escolhas.json -> <pasta>/video/assets/broll/*.jpg|mp4 + fontes/creditos-midia.json

buscas.json:   [{"id": "ouro", "q": "gold nugget", "tipo": "img"|"video"}, ...]
escolhas.json: [{"id": "ouro", "n": 3, "ini": 12.0, "dur": 3.0}, ...]   (n = número na folha; ini/dur só para vídeo)
"""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import FFMPEG, UA

API = 'https://commons.wikimedia.org/w/api.php'
LIVRE = re.compile(r'^(public domain|pd|cc0|cc by( \d\.\d)?( br| igo)?)$')
LARGURA_MIN = 900  # px: foto menor que isso fica borrada em 1080p
TENTATIVAS = 5


def licenca_livre(nome):
    """True para domínio público, CC0 e CC BY (qualquer versão); False para SA, NC, ND e o resto."""
    return bool(LIVRE.match(nome.strip().lower()))


def _com_retentativa(fazer):
    """Commons limita taxa com HTTP 429: espera cada vez mais e tenta de novo."""
    for k in range(TENTATIVAS):
        try:
            return fazer()
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(20 * (k + 1))
    raise SystemExit('Commons: 429 persistente')


def api(**p):
    url = API + '?' + urllib.parse.urlencode(p)
    return _com_retentativa(lambda: json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60)))


def filtra(paginas, tipo='img', n=12):
    """Páginas da API (prop=imageinfo) -> candidatos com licença livre, na ordem de relevância da busca."""
    out = []
    for pg in sorted(paginas, key=lambda x: x.get('index', 0)):
        ii = pg['imageinfo'][0]
        meta = ii.get('extmetadata', {})
        lic = meta.get('LicenseShortName', {}).get('value', '').strip()
        if not licenca_livre(lic):
            continue
        if tipo == 'img' and (ii.get('width', 0) < LARGURA_MIN or ii.get('width', 0) < ii.get('height', 1) * 0.9):
            continue  # pequena demais ou em pé
        autor = re.sub('<[^>]+>', '', meta.get('Artist', {}).get('value', '')).strip()[:90]
        out.append({'titulo': pg['title'][5:], 'licenca': lic, 'autor': autor, 'w': ii.get('width'), 'h': ii.get('height'),
                    'dur': ii.get('duration'), 'thumb': ii.get('thumburl'), 'url': ii.get('url')})
        if len(out) >= n:
            break
    return out


def busca(q, tipo='img', n=12):
    """Resultados com licença livre: título, licença, autor, tamanho, duração e URL de miniatura (320 px)."""
    d = api(action='query', format='json', generator='search', gsrsearch=('filetype:video ' if tipo == 'video' else 'filetype:bitmap ') + q,
            gsrnamespace=6, gsrlimit=50, prop='imageinfo', iiprop='size|extmetadata|url|mediatype', iiurlwidth=320,
            iiextmetadatafilter='LicenseShortName|Artist')
    return filtra(d.get('query', {}).get('pages', {}).values(), tipo, n)


def baixa(url, destino):
    def fazer():
        dado = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()
        with open(destino, 'wb') as f:
            f.write(dado)
        return destino
    return _com_retentativa(fazer)


def folha(cands, titulo, saida):
    """Grade 6xN de miniaturas numeradas (vídeo: quadro do meio), para escolher olhando."""
    from PIL import Image, ImageDraw, ImageFont

    W, H, C = 320, 200, 6
    L = max(1, (len(cands) + C - 1) // C)
    img = Image.new('RGB', (W * C, (H + 22) * L + 40), (20, 20, 24))
    d = ImageDraw.Draw(img)
    f = ImageFont.load_default(18)
    d.text((10, 10), titulo, fill=(255, 210, 63), font=f)
    tmp = saida + '.tmp'
    for k, c in enumerate(cands):
        x, y = (k % C) * W, 40 + (k // C) * (H + 22)
        try:
            baixa(c['thumb'], tmp)
            t = Image.open(tmp).convert('RGB')
            t.thumbnail((W - 6, H - 6))
            img.paste(t, (x + 3, y + 3))
        except (OSError, urllib.error.URLError) as e:
            print(f'  sem miniatura para {c["titulo"]}: {e}')
            d.text((x + 10, y + 80), 'sem miniatura', fill=(200, 80, 80), font=f)
        extra = f' {c["dur"]:.0f}s' if c.get('dur') else f' {c["w"]}px'
        d.text((x + 4, y + H), f'{k + 1}. {c["licenca"][:12]}{extra}', fill=(230, 230, 230), font=f)
        time.sleep(0.4)
    if os.path.exists(tmp):
        os.remove(tmp)
    img.save(saida, quality=82)


def derivado(titulo):
    """Melhor transcodificação do vídeo (1080p/720p webm) para o ffmpeg ler só o trecho."""
    d = api(action='query', format='json', titles='File:' + titulo, prop='videoinfo', viprop='derivatives|url')
    vi = list(d['query']['pages'].values())[0]['videoinfo'][0]
    ders = [x for x in vi.get('derivatives', []) if x.get('height', 0) >= 480]
    ders.sort(key=lambda x: (x.get('height', 0) > 1080, -x.get('height', 0)))
    return ders[0]['src'] if ders else vi['url']


def corta_video(titulo, destino, ini, dur):
    """Baixa só o trecho [ini, ini+dur] direto da URL remota, já em 1080p30 sem áudio."""
    url = derivado(titulo)
    vf = 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30'
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-user_agent', UA['User-Agent'], '-ss', str(ini), '-i', url, '-t', str(dur),
                    '-an', '-vf', vf, '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-pix_fmt', 'yuv420p', destino], check=True)


def _le_json(arq, padrao):
    if not os.path.exists(arq):
        return padrao
    with open(arq, encoding='utf8') as f:
        return json.load(f)


def _grava_json(arq, dado):
    os.makedirs(os.path.dirname(arq), exist_ok=True)
    with open(arq, 'w', encoding='utf8') as f:
        json.dump(dado, f, ensure_ascii=False, indent=1)


def executar_busca(pasta, buscas):
    md = os.path.join(pasta, 'midia')
    cand_arq = os.path.join(md, 'candidatos.json')
    cands = _le_json(cand_arq, {})
    for b in buscas:
        if b['id'] in cands and not b.get('refaz'):
            continue
        tipo = b.get('tipo', 'img')
        cands = {**cands, b['id']: {'tipo': tipo, 'lista': busca(b['q'], tipo)}}
        _grava_json(cand_arq, cands)
        folha(cands[b['id']]['lista'], f'{b["id"]}  ({tipo}: {b["q"]})', os.path.join(md, f'cand-{b["id"]}.jpg'))
        print(b['id'], len(cands[b['id']]['lista']), flush=True)
        time.sleep(1)


def executar_baixa(pasta, escolhas):
    from PIL import Image

    cands = _le_json(os.path.join(pasta, 'midia', 'candidatos.json'), None)
    if cands is None:
        raise SystemExit('rode "midia busca" antes de "midia baixa"')
    dst = os.path.join(pasta, 'video', 'assets', 'broll')
    os.makedirs(dst, exist_ok=True)
    cred_arq = os.path.join(pasta, 'fontes', 'creditos-midia.json')
    cred = _le_json(cred_arq, {})
    for e in escolhas:
        c = cands[e['id']]['lista'][e['n'] - 1]
        nome = e.get('arq', e['id'])  # o mesmo candidato pode virar arquivos com nomes diferentes
        if cands[e['id']]['tipo'] == 'video':
            saida = os.path.join(dst, nome + '.mp4')
            if not os.path.exists(saida):
                corta_video(c['titulo'], saida, e.get('ini', 0), e.get('dur', 3.5))
        else:
            saida = os.path.join(dst, nome + '.jpg')
            if not os.path.exists(saida):
                baixa(API.replace('api.php', 'thumb.php') + '?' + urllib.parse.urlencode({'f': c['titulo'], 'w': 1920}), saida)
                Image.open(saida).convert('RGB').save(saida, quality=90)
        cred = {**cred, nome: f"{c['titulo']} - {c['autor'] or 'autor desconhecido'} - {c['licenca']} - Wikimedia Commons"}
        _grava_json(cred_arq, cred)
        print('ok', nome, os.path.basename(saida), flush=True)
        time.sleep(1.5)


def main(acao, pasta, arq):
    pasta = os.path.abspath(pasta)
    with open(arq, encoding='utf8') as f:
        pedidos = json.load(f)
    if acao == 'busca':
        executar_busca(pasta, pedidos)
    else:
        executar_baixa(pasta, pedidos)
