from edital_agent.normalizacao import (
    extrair_data,
    moeda_para_float,
    normalizar_criterio,
    normalizar_data,
    normalizar_modalidade,
)


def test_extrair_data_formatos():
    assert extrair_data("20/08/2026 às 09:00") == "2026-08-20 09:00"
    assert extrair_data("2026-07-06T08:31:00") == "2026-07-06 08:31"
    assert extrair_data("dia 5 de julho de 2026") == "2026-07-05"
    assert extrair_data("sem data aqui") is None


def test_normalizar_data_compara_por_dia():
    assert normalizar_data("06/07/2026 08:31") == normalizar_data("2026-07-06T08:31:00")
    assert normalizar_data("06/07/2026") == "2026-07-06"


def test_moeda_para_float():
    assert moeda_para_float("R$ 554.771,65") == 554771.65
    assert moeda_para_float("R$ 1.000,00") == 1000.0
    assert moeda_para_float(554771.65) == 554771.65
    assert moeda_para_float("554771.65") == 554771.65
    assert moeda_para_float("texto sem valor") is None


def test_normalizar_modalidade():
    assert normalizar_modalidade("Pregão - Eletrônico") == "pregao eletronico"
    assert normalizar_modalidade("pregao eletronico") == "pregao eletronico"
    assert normalizar_modalidade("Concorrência - Eletrônica") == "concorrencia"
    assert normalizar_modalidade("Dispensa") == "dispensa"
    assert normalizar_modalidade(None) is None


def test_normalizar_criterio():
    assert normalizar_criterio("Menor preço") == "menor preco"
    assert normalizar_criterio("MENOR PREÇO") == "menor preco"
    assert normalizar_criterio("Técnica e Preço") == "tecnica e preco"
