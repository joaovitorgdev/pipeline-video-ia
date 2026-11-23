"""Narração: uma voz por cena (tmp/voz_NN.wav) com voz neural pt-BR via edge-tts.

Só refaz as cenas cujo texto mudou (o texto usado fica ao lado, em voz_NN.txt): editar uma frase do roteiro
não regrava o vídeo inteiro. Voz, ritmo e tom: EDGE_VOZ, EDGE_RITMO, EDGE_TOM.

Observação de licença: o edge-tts usa o serviço de leitura em voz alta do navegador. Para uso comercial,
troque por um serviço de TTS com licença explícita (a função `fala` é o único ponto a mudar).
"""
import asyncio
import io
import os
import subprocess

from .config import FFMPEG

VOZ = os.environ.get('EDGE_VOZ', 'pt-BR-AntonioNeural')
RITMO = os.environ.get('EDGE_RITMO', '-6%')  # documentário: ~140 palavras/min
TOM = os.environ.get('EDGE_TOM', '-2Hz')
SR = 24000
TENTATIVAS = 3
LIMIAR_VOZ = 500  # RMS (int16) acima do qual consideramos que há fala


def apara(pcm, sr=SR, antes=0.12, depois=0.35):
    """Silêncio uniforme nas pontas de cada cena (o TTS devolve pausas de tamanhos variados). pcm: array int16."""
    import numpy as np

    win = sr // 100
    rms = np.sqrt(np.convolve(pcm.astype(float) ** 2, np.ones(win) / win, 'same'))
    voz = np.where(rms > LIMIAR_VOZ)[0]
    if not len(voz):
        return pcm
    corte = pcm[max(0, voz[0] - win * 3): voz[-1] + win * 6]
    return np.concatenate([np.zeros(int(sr * antes), np.int16), corte, np.zeros(int(sr * depois), np.int16)])


async def fala(texto):
    """Texto -> áudio mono float32 em SR Hz."""
    import edge_tts
    import soundfile as sf

    mp3 = b''.join([c['data'] async for c in edge_tts.Communicate(texto, VOZ, rate=RITMO, pitch=TOM).stream() if c['type'] == 'audio'])
    wav = subprocess.run([FFMPEG, '-loglevel', 'error', '-i', '-', '-ar', str(SR), '-ac', '1', '-f', 'wav', '-'],
                         input=mp3, capture_output=True, check=True).stdout
    return sf.read(io.BytesIO(wav), dtype='float32')[0]


async def _fala_com_retentativa(texto, rotulo):
    for tentativa in range(TENTATIVAS):  # serviço online: rede instável não derruba a narração inteira
        try:
            return await fala(texto)
        except Exception as e:  # noqa: BLE001 - qualquer falha de rede/serviço vale nova tentativa
            if tentativa == TENTATIVAS - 1:
                raise
            print(f'  refazendo {rotulo}: {e}', flush=True)
            await asyncio.sleep(5)


def cenas_pendentes(tmp, cenas):
    """Índices das cenas sem voz gravada ou cujo texto mudou desde a última gravação."""
    def em_dia(i, c):
        wav, txt = (os.path.join(tmp, f'voz_{i + 1:02d}.{ext}') for ext in ('wav', 'txt'))
        if not (os.path.exists(wav) and os.path.exists(txt)):
            return False
        with open(txt, encoding='utf8') as f:
            return f.read() == c['narracao']
    return [i for i, c in enumerate(cenas) if 'narracao' in c and not em_dia(i, c)]


def narra(tmp, cenas):
    """Grava tmp/voz_NN.wav para cada cena pendente."""
    import numpy as np
    import soundfile as sf

    os.makedirs(tmp, exist_ok=True)
    falta = cenas_pendentes(tmp, cenas)
    if not falta:
        return
    print(f'voz: {len(falta)} cenas ({VOZ})', flush=True)

    async def todas():
        for i in falta:
            a = await _fala_com_retentativa(cenas[i]['narracao'], f'cena {i + 1}')
            wav = os.path.join(tmp, f'voz_{i + 1:02d}.wav')
            sf.write(wav, apara((np.clip(a, -1, 1) * 32767).astype(np.int16)), SR, subtype='PCM_16')
            with open(wav[:-4] + '.txt', 'w', encoding='utf8') as f:
                f.write(cenas[i]['narracao'])
            print(f'  cena {i + 1} ok', flush=True)

    asyncio.run(todas())
