from edital_agent.avaliacao.avaliar import bootstrap_ic
from edital_agent.avaliacao.juiz import JuizHeuristico, gerar_afirmacoes
from edital_agent.avaliacao.ragas_metrics import (
    answer_correctness,
    comparar_campo,
    faithfulness,
)

CONTEXTOS = [
    "2. DO VALOR: O valor total estimado da contratação é de R$ 150.000,00.",
    "3.1. O encerramento do recebimento das propostas ocorrerá em 20/08/2026 às 09:00.",
    "PREGÃO ELETRÔNICO Nº 12/2026 - critério de julgamento: menor preço.",
]


def test_comparar_campo_normaliza_tipos():
    assert comparar_campo("valor_estimado", "R$ 150.000,00", 150000.0) is True
    assert comparar_campo("valor_estimado", 152000.0, 150000.0) is False  # >0,5%
    assert comparar_campo("prazo_entrega_proposta", "20/08/2026 09:00", "2026-08-20T09:00:00") is True
    assert comparar_campo("modalidade", "Pregão - Eletrônico", "pregao eletronico") is True
    assert comparar_campo("uf", "sp", "SP") is True
    assert comparar_campo("valor_estimado", None, None) is None  # abstenção correta
    assert comparar_campo("valor_estimado", None, 100.0) is False


def test_faithfulness_com_juiz_heuristico():
    valores = {
        "valor_estimado": 150000.0,             # sustentado
        "prazo_entrega_proposta": "2026-08-20", # sustentado
        "modalidade": "pregao eletronico",      # sustentado
        "objeto": "compra de helicópteros de combate",  # NÃO sustentado (alucinação)
    }
    resultado = faithfulness(valores, CONTEXTOS, JuizHeuristico())
    assert resultado.total == 4
    assert resultado.sustentadas == 3
    assert resultado.valor == 0.75
    assert resultado.taxa_alucinacao == 0.25
    assert resultado.por_campo["objeto"] is False


def test_faithfulness_sem_campos_preenchidos():
    resultado = faithfulness({"valor_estimado": None}, CONTEXTOS, JuizHeuristico())
    assert resultado.valor is None
    assert resultado.taxa_alucinacao is None


def test_answer_correctness_extracao_perfeita(fake_embedder):
    valores = {
        "prazo_entrega_proposta": "2026-08-20 09:00",
        "valor_estimado": 150000.0,
        "modalidade": "pregao eletronico",
    }
    gt = {
        "prazo_entrega_proposta": "2026-08-20T09:00:00",
        "valor_estimado": 150000.0,
        "modalidade": "Pregão - Eletrônico",
    }
    resultado = answer_correctness(valores, gt, fake_embedder)
    assert resultado.f1_factual == 1.0
    assert resultado.valor > 0.85


def test_answer_correctness_penaliza_erro_e_omissao(fake_embedder):
    valores = {"prazo_entrega_proposta": None, "valor_estimado": 999.0,
               "modalidade": "pregao eletronico"}
    gt = {"prazo_entrega_proposta": "2026-08-20", "valor_estimado": 150000.0,
          "modalidade": "pregao eletronico"}
    resultado = answer_correctness(valores, gt, fake_embedder)
    assert resultado.tp == 1 and resultado.fn == 2 and resultado.fp == 1
    assert resultado.f1_factual < 0.5


def test_gerar_afirmacoes_ignora_nulos():
    afirmacoes = gerar_afirmacoes({"valor_estimado": 10.0, "modalidade": None})
    assert len(afirmacoes) == 1
    assert afirmacoes[0].campo == "valor_estimado"
    assert "R$ 10.0" in afirmacoes[0].texto_nl


def test_bootstrap_ic_contem_media():
    valores = [0.8, 0.9, 0.85, 0.95, 0.7, 0.88]
    ic = bootstrap_ic(valores, n_amostras=500)
    assert ic is not None
    media = sum(valores) / len(valores)
    assert ic[0] <= media <= ic[1]
    assert bootstrap_ic([0.5]) is None  # amostra insuficiente
