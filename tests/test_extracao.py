"""Extração de documentos: DOCX em memória e resolução de formatos."""

import io
import zipfile

import pytest

from edital_agent.extracao.pdf import extrair_texto, resolver_documento

DOCUMENT_XML = """<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>PREGÃO ELETRÔNICO Nº 1/2026</w:t></w:r></w:p>
    <w:p><w:r><w:t>O valor total estimado é de </w:t></w:r>
         <w:r><w:t>R$ 100.000,00.</w:t></w:r></w:p>
  </w:body>
</w:document>"""


def _docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", DOCUMENT_XML)
    return buffer.getvalue()


def test_extrair_texto_docx(tmp_path):
    caminho = tmp_path / "edital.bin"
    caminho.write_bytes(_docx_bytes())
    resultado = extrair_texto(caminho)
    assert resultado.metodo == "docx"
    assert "PREGÃO ELETRÔNICO Nº 1/2026" in resultado.texto
    # runs de texto do mesmo parágrafo são concatenados
    assert "R$ 100.000,00" in resultado.texto


def test_resolver_documento_docx_direto(tmp_path):
    caminho = tmp_path / "edital.bin"
    caminho.write_bytes(_docx_bytes())
    assert resolver_documento(caminho) == caminho


def test_resolver_documento_zip_com_docx(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("anexos/Edital-01.docx", _docx_bytes())
        zf.writestr("anexos/planilha.xlsx", b"nao interessa")
    caminho = tmp_path / "pacote.bin"
    caminho.write_bytes(buffer.getvalue())
    resolvido = resolver_documento(caminho)
    assert resolvido.name == "Edital-01.docx"
    assert "PREGÃO" in extrair_texto(resolvido).texto


def test_resolver_documento_formato_invalido(tmp_path):
    caminho = tmp_path / "arquivo.bin"
    caminho.write_bytes(b"conteudo qualquer que nao e pdf nem zip")
    with pytest.raises(ValueError):
        resolver_documento(caminho)
