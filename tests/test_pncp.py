"""Parsing de payloads do PNCP (fixture gravada de resposta real, sem rede)."""

from edital_agent.coleta.pncp import Contratacao, escolher_arquivo_edital

PAYLOAD_REAL = {
    "orgaoEntidade": {"cnpj": "88201298000149", "razaoSocial": "MUNICIPIO DE LAVRAS DO SUL"},
    "anoCompra": 2026,
    "sequencialCompra": 679,
    "unidadeOrgao": {"ufSigla": "RS", "municipioNome": "Lavras do Sul"},
    "dataAberturaProposta": "2026-06-18T17:00:00",
    "dataEncerramentoProposta": "2026-07-06T08:31:00",
    "objetoCompra": "Sistema de Registro de Preços para aquisições de 5 veículos ZERO KM",
    "numeroControlePNCP": "88201298000149-1-000679/2026",
    "modalidadeId": 6,
    "valorTotalEstimado": 554771.65,
    "modalidadeNome": "Pregão - Eletrônico",
    "situacaoCompraNome": "Divulgada no PNCP",
}


def test_contratacao_de_json():
    c = Contratacao.de_json(PAYLOAD_REAL)
    assert c.cnpj == "88201298000149"
    assert c.uf == "RS"
    assert c.valor_total_estimado == 554771.65
    assert c.data_encerramento_proposta == "2026-07-06T08:31:00"
    assert c.id_edital == "88201298000149-1-000679-2026"  # '/' vira '-'


def test_escolher_arquivo_prioriza_edital():
    arquivos = [
        {"tipoDocumentoNome": "Estudo Técnico Preliminar", "statusAtivo": True},
        {"tipoDocumentoNome": "Edital", "statusAtivo": True, "titulo": "edital"},
        {"tipoDocumentoNome": "Edital", "statusAtivo": False},
    ]
    escolhido = escolher_arquivo_edital(arquivos)
    assert escolhido["titulo"] == "edital"
    assert escolher_arquivo_edital([]) is None
    # aviso de contratação direta (dispensa) também é aceito
    aviso = [{"tipoDocumentoNome": "Aviso de Contratação Direta", "statusAtivo": True}]
    assert escolher_arquivo_edital(aviso) == aviso[0]
