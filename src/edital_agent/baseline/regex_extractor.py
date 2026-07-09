"""Baseline: extração por expressões regulares sobre o texto integral do edital.

É o comparativo exigido pela proposta ("baseline: extração por regex sobre o
texto do edital"). Representa a abordagem clássica baseada em regras — rápida e
gratuita, porém frágil diante da variabilidade linguística dos editais.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..normalizacao import extrair_data, moeda_para_float, normalizar_texto

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
}


@dataclass
class ExtracaoBaseline:
    prazo_entrega_proposta: str | None = None
    valor_estimado: float | None = None
    modalidade: str | None = None
    objeto: str | None = None
    orgao_responsavel: str | None = None
    uf: str | None = None
    criterio_julgamento: str | None = None
    prazo_execucao: str | None = None

    def como_dict(self) -> dict:
        return {
            "prazo_entrega_proposta": self.prazo_entrega_proposta,
            "valor_estimado": self.valor_estimado,
            "modalidade": self.modalidade,
            "objeto": self.objeto,
            "orgao_responsavel": self.orgao_responsavel,
            "uf": self.uf,
            "criterio_julgamento": self.criterio_julgamento,
            "prazo_execucao": self.prazo_execucao,
        }


_JANELA = 260  # caracteres inspecionados após a âncora


def _janela_apos(texto: str, padrao: str) -> str | None:
    m = re.search(padrao, texto, re.IGNORECASE)
    if not m:
        return None
    return texto[m.start(): m.end() + _JANELA]


def _prazo_proposta(texto: str) -> str | None:
    ancoras = [
        r"encerramento\s+(?:do\s+recebimento\s+)?d[ae]s?\s+propostas?",
        r"(?:limite|final)\s+para\s+(?:entrega|recebimento|acolhimento|apresenta\w+)\s+d[ae]s?\s+propostas?",
        r"recebimento\s+d[ae]s?\s+propostas?\s*(?:até|ate)?",
        r"abertura\s+da\s+sess[ãa]o\s+p[úu]blica",
        r"(?:fim|t[ée]rmino)\s+do\s+acolhimento",
        r"data\s+da\s+sess[ãa]o",
        r"abertura\s+d[ae]s?\s+propostas?",
    ]
    for ancora in ancoras:
        janela = _janela_apos(texto, ancora)
        if janela:
            data = extrair_data(janela)
            if data:
                return data
    return None


def _valor_estimado(texto: str) -> float | None:
    ancoras = [
        r"valor\s+(?:total\s+)?(?:global\s+)?estimad[oa]",
        r"valor\s+m[áa]ximo\s+(?:aceit[áa]vel|admitido)",
        r"valor\s+global\s+(?:m[áa]ximo\s+)?",
        r"pre[çc]o\s+(?:total\s+)?estimado",
        r"or[çc]amento\s+estimado",
        r"custo\s+estimado",
    ]
    for ancora in ancoras:
        janela = _janela_apos(texto, ancora)
        if janela:
            m = re.search(r"R\$\s*[\d\.\s]{1,15},\d{2}", janela)
            if m:
                return moeda_para_float(m.group(0))
    return None


def _modalidade(texto: str) -> str | None:
    t = normalizar_texto(texto[:20000])  # modalidade aparece no cabeçalho
    padroes = [
        ("pregao eletronico", r"pregao[\s,]+(?:na\s+forma\s+)?eletronic[oa]"),
        ("pregao presencial", r"pregao[\s,]+(?:na\s+forma\s+)?presencial"),
        ("concorrencia", r"concorrencia"),
        ("dispensa", r"dispensa\s+(?:de\s+licitacao|eletronica)"),
        ("inexigibilidade", r"inexigibilidade"),
        ("leilao", r"leilao"),
        ("credenciamento", r"credenciamento"),
        ("pregao eletronico", r"\bpregao\b"),
    ]
    for categoria, padrao in padroes:
        if re.search(padrao, t):
            return categoria
    return None


def _criterio(texto: str) -> str | None:
    t = normalizar_texto(texto)
    padroes = [
        ("menor preco", r"menor\s+preco"),
        ("maior desconto", r"maior\s+(?:percentual\s+de\s+)?desconto"),
        ("tecnica e preco", r"tecnica\s+e\s+preco"),
        ("melhor tecnica", r"melhor\s+tecnica"),
        ("maior lance", r"maior\s+lance"),
        ("maior retorno economico", r"maior\s+retorno\s+economico"),
    ]
    for categoria, padrao in padroes:
        if re.search(padrao, t):
            return categoria
    return None


def _objeto(texto: str) -> str | None:
    for ancora in (
        r"(?:do\s+)?objeto\s*[:\-–]",
        r"objeto\s+da\s+(?:presente\s+)?licitac[ãa]o\s+[ée]",
        r"tem\s+(?:por|como)\s+objeto",
        r"constitui\s+objeto",
    ):
        m = re.search(ancora, texto, re.IGNORECASE)
        if m:
            trecho = texto[m.end(): m.end() + 500]
            trecho = re.sub(r"\s+", " ", trecho).strip(" :-–")
            corte = re.search(r"[.;]\s", trecho)
            if corte and corte.start() > 30:
                trecho = trecho[: corte.start() + 1]
            return trecho[:400] or None
    return None


def _orgao(texto: str) -> str | None:
    cabecalho = texto[:3000]
    padroes = [
        r"(?:MUNIC[ÍI]PIO|PREFEITURA(?:\s+MUNICIPAL)?)\s+DE\s+[A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s\-']{2,60}",
        r"(?:GOVERNO\s+DO\s+ESTADO|ESTADO)\s+D[EOA]S?\s+[A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s]{2,50}",
        r"(?:MINIST[ÉE]RIO|SECRETARIA|TRIBUNAL|UNIVERSIDADE|INSTITUTO|FUNDA[ÇC][ÃA]O|AUTARQUIA|C[ÂA]MARA(?:\s+MUNICIPAL)?|CONSELHO)\s+[A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s\-]{2,70}",
    ]
    for padrao in padroes:
        m = re.search(padrao, cabecalho)
        if m:
            nome = re.sub(r"\s+", " ", m.group(0)).strip()
            return re.split(r"\s{2,}|\n", nome)[0][:120]
    return None


def _uf(texto: str) -> str | None:
    cabecalho = texto[:5000]
    m = re.search(r"(?:estado\s+d[eoa]s?\s+)([A-Za-zÀ-ú\s]{4,25})[\s,./-]", cabecalho, re.IGNORECASE)
    estados = {
        "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA",
        "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES", "goias": "GO",
        "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
        "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
        "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
        "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
        "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
        "tocantins": "TO",
    }
    if m:
        nome = normalizar_texto(m.group(1))
        for chave in sorted(estados, key=len, reverse=True):
            if nome.startswith(chave):
                return estados[chave]
    m = re.search(r"[-–/]\s*([A-Z]{2})\b", cabecalho)
    if m and m.group(1) in UFS:
        return m.group(1)
    m = re.search(r"\b(?:CEP[\s:]*[\d\.\-]+\s*[,\-–]?\s*)?([A-Z]{2})\s*[,.]?\s*CEP", cabecalho)
    if m and m.group(1) in UFS:
        return m.group(1)
    return None


def _prazo_execucao(texto: str) -> str | None:
    for ancora in (
        r"prazo\s+(?:de\s+|da\s+|para\s+(?:a\s+)?)?(?:execu[çc][ãa]o|entrega|vig[êe]ncia)[^.]{0,80}?",
    ):
        m = re.search(
            ancora + r"(\d{1,4})\s*\(?[a-zç\s]*\)?\s*(dias?|meses|m[êe]s|anos?)",
            texto,
            re.IGNORECASE,
        )
        if m:
            unidade = normalizar_texto(m.group(2))
            unidade = {"mes": "meses", "meses": "meses", "dia": "dias", "dias": "dias",
                       "ano": "anos", "anos": "anos"}.get(unidade, unidade)
            return f"{m.group(1)} {unidade}"
    return None


def extrair_por_regex(texto: str) -> ExtracaoBaseline:
    """Extrai os 8 campos-alvo do texto integral usando apenas regras."""
    return ExtracaoBaseline(
        prazo_entrega_proposta=_prazo_proposta(texto),
        valor_estimado=_valor_estimado(texto),
        modalidade=_modalidade(texto),
        objeto=_objeto(texto),
        orgao_responsavel=_orgao(texto),
        uf=_uf(texto),
        criterio_julgamento=_criterio(texto),
        prazo_execucao=_prazo_execucao(texto),
    )
