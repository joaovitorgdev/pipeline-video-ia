"""Tempo de cada palavra (faster-whisper) e legendas palavra a palavra.

O Whisper transcreve a narração com word_timestamps; as palavras ouvidas são casadas com as do roteiro
por posição (difflib). Palavra do roteiro sem par na transcrição ganha tempo interpolado entre as vizinhas,
então a legenda sempre mostra o texto do roteiro, com a grafia certa, no tempo da fala.
"""
import difflib
import html
import os
import re
import subprocess
import unicodedata

from .config import FFMPEG, WHISPER_MODELO

# Palavras que não podem fechar um grupo de legenda ("a casa DE" / "PEDRA" fica feio).
LIGACAO = {'e', 'o', 'a', 'os', 'as', 'de', 'da', 'do', 'das', 'dos', 'no', 'na', 'nos', 'nas', 'um', 'uma', 'que', 'se', 'em', 'com',
           'por', 'pra', 'para', 'ao', 'à'}
PAUSA_QUEBRA = 0.25  # s de silêncio que quebram o grupo de legenda
PASSO_SEM_PAR = 0.35  # s por palavra quando não há vizinha à direita para interpolar
MAX_PALAVRAS = 4


def norm(w):
    """Minúsculas, sem acento e sem pontuação: 'Brasília,' -> 'brasilia'."""
    w = unicodedata.normalize('NFD', w.lower())
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in w if unicodedata.category(c) != 'Mn'))


def esc(t):
    """Texto do roteiro -> HTML seguro: **x** vira destaque."""
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html.escape(t))


def alinha(texto, ouvidas):
    """Palavras do roteiro com início/fim. ouvidas: [(palavra, inicio, fim)] na ordem da transcrição."""
    script = texto.split()
    m = difflib.SequenceMatcher(None, [norm(w) for w in script], [norm(w[0]) for w in ouvidas], autojunk=False)
    t = [None] * len(script)
    for b in m.get_matching_blocks():
        for k in range(b.size):
            _, ini, fim = ouvidas[b.b + k]
            t[b.a + k] = (round(ini, 3), round(fim, 3))
    for i in range(len(t)):
        if t[i] is None:
            j = i
            while j < len(t) and t[j] is None:
                j += 1
            ini = t[i - 1][1] if i else 0.0
            fim = t[j][0] if j < len(t) else ini + PASSO_SEM_PAR * (j - i)
            passo = (fim - ini) / (j - i)
            for k in range(i, j):
                t[k] = (round(ini + passo * (k - i), 3), round(ini + passo * (k - i + 1), 3))
    return [{'text': w, 'start': s, 'end': e} for w, (s, e) in zip(script, t)]


def carrega_modelo():
    from faster_whisper import WhisperModel

    return WhisperModel(WHISPER_MODELO, device='cpu', compute_type='int8')


def tempos(modelo, wav, texto):
    """Transcreve wav com o Whisper (texto do roteiro como prompt) e alinha com o roteiro."""
    import soundfile as sf

    a16 = wav[:-4] + '_16k.wav'
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', wav, '-ar', '16000', '-ac', '1', a16], check=True)
    a, _ = sf.read(a16, dtype='float32')
    os.remove(a16)
    segs, _ = modelo.transcribe(a, language='pt', word_timestamps=True, initial_prompt=texto)
    return alinha(texto, [(w.word, w.start, w.end) for s in segs for w in s.words])


def acha(words, frase, n=0):
    """Tempo (local) da n-ésima ocorrência da frase nas palavras da cena."""
    alvo = [norm(x) for x in frase.split() if norm(x)]
    k = 0
    for i in range(len(words) - len(alvo) + 1):
        if [norm(w['text']) for w in words[i:i + len(alvo)]] == alvo:
            if k == n:
                return words[i]['start']
            k += 1
    raise SystemExit(f'âncora não achada: {frase!r} (ocorrência {n}) em: {" ".join(w["text"] for w in words)[:200]}')


def _trechos(words):
    """Quebra em pontuação final, vírgula (com 2+ palavras) ou pausa longa."""
    trechos, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        prox = words[i + 1] if i + 1 < len(words) else None
        if (re.search(r'[.:?!…]$', w['text']) or (w['text'].endswith(',') and len(cur) >= 2) or prox is None
                or prox['start'] - w['end'] >= PAUSA_QUEBRA):
            trechos.append(cur)
            cur = []
    return trechos


