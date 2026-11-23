"""roteiro.json -> projeto HyperFrames pronto para renderizar.

Passos: voz por cena (edge-tts) -> Whisper por cena (com cache) -> mapas -> uma composição por cena
-> index.html (cenas, voz, música, efeitos) + legendas palavra a palavra + pergunta fixa no topo.
Depois: python -m pipeline render <pasta>  (ou npx hyperframes render dentro de <pasta>/video).
"""
import json
import os
import shutil
import subprocess

from . import legendas, tts
from .cenas import Cena, H, W
from .config import FFPROBE
from .roteiro import carregar

AQUI = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(AQUI, 'runtime')
# s: entre cenas, antes de capítulo, cartão de capítulo, final (8 s: tela final do YouTube pede no mínimo 5 s)
GAP, GAP_CAP, LEAD_CAP, FIM_EXTRA = 0.35, 0.5, 2.1, 8.0
SFX_MIN_INTERVALO = 0.22  # s: efeitos mais próximos que isso viram ruído
# Momento do "pico" de cada efeito (para alinhar o impacto com a entrada da peça) e duração, em segundos.
# Com outros arquivos de efeito, sobrescreva em <sfx>/sfx.json: {"pop": {"pico": 0.1, "dur": 0.7}, ...}
PICO = {'click': 0.073, 'impact-bass-1': 0.073, 'impact-bass-2': 0.073, 'pop': 0.12, 'sparkle': 0.027, 'whoosh': 0.162,
        'whoosh-short': 0.162}
DURS = {'click': 0.37, 'impact-bass-1': 2.12, 'impact-bass-2': 2.12, 'pop': 0.72, 'sparkle': 1.8, 'whoosh': 0.57, 'whoosh-short': 0.57}
CROSSFADE_MUSICA = 2.0
HYPERFRAMES_JSON = {
    '$schema': 'https://hyperframes.heygen.com/schema/hyperframes.json',
    'paths': {'blocks': 'compositions', 'components': 'compositions/components', 'assets': 'assets'},
    'media': {'autoProxy': True},
}


def _grava(arq, texto):
    with open(arq, 'w', encoding='utf8') as f:
        f.write(texto)


def _le_json(arq, padrao):
    if not os.path.exists(arq):
        return padrao
    with open(arq, encoding='utf8') as f:
        return json.load(f)


def palavras_por_cena(tmp, cenas):
    """Tempos de palavra de cada cena. Cache em tmp/palavras.json: só roda o Whisper na cena cujo texto mudou."""
    cache = os.path.join(tmp, 'palavras.json')
    pal = _le_json(cache, {})
    modelo = None
    for i, c in enumerate(cenas):
        cid = f'c{i + 1:02d}'
        if pal.get(cid, {}).get('texto') == c['narracao']:
            continue
        modelo = modelo or legendas.carrega_modelo()
        pal = {**pal, cid: {'texto': c['narracao'], 'palavras': legendas.tempos(modelo, os.path.join(tmp, f'voz_{i + 1:02d}.wav'), c['narracao'])}}
        with open(cache, 'w', encoding='utf8') as f:
            json.dump(pal, f, ensure_ascii=False)
    return pal


def linha_do_tempo(tmp, cenas, pal):
    """Emenda as vozes com pausas e devolve (áudio, sr, palavras globais, {cid: (início, dur, lead, palavras locais)}, total)."""
    import numpy as np
    import soundfile as sf

    linha, partes, cursor, cenas_t, sr = [], [], 0.0, {}, tts.SR
    for i, c in enumerate(cenas):
        cid = f'c{i + 1:02d}'
        a, sr = sf.read(os.path.join(tmp, f'voz_{i + 1:02d}.wav'), dtype='float32')
        lead = LEAD_CAP if c.get('capitulo') else 0.0
        proxima_cap = i + 1 < len(cenas) and cenas[i + 1].get('capitulo')
        dur = round(lead + len(a) / sr + (GAP_CAP if proxima_cap else GAP) + (FIM_EXTRA if i + 1 == len(cenas) else 0), 3)
        partes += [np.zeros(int(lead * sr), np.float32), a, np.zeros(max(0, int((dur - lead) * sr) - len(a)), np.float32)]
        ws = [{**w, 'start': round(w['start'] + lead, 3), 'end': round(w['end'] + lead, 3)} for w in pal[cid]['palavras']]
        linha += [{**w, 'start': round(w['start'] + cursor, 3), 'end': round(w['end'] + cursor, 3)} for w in ws]
        cenas_t[cid] = (round(cursor, 3), dur, lead, ws)
        cursor = round(cursor + dur, 3)
    return np.concatenate(partes), sr, linha, cenas_t, round(cursor, 2)


