from edital_agent.indexacao.chunking import dividir_em_chunks

from .conftest import EDITAL_SINTETICO


def test_chunks_cobrem_texto_e_tem_secao():
    chunks = dividir_em_chunks(EDITAL_SINTETICO, id_edital="teste", tamanho=300, overlap=60)
    assert len(chunks) >= 4
    assert all(c.id.startswith("teste#c") for c in chunks)
    secoes = {c.secao for c in chunks}
    assert any("OBJETO" in s for s in secoes)
    assert any("VALOR" in s or "PROPOSTAS" in s for s in secoes)
    # conteúdo crítico não pode se perder no chunking
    texto_completo = " ".join(c.texto for c in chunks)
    assert "150.000,00" in texto_completo
    assert "20/08/2026" in texto_completo


def test_overlap_em_blocos_longos():
    texto = "SEÇÃO I - LONGA\n" + ("palavra " * 800)
    chunks = dividir_em_chunks(texto, tamanho=500, overlap=100)
    assert len(chunks) > 3
    # overlap: início de um chunk repete o fim do anterior
    assert chunks[1].texto[:40].strip() in chunks[0].texto + chunks[1].texto


def test_texto_vazio():
    assert dividir_em_chunks("") == []
