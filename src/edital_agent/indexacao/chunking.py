"""Chunking semântico de editais: divide o texto respeitando seções e cláusulas.

Editais seguem estrutura numerada ("1. DO OBJETO", "12.3 ...", "CLÁUSULA SEGUNDA").
O chunker detecta cabeçalhos de seção, mantém o título da seção como metadado de
cada chunk (rastreabilidade) e aplica janela com overlap para não cortar
informações na fronteira (tratamento previsto na seção 2.5 da proposta).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Cabeçalhos típicos: "1. DO OBJETO", "12.3. ...", "CLÁUSULA SEGUNDA - ...",
# "ANEXO I", "SEÇÃO II", ou linhas inteiras em caixa alta.
_PADRAO_SECAO = re.compile(
    r"^\s*(?:"
    r"(?:\d{1,2}(?:\.\d{1,2}){0,2})\s*[\.\)\-–—]\s+(?=[A-ZÀ-Ú])"
    r"|CL[ÁA]USULA\s+"
    r"|ANEXO\s+[IVXLC\d]"
    r"|SE[ÇC][ÃA]O\s+"
    r"|CAP[ÍI]TULO\s+"
    r")",
    re.MULTILINE,
)
_LINHA_CAIXA_ALTA = re.compile(r"^[A-ZÀ-Ú0-9][A-ZÀ-Ú0-9\s\-–—:,\.\(\)/]{10,80}$")


@dataclass
class Chunk:
    id: str
    texto: str
    secao: str
    posicao: int  # offset (caracteres) no documento
    id_edital: str = ""
    metadados: dict = field(default_factory=dict)


def _e_cabecalho(linha: str) -> bool:
    linha = linha.strip()
    if not linha or len(linha) > 120:
        return False
    if _PADRAO_SECAO.match(linha):
        return True
    return bool(_LINHA_CAIXA_ALTA.match(linha)) and not linha.startswith("[página")


def _segmentar_por_secao(texto: str) -> list[tuple[str, str, int]]:
    """Devolve [(titulo_secao, corpo, offset_inicial)]."""
    linhas = texto.split("\n")
    segmentos: list[tuple[str, list[str], int]] = []
    titulo_atual = "PREÂMBULO"
    corpo_atual: list[str] = []
    offset = 0
    offset_secao = 0
    for linha in linhas:
        if _e_cabecalho(linha):
            if corpo_atual:
                segmentos.append((titulo_atual, corpo_atual, offset_secao))
            titulo_atual = linha.strip()[:110]
            corpo_atual = [linha]
            offset_secao = offset
        else:
            corpo_atual.append(linha)
        offset += len(linha) + 1
    if corpo_atual:
        segmentos.append((titulo_atual, corpo_atual, offset_secao))
    return [(t, "\n".join(c).strip(), o) for t, c, o in segmentos if "\n".join(c).strip()]


def _fatiar(texto: str, tamanho: int, overlap: int) -> list[tuple[str, int]]:
    """Fatia um bloco em janelas de ~tamanho com overlap, quebrando em fim de frase."""
    if len(texto) <= tamanho:
        return [(texto, 0)]
    fatias: list[tuple[str, int]] = []
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + tamanho, len(texto))
        if fim < len(texto):
            # tenta quebrar no último fim de frase/linha dentro da janela
            corte = max(
                texto.rfind(". ", inicio + tamanho // 2, fim),
                texto.rfind("\n", inicio + tamanho // 2, fim),
            )
            if corte > inicio:
                fim = corte + 1
        fatias.append((texto[inicio:fim].strip(), inicio))
        if fim >= len(texto):
            break
        inicio = max(fim - overlap, inicio + 1)
    return [f for f in fatias if f[0]]


def dividir_em_chunks(
    texto: str,
    id_edital: str = "",
    tamanho: int = 1400,
    overlap: int = 250,
) -> list[Chunk]:
    """Divide o texto do edital em chunks com metadado de seção e overlap."""
    chunks: list[Chunk] = []
    n = 0
    for titulo, corpo, offset_secao in _segmentar_por_secao(texto):
        for fatia, offset_local in _fatiar(corpo, tamanho, overlap):
            chunks.append(
                Chunk(
                    id=f"{id_edital}#c{n:04d}" if id_edital else f"c{n:04d}",
                    texto=fatia,
                    secao=titulo,
                    posicao=offset_secao + offset_local,
                    id_edital=id_edital,
                )
            )
            n += 1
    return chunks