def blocos_pergunta(R, cenas, cenas_t, total):
    """Pergunta fixa: do fim do cartão de cada capítulo até o próximo capítulo."""
    caps = [(cenas_t[f'c{i + 1:02d}'][0] + (LEAD_CAP + 0.4 if c.get('capitulo') else 0.6),
             c.get('capitulo', {}).get('pergunta') or R.get('pergunta', ''))
            for i, c in enumerate(cenas) if c.get('capitulo') or i == 0]
    out = []
    for k, (a, txt) in enumerate(caps):
        b = (caps[k + 1][0] - (LEAD_CAP + 0.4)) if k + 1 < len(caps) else total - FIM_EXTRA + 0.5
        if txt:
            out.append((a, b, txt))
    return out


def efeitos(sons, sfx_dir, video):
    """<audio> dos efeitos sonoros (no máximo um a cada 0,22 s). Sem pasta de efeitos, o vídeo sai sem eles."""
    if not sfx_dir or not os.path.isdir(sfx_dir):
        return []
    pico = {**PICO, **{n: v['pico'] for n, v in _le_json(os.path.join(sfx_dir, 'sfx.json'), {}).items()}}
    durs = {**DURS, **{n: v['dur'] for n, v in _le_json(os.path.join(sfx_dir, 'sfx.json'), {}).items()}}
    os.makedirs(os.path.join(video, 'assets', 'sfx'), exist_ok=True)
    linhas, ult = [], -9.0
    for t, nome, vol in sorted(sons):
        arq = os.path.join(sfx_dir, nome + '.mp3')
        if t - ult < SFX_MIN_INTERVALO or nome not in pico or not os.path.exists(arq):
            continue
        ult = t
        shutil.copy(arq, os.path.join(video, 'assets', 'sfx', nome + '.mp3'))
        ini = max(0.0, round(t + 1 / 30 - pico[nome], 3))
        linhas.append(f'      <audio id="sfx{len(linhas)}" src="assets/sfx/{nome}.mp3" data-start="{ini}" data-duration="{durs[nome]}" '
                      f'data-track-index="{50 + len(linhas) % 4}" data-volume="{vol}"></audio>')
    return linhas


def duracao(arq):
    return float(subprocess.run([FFPROBE, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', arq],
                                capture_output=True, text=True, check=True).stdout.strip())


def trilhas(R, cenas_t, total, musica_dir, video):
    """<audio> da música de fundo; faixa mais curta que o trecho repete, emendando com 2 s de sobreposição."""
    out, musicas = [], R.get('musicas', [])
    for k, m in enumerate(musicas):
        src = os.path.join(musica_dir or '', m['arq'])
        if not os.path.exists(src):
            print(f'aviso: música {m["arq"]} não achada em {musica_dir}: o vídeo sai sem ela')
            continue
        dst = os.path.join(video, 'assets', 'musica', m['arq'])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)
        ini = cenas_t[m['de']][0]
        fim = cenas_t[musicas[k + 1]['de']][0] + 1.0 if k + 1 < len(musicas) else total
        dm, t0, r = duracao(dst), ini, 0
        while t0 < fim - 1:
            d = min(dm, fim - t0)
            out.append(f'      <audio id="musica{k}r{r}" src="assets/musica/{m["arq"]}" data-start="{t0:.3f}" data-duration="{d:.3f}" '
                       f'data-track-index="{40 + len(out) % 2}" data-volume="{m.get("vol", 0.1)}" data-fade-in="{1.0 if r == 0 else 2.0}" '
                       f'data-fade-out="2.0"></audio>')
            t0, r = t0 + dm - CROSSFADE_MUSICA, r + 1
    return out


