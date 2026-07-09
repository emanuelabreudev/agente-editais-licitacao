"""Teste end-to-end do loop agêntico usando o MockLLM (sem rede)."""

from edital_agent.agente.agente import AgenteEdital
from edital_agent.indexacao.chunking import dividir_em_chunks
from edital_agent.indexacao.vetorial import IndiceVetorial
from edital_agent.llm.cliente import MockLLM

from .conftest import EDITAL_SINTETICO


def test_agente_mock_extrai_e_registra_contextos(fake_embedder):
    chunks = dividir_em_chunks(EDITAL_SINTETICO, id_edital="teste", tamanho=300, overlap=60)
    indice = IndiceVetorial(chunks, fake_embedder)
    agente = AgenteEdital(MockLLM(), indice, max_iteracoes=5)

    resultado = agente.executar("teste")

    # o loop deve terminar com uma extração registrada e contextos rastreados
    assert resultado.iteracoes >= 2
    assert len(resultado.contextos) > 0
    valores = resultado.extracao.valores()
    assert valores["modalidade"] == "pregao eletronico"
    assert valores["valor_estimado"] == 150000.0
    assert valores["prazo_entrega_proposta"] == "2026-08-20 09:00"

    # uso contabilizado (chamadas > 0) e custo zero no mock
    assert resultado.uso["chamadas"] >= 2
    assert resultado.uso["custo_usd"] == 0.0


def test_pos_processamento_valida_citacoes(fake_embedder):
    chunks = dividir_em_chunks(EDITAL_SINTETICO, id_edital="teste", tamanho=300, overlap=60)
    indice = IndiceVetorial(chunks, fake_embedder)
    agente = AgenteEdital(MockLLM(), indice, max_iteracoes=5)
    agente._contextos = {
        "teste#c0001": {"chunk_id": "teste#c0001", "secao": "s", "texto": "o valor é R$ 10,00"}
    }
    extracao = agente._pos_processar(
        {
            "valor_estimado": {
                "valor": 10.0,
                "chunks_evidencia": ["teste#c0001"],
                "citacao": "o valor é R$ 10,00",
                "confianca": 0.9,
            },
            "modalidade": {
                "valor": "pregao eletronico",
                "chunks_evidencia": ["chunk_que_nao_existe"],
                "citacao": None,
                "confianca": 0.9,
            },
        }
    )
    assert extracao.valor_estimado.evidencia_valida is True
    assert extracao.modalidade.evidencia_valida is False  # citou chunk não recuperado
    assert extracao.objeto.evidencia_valida is None  # campo nulo
