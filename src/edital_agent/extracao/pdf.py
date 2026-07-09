"""Extração de texto de documentos de edital (PDF nativo, ZIP com PDFs, OCR fallback).

Fluxo (objetivo específico 3):
  1. Se o arquivo baixado for ZIP, extrai e escolhe o PDF do edital.
  2. Extrai texto página a página com pypdf.
  3. Páginas com pouco texto (< min_chars_por_pagina) indicam PDF escaneado;
     se Tesseract + poppler estiverem instalados, aplica OCR nessas páginas.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger(__name__)

_OCR_DISPONIVEL: bool | None = None


def ocr_disponivel() -> bool:
    """Verifica se pytesseract/pdf2image e os binários do sistema existem."""
    global _OCR_DISPONIVEL
    if _OCR_DISPONIVEL is None:
        try:
            import pdf2image  # noqa: F401
            import pytesseract

            pytesseract.get_tesseract_version()
            _OCR_DISPONIVEL = True
        except Exception:
            _OCR_DISPONIVEL = False
    return _OCR_DISPONIVEL


@dataclass
class ResultadoExtracao:
    texto: str
    n_paginas: int
    n_paginas_ocr: int
    metodo: str  # "pypdf" | "pypdf+ocr" | "ocr_indisponivel"
    caminho_pdf: str
    avisos: list[str] = field(default_factory=list)

    @property
    def caracteres(self) -> int:
        return len(self.texto)


def _e_pdf(dados: bytes) -> bool:
    return dados[:5] == b"%PDF-"


def _e_zip(dados: bytes) -> bool:
    return dados[:4] == b"PK\x03\x04"


def _texto_de_docx(dados: bytes) -> str:
    """Extrai texto de um DOCX (parágrafos de word/document.xml)."""
    import xml.etree.ElementTree as ET

    ns_w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(dados)) as zf:
        raiz = ET.fromstring(zf.read("word/document.xml"))
    paragrafos = []
    for p in raiz.iter(f"{ns_w}p"):
        texto = "".join(t.text or "" for t in p.iter(f"{ns_w}t"))
        if texto.strip():
            paragrafos.append(texto)
    return "\n".join(paragrafos)


def _e_docx(dados: bytes) -> bool:
    if not _e_zip(dados):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as zf:
            return "word/document.xml" in zf.namelist()
    except zipfile.BadZipFile:
        return False


def resolver_documento(caminho: Path, dir_extracao: Path | None = None) -> Path:
    """Devolve o caminho de um PDF ou DOCX utilizável.

    Alguns órgãos publicam o edital como ZIP contendo edital + anexos; nesse
    caso extrai os PDFs/DOCX e escolhe o que aparenta ser o edital principal
    (nome contendo 'edital'; senão, o maior arquivo).
    """
    dados = caminho.read_bytes()
    if _e_pdf(dados) or _e_docx(dados):
        return caminho
    if not _e_zip(dados):
        raise ValueError(f"Formato não reconhecido (nem PDF, DOCX ou ZIP): {caminho}")

    dir_extracao = dir_extracao or caminho.parent / (caminho.stem + "_zip")
    dir_extracao.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(dados)) as zf:
        candidatos: list[tuple[str, int]] = [
            (n, zf.getinfo(n).file_size)
            for n in zf.namelist()
            if n.lower().endswith((".pdf", ".docx")) and not n.endswith("/")
        ]
        if not candidatos:
            raise ValueError(f"ZIP sem PDFs/DOCX: {caminho}")
        com_edital = [p for p in candidatos if "edital" in p[0].lower()]
        escolhido = max(com_edital or candidatos, key=lambda p: p[1])[0]
        destino = dir_extracao / Path(escolhido).name
        destino.write_bytes(zf.read(escolhido))
        return destino


def _normalizar_texto(texto: str) -> str:
    texto = texto.replace("\x00", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _ocr_paginas(caminho: Path, paginas: list[int], dpi: int) -> dict[int, str]:
    """OCR (Tesseract, por-BR quando disponível) apenas das páginas indicadas."""
    import pdf2image
    import pytesseract

    idiomas = pytesseract.get_languages(config="")
    lang = "por" if "por" in idiomas else "eng"
    resultado: dict[int, str] = {}
    for num in paginas:
        imagens = pdf2image.convert_from_path(
            str(caminho), dpi=dpi, first_page=num + 1, last_page=num + 1
        )
        if imagens:
            resultado[num] = pytesseract.image_to_string(imagens[0], lang=lang)
    return resultado


def extrair_texto(
    caminho: Path,
    min_chars_por_pagina: int = 200,
    ocr_dpi: int = 200,
    max_paginas: int | None = None,
) -> ResultadoExtracao:
    """Extrai o texto de um PDF ou DOCX, com fallback de OCR p/ PDF escaneado."""
    dados = caminho.read_bytes()
    if _e_docx(dados):
        texto = _normalizar_texto(_texto_de_docx(dados))
        return ResultadoExtracao(
            texto=texto,
            n_paginas=0,
            n_paginas_ocr=0,
            metodo="docx",
            caminho_pdf=str(caminho),
            avisos=[],
        )
    avisos: list[str] = []
    reader = PdfReader(str(caminho))
    n_paginas_total = len(reader.pages)
    n_paginas = n_paginas_total
    if max_paginas is not None and n_paginas_total > max_paginas:
        n_paginas = max_paginas
        avisos.append(
            f"PDF com {n_paginas_total} páginas; processadas apenas as {max_paginas} primeiras"
        )

    textos: list[str] = []
    paginas_pobres: list[int] = []
    for i in range(n_paginas):
        try:
            t = reader.pages[i].extract_text() or ""
        except Exception as exc:  # páginas corrompidas não devem abortar o documento
            logger.warning("Falha ao extrair página %d de %s: %s", i, caminho.name, exc)
            t = ""
        textos.append(t)
        if len(t.strip()) < min_chars_por_pagina:
            paginas_pobres.append(i)

    n_ocr = 0
    metodo = "pypdf"
    if paginas_pobres:
        if ocr_disponivel():
            try:
                ocr = _ocr_paginas(caminho, paginas_pobres, dpi=ocr_dpi)
                for num, texto_ocr in ocr.items():
                    if len(texto_ocr.strip()) > len(textos[num].strip()):
                        textos[num] = texto_ocr
                        n_ocr += 1
                if n_ocr:
                    metodo = "pypdf+ocr"
            except Exception as exc:
                avisos.append(f"OCR falhou: {exc}")
        else:
            avisos.append(
                f"{len(paginas_pobres)} página(s) com pouco texto e OCR indisponível "
                "(instale tesseract-ocr + poppler-utils)"
            )
            if len(paginas_pobres) == n_paginas:
                metodo = "ocr_indisponivel"

    corpo = "\n\n".join(
        f"[página {i + 1}]\n{_normalizar_texto(t)}" for i, t in enumerate(textos) if t.strip()
    )
    return ResultadoExtracao(
        texto=corpo,
        n_paginas=n_paginas_total,
        n_paginas_ocr=n_ocr,
        metodo=metodo,
        caminho_pdf=str(caminho),
        avisos=avisos,
    )
