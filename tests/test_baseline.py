from edital_agent.baseline.regex_extractor import extrair_por_regex

from .conftest import EDITAL_SINTETICO


def test_baseline_extrai_campos_criticos():
    extracao = extrair_por_regex(EDITAL_SINTETICO)
    assert extracao.prazo_entrega_proposta == "2026-08-20 09:00"
    assert extracao.valor_estimado == 150000.0
    assert extracao.modalidade == "pregao eletronico"


def test_baseline_extrai_campos_descritivos():
    extracao = extrair_por_regex(EDITAL_SINTETICO)
    assert extracao.criterio_julgamento == "menor preco"
    assert "material escolar" in (extracao.objeto or "")
    assert "EXEMPLO" in (extracao.orgao_responsavel or "")
    assert extracao.uf == "SP"
    assert extracao.prazo_execucao == "30 dias"


def test_baseline_texto_sem_informacao():
    extracao = extrair_por_regex("documento sem nenhuma informação de licitação")
    assert extracao.valor_estimado is None
    assert extracao.prazo_entrega_proposta is None
    assert extracao.modalidade is None
