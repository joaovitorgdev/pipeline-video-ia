"""Gera um roteiro.json a partir de um tema com a API do Claude (saída estruturada + Pydantic).

Como funciona:
1. O modelo Pydantic `Roteiro` vira JSON Schema e vai junto do pedido (`output_format`),
   então a API só responde JSON nesse formato.
2. O SDK valida a resposta com o próprio `Roteiro`; regras que o schema não expressa
   (o gatilho "em" precisa estar na narração) ficam num validador Pydantic.
3. O dicionário final passa pelo mesmo `validar()` do comando `python -m pipeline validar`.
Se a validação falhar, pede de novo mandando o erro para o modelo corrigir (até TENTATIVAS vezes).
A chave vem só de ANTHROPIC_API_KEY; sem ela o comando avisa e sai, sem afetar o resto do pipeline.
"""
import os
from typing import Literal

import anthropic
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .roteiro import validar

MODELO = 'claude-opus-5-5'
TENTATIVAS = 3

SISTEMA = (
    'Você escreve roteiros curtos de vídeos explicativos de geografia e história do Brasil, em português do Brasil. '
    'A narração é falada por voz sintética: escreva números por extenso e frases curtas. '
    'Cada efeito visual ("fx") aparece quando a narração diz o trecho do campo "em", '
    'que deve ser copiado exatamente da narração da mesma cena.'
)


class ErroGeracao(Exception):
    """Falha que o usuário consegue resolver (sem chave, erro da API, saída inválida)."""


class Fx(BaseModel):
    model_config = ConfigDict(extra='forbid')

    em: str = Field(description='trecho exato da narração desta cena em que o efeito aparece')
    tipo: Literal['chip', 'cartao'] = Field(description='chip = etiqueta curta; cartao = frase de destaque')
    texto: str = Field(description='texto mostrado na tela, curto')


class Cena(BaseModel):
    model_config = ConfigDict(extra='forbid')

    narracao: str = Field(min_length=1, description='uma ou duas frases faladas')
    fx: list[Fx] = Field(max_length=2, description='zero a dois efeitos visuais')

    @model_validator(mode='after')
    def gatilhos_na_narracao(self) -> 'Cena':
        for fx in self.fx:
            if fx.em.lower() not in self.narracao.lower():
                raise ValueError(f'fx "em": {fx.em!r} não aparece na narração {self.narracao!r}')
        return self


class Roteiro(BaseModel):
    model_config = ConfigDict(extra='forbid')

    pergunta: str = Field(description='pergunta que o vídeo responde, em caixa alta')
    cenas: list[Cena] = Field(min_length=3, max_length=8)

    def para_json(self) -> dict:
        """Formato do roteiro.json lido por `montar` (fundo papel: não depende de mapas)."""
        return {
            'pergunta': self.pergunta,
            'cenas': [{'narracao': c.narracao, 'fundo': {'tipo': 'papel'}, 'fx': [f.model_dump() for f in c.fx]}
                      for c in self.cenas],
        }


def cliente_padrao() -> anthropic.Anthropic:
    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise ErroGeracao('defina a variável de ambiente ANTHROPIC_API_KEY para usar o comando gerar '
                          '(o resto do pipeline funciona sem ela)')
    return anthropic.Anthropic()


def gerar(tema: str, client: anthropic.Anthropic | None = None, modelo: str = MODELO) -> dict:
    """Roteiro validado (dict no formato do roteiro.json) para o tema dado."""
    client = client or cliente_padrao()
    pedido = f'Escreva o roteiro de um vídeo de 4 a 6 cenas sobre: {tema}'
    erro = None
    for _ in range(TENTATIVAS):
        conteudo = pedido if erro is None else f'{pedido}\n\nA tentativa anterior foi rejeitada: {erro}\nCorrija.'
        try:
            resp = client.messages.parse(
                model=modelo,
                max_tokens=16000,
                system=SISTEMA,
                messages=[{'role': 'user', 'content': conteudo}],
                output_format=Roteiro,
            )
        except ValidationError as e:  # JSON fora do schema ou regra do validador quebrada
            erro = str(e)
            continue
        except anthropic.AuthenticationError as e:
            raise ErroGeracao('a API recusou a chave em ANTHROPIC_API_KEY') from e
        except anthropic.APIError as e:  # o SDK já repete sozinho 429/5xx/rede antes de chegar aqui
            raise ErroGeracao(f'erro da API: {e}') from e

        if resp.stop_reason == 'refusal':
            raise ErroGeracao('o modelo recusou o pedido; tente outro tema')
        if resp.parsed_output is None:
            erro = 'resposta sem JSON'
            continue
        R = resp.parsed_output.para_json()
        erros = validar(R)
        if not erros:
            return R
        erro = '; '.join(erros)
    raise ErroGeracao(f'saída inválida após {TENTATIVAS} tentativas: {erro}')
