"""Configuração por variáveis de ambiente (nada de caminho absoluto nem credencial no código)."""
import os

# Cache de tiles de mapa e malhas do IBGE (pode passar de dezenas de MB: fica fora do git).
CACHE = os.path.abspath(os.environ.get('PIPELINE_CACHE', 'cache'))
# Wikimedia pede um User-Agent identificável com contato; sem ele o upload.wikimedia.org devolve 429.
UA = {'User-Agent': os.environ.get('PIPELINE_UA', 'pipeline-video-ia/1.0 (defina PIPELINE_UA com um contato)')}
FFMPEG = os.environ.get('FFMPEG', 'ffmpeg')
FFPROBE = os.environ.get('FFPROBE', 'ffprobe')
HYPERFRAMES = os.environ.get('HYPERFRAMES', 'hyperframes@0.9.34')  # pacote npm usado via npx
WHISPER_MODELO = os.environ.get('WHISPER_MODELO', 'small')