def index_html(cenas_t, total, dur_voz, audios):
    hosts = '\n'.join(f'      <div id="{cid}" data-composition-id="{cid}" data-composition-src="compositions/{cid}.html" data-start="{ini}" '
                      f'data-duration="{dur}" data-track-index="1" data-track-kind="graphics" data-width="{W}" data-height="{H}"></div>'
                      for cid, (ini, dur, _, _) in cenas_t.items())
    with open(os.path.join(RUNTIME, 'tema.css'), encoding='utf8') as f:
        css = f.read()
    return f'''<!doctype html>
<html lang="pt-BR" data-resolution="landscape">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <script src="assets/timing.js"></script>
    <script src="assets/kit.js"></script>
    <style>
{css}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{W}" data-height="{H}">
{hosts}
      <div id="pergunta" data-composition-id="pergunta" data-composition-src="compositions/pergunta.html" data-start="0" data-duration="{total}" data-track-index="2" data-track-kind="graphics" data-width="{W}" data-height="{H}" style="z-index: 8"></div>
      <div id="legendas" data-composition-id="legendas" data-composition-src="compositions/legendas.html" data-start="0" data-duration="{total}" data-track-index="3" data-track-kind="captions" data-width="{W}" data-height="{H}" style="z-index: 10"></div>
      <audio id="voz" src="assets/voz.wav" data-start="0" data-duration="{dur_voz}" data-track-index="30" data-volume="1"></audio>
{chr(10).join(audios)}
    </div>
    <script>window.__timelines = window.__timelines || {{}}; window.__timelines["main"] = gsap.timeline({{ paused: true }});</script>
  </body>
</html>
'''


def main(pasta, sfx_dir=None, musica_dir=None):
    import soundfile as sf

    pasta = os.path.abspath(pasta)
    R = carregar(os.path.join(pasta, 'roteiro.json'))
    creditos = _le_json(os.path.join(pasta, 'fontes', 'creditos-midia.json'), {})
    cenas = R['cenas']
    tmp, video = os.path.join(pasta, 'tmp'), os.path.join(pasta, 'video')
    for d in (tmp, os.path.join(video, 'assets', 'mapas'), os.path.join(video, 'compositions')):
        os.makedirs(d, exist_ok=True)
    tts.narra(tmp, cenas)                                              # 1) voz
    pal = palavras_por_cena(tmp, cenas)                                # 2) tempos
    voz, sr, linha, cenas_t, total = linha_do_tempo(tmp, cenas, pal)
    sf.write(os.path.join(video, 'assets', 'voz.wav'), voz, sr, subtype='PCM_16')
    sons = []
    for i, c in enumerate(cenas):                                      # 3) mapas e cenas
        cid = f'c{i + 1:02d}'
        ini, dur, lead, ws = cenas_t[cid]
        cn = Cena(cid, c, ws, dur, R.get('vistas', {}), video, creditos)
        _grava(os.path.join(video, 'compositions', f'{cid}.html'), cn.monta(lead))
        sons += [(ini + t, nome, vol) for t, nome, vol in cn.sons]
    shutil.copy(os.path.join(RUNTIME, 'kit.js'), os.path.join(video, 'assets', 'kit.js'))  # 4) runtime e áudio
    audios = trilhas(R, cenas_t, total, musica_dir or os.path.join(pasta, 'musica'), video)
    audios += efeitos(sons, sfx_dir or os.path.join(pasta, 'sfx'), video)
    _grava(os.path.join(video, 'index.html'), index_html(cenas_t, total, round(len(voz) / sr, 3), audios))  # 5) index
    timing = {'total': total, 'cenas': {k: [v[0], v[1]] for k, v in cenas_t.items()}, 'words': linha}
    _grava(os.path.join(video, 'assets', 'timing.js'), '// gerado por pipeline/montar.py\nwindow.TIMING = ' + json.dumps(timing, ensure_ascii=False) + ';\n')
    _grava(os.path.join(video, 'compositions', 'legendas.html'), legendas.legendas_html(linha, total))
    _grava(os.path.join(video, 'compositions', 'pergunta.html'), legendas.pergunta_html(blocos_pergunta(R, cenas, cenas_t, total), total))
    _grava(os.path.join(video, 'hyperframes.json'), json.dumps(HYPERFRAMES_JSON, indent=2))
    nome = os.path.basename(pasta)
    _grava(os.path.join(video, 'meta.json'), json.dumps({'id': nome, 'name': nome}, indent=2))
    capitulos = [(cenas_t[f'c{i + 1:02d}'][0], c['capitulo']['titulo']) for i, c in enumerate(cenas) if c.get('capitulo')]
    _grava(os.path.join(pasta, 'tempos.json'), json.dumps({'total': total, 'capitulos': capitulos}, ensure_ascii=False, indent=1))
    print(f'{len(cenas)} cenas, {total / 60:.1f} min, {len(audios)} faixas de música/efeito')
    for t, tit in capitulos:
        print(f'  {int(t // 60)}:{int(t % 60):02d} {tit}')
