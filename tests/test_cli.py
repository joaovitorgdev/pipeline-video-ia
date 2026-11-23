import os

import pytest

from pipeline.__main__ import main, parser

EXEMPLO = os.path.join(os.path.dirname(__file__), '..', 'exemplos', 'roteiro-exemplo.json')


def test_help_lista_comandos(capsys):
    with pytest.raises(SystemExit) as e:
        parser().parse_args(['--help'])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for cmd in ('validar', 'montar', 'midia', 'render'):
        assert cmd in out


def test_validar_exemplo(capsys):
    main(['validar', EXEMPLO])
    assert capsys.readouterr().out.startswith('ok: 4 cenas')
