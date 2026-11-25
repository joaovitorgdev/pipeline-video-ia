"""Testes do gerador com a API simulada (unittest.mock): nenhum teste acessa a rede."""
from unittest import mock

import anthropic
import httpx2
import pytest
from pydantic import ValidationError

from pipeline import gerar
from pipeline.gerar import ErroGeracao, Roteiro

OK = {
    'pergunta': 'POR QUE O RIO SÃO FRANCISCO É O VELHO CHICO?',
    'cenas': [
        {'narracao': 'O rio São Francisco nasce em Minas Gerais.', 'fx': [{'em': 'Minas Gerais', 'tipo': 'chip', 'texto': 'NASCENTE'}]},
        {'narracao': 'Ele atravessa cinco estados até o mar.', 'fx': []},
        {'narracao': 'Por isso é chamado de rio da integração nacional.', 'fx': [{'em': 'integração', 'tipo': 'cartao', 'texto': 'Rio da integração'}]},
    ],
}


def resposta(dados=OK, stop_reason='end_turn'):
    return mock.Mock(parsed_output=Roteiro.model_validate(dados), stop_reason=stop_reason)


def erro_validacao(json_texto):
    try:
        Roteiro.model_validate_json(json_texto)
    except ValidationError as e:
        return e
    raise AssertionError('era para falhar')


def cliente(*efeitos):
    c = mock.Mock()
    c.messages.parse.side_effect = list(efeitos)
    return c


def test_sucesso_devolve_roteiro_no_formato_do_pipeline():
    c = cliente(resposta())
    R = gerar.gerar('rio São Francisco', client=c)
    assert R['cenas'][0]['fundo'] == {'tipo': 'papel'}
    assert R['cenas'][0]['fx'][0] == {'em': 'Minas Gerais', 'tipo': 'chip', 'texto': 'NASCENTE'}
    kwargs = c.messages.parse.call_args.kwargs
    assert kwargs['output_format'] is Roteiro
    assert 'rio São Francisco' in kwargs['messages'][0]['content']


def test_json_invalido_tenta_de_novo_com_o_erro_no_pedido():
    c = cliente(erro_validacao('{"pergunta": "X", "cenas": ['), resposta())
    R = gerar.gerar('tema', client=c)
    assert len(R['cenas']) == 3
    assert c.messages.parse.call_count == 2
    assert 'rejeitada' in c.messages.parse.call_args.kwargs['messages'][0]['content']


def test_json_invalido_em_todas_as_tentativas_vira_erro_claro():
    c = cliente(*[erro_validacao('não é json')] * gerar.TENTATIVAS)
    with pytest.raises(ErroGeracao, match='após 3 tentativas'):
        gerar.gerar('tema', client=c)
    assert c.messages.parse.call_count == gerar.TENTATIVAS


def test_gatilho_fora_da_narracao_e_rejeitado():
    ruim = {**OK, 'cenas': [{'narracao': 'Texto qualquer.', 'fx': [{'em': 'Brasília', 'tipo': 'chip', 'texto': 'X'}]}] * 3}
    with pytest.raises(ValidationError, match='não aparece na narração'):
        Roteiro.model_validate(ruim)


def test_erro_da_api_vira_erro_claro_sem_repetir():
    falha = anthropic.APIConnectionError(request=httpx2.Request('POST', 'https://api.anthropic.com/v1/messages'))
    c = cliente(falha)
    with pytest.raises(ErroGeracao, match='erro da API'):
        gerar.gerar('tema', client=c)
    assert c.messages.parse.call_count == 1


def test_recusa_do_modelo_vira_erro_claro():
    with pytest.raises(ErroGeracao, match='recusou'):
        gerar.gerar('tema', client=cliente(resposta(stop_reason='refusal')))


def test_sem_chave_avisa_sem_chamar_a_api(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    with mock.patch.object(anthropic, 'Anthropic') as construtor:
        with pytest.raises(ErroGeracao, match='ANTHROPIC_API_KEY'):
            gerar.gerar('tema')
    construtor.assert_not_called()


def test_cli_sem_chave_sai_com_mensagem_e_sem_arquivo(monkeypatch, tmp_path):
    from pipeline.__main__ import main

    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    with pytest.raises(SystemExit, match='ANTHROPIC_API_KEY'):
        main(['gerar', 'tema', str(tmp_path / 'video')])
    assert not (tmp_path / 'video').exists()


def test_schema_aceito_pelo_sdk():
    schema = anthropic.transform_schema(Roteiro.model_json_schema())
    assert schema['additionalProperties'] is False
