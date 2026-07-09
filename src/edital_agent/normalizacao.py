"""Normalização de valores extraídos (datas, moeda, categorias) para comparação.

Usada pelo baseline, pelo agente (pós-processamento) e pela avaliação, garantindo
que "06/07/2026 08:31", "2026-07-06T08:31:00" e "6 de julho de 2026" comparem igual.
"""

from __future__ import annotations

import re
import unicodedata

MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

_RE_DATA_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?")
_RE_DATA_BR = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\D{0,10}?(\d{1,2})[:h](\d{2}))?")
_RE_DATA_EXTENSO = re.compile(
    r"(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})", re.IGNORECASE
)
_RE_MOEDA = re.compile(r"R\$\s*([\d\.\s]{1,15},\d{2})")


def remover_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def normalizar_texto(texto: str | None) -> str:
    if not texto:
        return ""
    texto = remover_acentos(texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def extrair_data(texto: str | None) -> str | None:
    """Extrai a primeira data do texto e devolve como 'AAAA-MM-DD[ HH:MM]'."""
    if not texto:
        return None
    m = _RE_DATA_ISO.search(texto)
    if m:
        ano, mes, dia, hora, minuto = m.groups()
        base = f"{ano}-{mes}-{dia}"
        return f"{base} {hora}:{minuto}" if hora else base
    m = _RE_DATA_BR.search(texto)
    if m:
        dia, mes, ano, hora, minuto = m.groups()
        base = f"{ano}-{int(mes):02d}-{int(dia):02d}"
        return f"{base} {int(hora):02d}:{minuto}" if hora else base
    m = _RE_DATA_EXTENSO.search(texto)
    if m:
        dia, nome_mes, ano = m.groups()
        mes = MESES.get(remover_acentos(nome_mes.lower()))
        if mes:
            return f"{ano}-{mes:02d}-{int(dia):02d}"
    return None


def normalizar_data(valor: str | None, apenas_dia: bool = True) -> str | None:
    """Normaliza uma data para comparação; por padrão compara só AAAA-MM-DD."""
    data = extrair_data(valor)
    if data is None:
        return None
    return data[:10] if apenas_dia else data


def moeda_para_float(texto: str | None) -> float | None:
    """Converte 'R$ 554.771,65' (ou '554771.65') para float."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    m = _RE_MOEDA.search(texto)
    bruto = m.group(1) if m else texto
    bruto = bruto.strip().replace(" ", "")
    if re.fullmatch(r"\d+(\.\d+)?", bruto):
        return float(bruto)
    bruto = bruto.replace(".", "").replace(",", ".")
    try:
        return float(bruto)
    except ValueError:
        return None


CATEGORIAS_MODALIDADE = {
    "pregao eletronico": ["pregao eletronico", "pregao - eletronico", "pregao, na forma eletronica"],
    "pregao presencial": ["pregao presencial", "pregao - presencial"],
    "concorrencia": ["concorrencia"],
    "dispensa": ["dispensa"],
    "inexigibilidade": ["inexigibilidade"],
    "leilao": ["leilao"],
    "concurso": ["concurso"],
    "credenciamento": ["credenciamento"],
}

CATEGORIAS_CRITERIO = {
    "menor preco": ["menor preco"],
    "maior desconto": ["maior desconto"],
    "tecnica e preco": ["tecnica e preco", "melhor combinacao de tecnica e preco"],
    "melhor tecnica": ["melhor tecnica", "melhor tecnica ou conteudo artistico"],
    "maior lance": ["maior lance"],
    "maior retorno economico": ["maior retorno economico"],
    "nao aplicavel": ["nao aplicavel", "nao se aplica"],
}


def _categorizar(valor: str | None, categorias: dict[str, list[str]]) -> str | None:
    v = normalizar_texto(valor)
    if not v:
        return None
    for categoria, sinonimos in categorias.items():
        if any(s in v for s in sinonimos):
            return categoria
    return v


def normalizar_modalidade(valor: str | None) -> str | None:
    return _categorizar(valor, CATEGORIAS_MODALIDADE)


def normalizar_criterio(valor: str | None) -> str | None:
    return _categorizar(valor, CATEGORIAS_CRITERIO)
