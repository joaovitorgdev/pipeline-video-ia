"""Render do projeto HyperFrames em blocos e junção sem recodificar o vídeo.

Motivo: o HyperFrames grava quadros temporários (~1,25 MB por quadro em 1080p); num vídeo de 8 min isso
encheu o disco (ENOSPC) perto do quadro 13.600. Em blocos de 90 s o pico de disco fica pequeno, um bloco
que falha não perde os anteriores (os prontos são pulados) e a junção é instantânea:
  - vídeo: concat demuxer com -c copy (sem recodificar);
  - áudio: cada parte cortada/completada na duração exata do vídeo dela (contando quadros com ffprobe), para
    o atraso do AAC não acumular entre as partes; depois concatena e normaliza em -14 LUFS uma vez só.
"""
import glob
import json
import os
import subprocess

from .config import FFMPEG, FFPROBE, HYPERFRAMES

BLOCO = 90.0  # s
LUFS = -14


def blocos(total, bloco=BLOCO):
    """[(início, fim)] cobrindo [0, total] em pedaços de no máximo `bloco` segundos."""
    if total <= 0 or bloco <= 0:
        raise ValueError('total e bloco precisam ser positivos')
    out, s = [], 0.0
    while s < total - 0.01:
        e = round(min(s + bloco, total), 3)
        out.append((round(s, 3), e))
        s = e
    return out


def renderizar(video_dir, total, partes_dir, bloco=BLOCO, qualidade='delivery'):
    os.makedirs(partes_dir, exist_ok=True)
    for i, (s, e) in enumerate(blocos(total, bloco)):
        out = os.path.join(partes_dir, f'p{i:02d}.mp4')
        if os.path.exists(out) and os.path.getsize(out) > 0:
            print(f'parte {i} já pronta ({s}-{e})')
            continue
        subprocess.run(['npx', '--yes', HYPERFRAMES, 'render', '-o', out, '-q', qualidade, '--start', str(s), '--end', str(e), '--quiet'],
                       cwd=video_dir, check=True, shell=os.name == 'nt')  # npx é .cmd no Windows
        print(f'parte {i} ok ({s}-{e})', flush=True)


def dur_video(p):
    """Duração real do vídeo pelo número de quadros (o 'duration' do contêiner inclui o áudio)."""
    out = subprocess.run([FFPROBE, '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries',
                          'stream=nb_read_packets,r_frame_rate', '-of', 'json', p], capture_output=True, text=True, check=True).stdout
    return duracao_ffprobe(out)


def duracao_ffprobe(saida_json):
    """Quadros / fps a partir do JSON do ffprobe (por nome, não pela ordem das colunas)."""
    st = json.loads(saida_json)['streams'][0]
    a, b = st['r_frame_rate'].split('/')
    return int(st['nb_read_packets']) / (int(a) / int(b))


def juntar(partes_dir, final):
    partes = sorted(glob.glob(os.path.join(partes_dir, 'p*.mp4')))
    if not partes:
        raise SystemExit(f'nenhuma parte em {partes_dir}')
    lista = os.path.join(partes_dir, 'lista.txt')
    with open(lista, 'w', encoding='utf8') as f:
        f.write(''.join(f"file '{os.path.basename(p)}'\n" for p in partes))
    so_video = os.path.join(partes_dir, 'so-video.mp4')
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lista, '-map', '0:v', '-c', 'copy', so_video], check=True)
    wavs = []
    for k, p in enumerate(partes):
        d = dur_video(p)
        w = os.path.join(partes_dir, f'a{k:02d}.wav')
        subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', p, '-map', '0:a', '-af', f'atrim=0:{d:.4f},apad=whole_dur={d:.4f}',
                        '-ar', '48000', '-ac', '2', w], check=True)
        wavs.append(w)
    filtro = ''.join(f'[{k + 1}:a]' for k in range(len(wavs))) + f'concat=n={len(wavs)}:v=0:a=1,loudnorm=I={LUFS}:TP=-1.5:LRA=11[a]'
    entradas = [x for w in wavs for x in ('-i', w)]  # entrada 0 = vídeo; 1..n = áudio das partes
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', so_video, *entradas, '-filter_complex', filtro, '-map', '0:v', '-map', '[a]',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', final], check=True)
    print('ok ->', final)
    return final


def main(pasta, bloco=BLOCO):
    import json

    pasta = os.path.abspath(pasta)
    tempos = os.path.join(pasta, 'tempos.json')
    if not os.path.exists(tempos):
        raise SystemExit('rode "python -m pipeline montar" antes do render')
    with open(tempos, encoding='utf8') as f:
        total = json.load(f)['total']
    partes = os.path.join(pasta, 'partes')
    renderizar(os.path.join(pasta, 'video'), total, partes, bloco)
    return juntar(partes, os.path.join(pasta, 'final.mp4'))
