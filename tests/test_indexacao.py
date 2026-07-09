from edital_agent.indexacao.chunking import dividir_em_chunks
from edital_agent.indexacao.vetorial import IndiceVetorial

from .conftest import EDITAL_SINTETICO


def _indice(fake_embedder):
    chunks = dividir_em_chunks(EDITAL_SINTETICO, id_edital="teste", tamanho=300, overlap=60)
    return IndiceVetorial(chunks, fake_embedder)


def test_busca_recupera_chunk_relevante(fake_embedder):
    indice = _indice(fake_embedder)
    resultados = indice.buscar("valor total estimado da contratação", top_k=3)
    assert len(resultados) == 3
    assert any("150.000,00" in chunk.texto for chunk, _ in resultados)


def test_obter_chunk_com_vizinhos(fake_embedder):
    indice = _indice(fake_embedder)
    alvo = indice.chunks[1]
    vizinhos = indice.obter_chunk(alvo.id, janela=1)
    assert len(vizinhos) == 3
    assert vizinhos[1].id == alvo.id
    assert indice.obter_chunk("inexistente#c9999") == []


def test_persistencia_roundtrip(tmp_path, fake_embedder):
    indice = _indice(fake_embedder)
    indice.salvar(tmp_path / "idx")
    recarregado = IndiceVetorial.carregar(tmp_path / "idx", fake_embedder)
    assert len(recarregado.chunks) == len(indice.chunks)
    originais = [c.id for c, _ in indice.buscar("propostas encerramento", top_k=2)]
    recuperados = [c.id for c, _ in recarregado.buscar("propostas encerramento", top_k=2)]
    assert originais == recuperados