def grupos(words):
    """Índices das palavras de cada legenda: até 4 palavras, sem terminar em palavra de ligação e sem deixar uma sozinha no fim."""
    out = []
    for tr in _trechos(words):
        k = 0
        while k < len(tr):
            n = min(MAX_PALAVRAS if len(tr) - k != 5 else 3, len(tr) - k)  # 5 vira 3+2, não 4+1
            while n > 1 and k + n < len(tr) and norm(words[tr[k + n - 1]]['text']) in LIGACAO:
                n -= 1
            if len(tr) - (k + n) == 1 and n > 2:
                n -= 1
            out.append(tr[k:k + n])
            k += n
    return out


def legendas_html(words, total, W=1920, H=1080):
    gs = grupos(words)
    corpo, js = [], []
    for g, idx in enumerate(gs):
        ini = max(0.05, words[idx[0]]['start'] - 0.05)
        fim = words[idx[-1]]['end'] + 0.12
        if g + 1 < len(gs):
            fim = min(fim, words[gs[g + 1][0]]['start'] - 0.05)
        spans = ''.join(f'<span id="lg{g}w{k}">{html.escape(words[i]["text"].rstrip(".,:;"))}</span> ' for k, i in enumerate(idx))
        letras = len(' '.join(words[i]['text'] for i in idx))
        tam = max(44, min(64, int(1500 / (letras * 0.8))))
        corpo.append(f'    <div class="grupo" id="lg{g}" style="font-size: {tam}px">{spans.strip()}</div>')
        js.append(f'  tl.fromTo("#lg{g}", {{opacity: 0, scale: 0.85}}, {{opacity: 1, scale: 1, duration: 0.1, ease: "back.out(2.2)"}}, {ini:.3f});')
        for k, i in enumerate(idx):
            js.append(f'  tl.set("#lg{g}w{k}", {{color: "#FFD23F"}}, {words[i]["start"]:.3f});')
            js.append(f'  tl.set("#lg{g}w{k}", {{color: "#ffffff"}}, {max(words[i]["end"], words[i]["start"] + 0.05):.3f});')
        js.append(f'  tl.set("#lg{g}", {{opacity: 0}}, {fim:.3f});')
    return f'''<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    .grupo {{ position: absolute; left: 0; right: 0; top: 925px; text-align: center; opacity: 0; font-family: "Archivo Black", sans-serif;
      line-height: 1.05; color: #fff; padding: 0 160px; white-space: nowrap; -webkit-text-stroke: 13px #0B0F18; paint-order: stroke fill; text-transform: uppercase; }}
  </style>
  <div id="root" data-composition-id="legendas" data-width="{W}" data-height="{H}">
{chr(10).join(corpo)}
  </div>
  <script>
  const tl = gsap.timeline({{ paused: true }});
{chr(10).join(js)}
  tl.set({{}}, {{}}, {total:.3f});
  window.__timelines["legendas"] = tl;
  </script>
</template>
'''


def pergunta_html(blocos, total, W=1920, H=1080):
    """Pergunta fixa no topo, uma por capítulo: blocos = [(ini, fim, texto)]."""
    corpo, js = [], []
    for k, (a, b, txt) in enumerate(blocos):
        corpo.append(f'    <div class="perg" id="pg{k}">{esc(txt)}</div>')
        js.append(f'  tl.fromTo("#pg{k}", {{opacity: 0, y: -16}}, {{opacity: 1, y: 0, duration: 0.25, ease: "power2.out"}}, {a:.3f});')
        js.append(f'  tl.to("#pg{k}", {{opacity: 0, duration: 0.2}}, {b:.3f});')
    return f'''<template>
  <style>
    #root {{ position: absolute; inset: 0; }}
    .perg {{ position: absolute; left: 0; right: 0; top: 34px; text-align: center; opacity: 0; font-family: "Archivo Black", sans-serif; font-size: 44px;
      color: #fff; -webkit-text-stroke: 10px #0B0F18; paint-order: stroke fill; white-space: nowrap; }}
    .perg b {{ color: #FFD23F; font-weight: normal; }}
  </style>
  <div id="root" data-composition-id="pergunta" data-width="{W}" data-height="{H}">
{chr(10).join(corpo)}
  </div>
  <script>
  const tl = gsap.timeline({{ paused: true }});
{chr(10).join(js)}
  tl.set({{}}, {{}}, {total:.3f});
  window.__timelines["pergunta"] = tl;
  </script>
</template>
'''
