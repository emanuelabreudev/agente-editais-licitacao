"""Agente autônomo (single-agent) de extração com orquestração de ferramentas.

Arquitetura (objetivo específico 4): agente único com function calling sobre um
índice RAG do edital. Ferramentas:
  - buscar_trechos: busca semântica no índice FAISS do edital;
  - ler_trecho: leitura de um chunk com vizinhos (contexto adicional);
  - registrar_extracao: entrega final estruturada (schema estrito).

Controle de alucinação:
  - o prompt exige citação de chunk_id + trecho literal para todo campo;
  - o pós-processamento valida cada citação contra os chunks efetivamente
    recuperados (evidencia_valida), permitindo medir e filtrar alucinações.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..indexacao.vetorial import IndiceVetorial
from ..llm.cliente import RespostaLLM, UsoLLM
from ..normalizacao import normalizar_texto
from .schema import CAMPOS, ExtracaoEdital, schema_ferramenta_extracao

logger = logging.getLogger(__name__)

PROMPT_SISTEMA = """Você é um agente especialista em análise de editais de licitação do governo \
brasileiro (Lei 14.133/2021). Sua tarefa é extrair campos estruturados de UM edital, usando \
exclusivamente as ferramentas de busca e leitura sobre o texto do próprio edital.

Campos a extrair:
- prazo_entrega_proposta: data limite para entrega/encerramento do recebimento das propostas \
(se houver data e hora, formate 'AAAA-MM-DD HH:MM'; senão 'AAAA-MM-DD').
- valor_estimado: valor TOTAL estimado da contratação, em reais, como número (ex.: 554771.65). \
Se o orçamento for sigiloso ou o valor não constar, use null.
- modalidade: uma das categorias do schema.
- objeto: descrição resumida do objeto.
- orgao_responsavel: órgão/entidade licitante.
- uf: sigla da UF do órgão.
- criterio_julgamento: uma das categorias do schema.
- prazo_execucao: prazo de execução/vigência do contrato (ex.: '12 meses').

Regras obrigatórias:
1. Baseie CADA campo apenas em trechos retornados pelas ferramentas. Nunca use conhecimento \
externo nem invente valores.
2. Para cada campo preenchido, informe em chunks_evidencia o(s) id(s) do(s) chunk(s) usados e em \
citacao um trecho LITERAL e curto copiado do chunk que comprova o valor.
3. Se a informação não aparecer nos trechos recuperados, faça novas buscas com termos \
alternativos; se ainda assim não encontrar, use valor null e confianca 0.
4. Faça quantas buscas precisar (várias por turno é permitido) e use ler_trecho para expandir \
contexto quando um trecho parecer truncado.
5. Ao terminar, chame registrar_extracao exatamente uma vez com todos os campos.
"""


def definicoes_ferramentas() -> list[dict[str, Any]]:
    return [
        {
            "name": "buscar_trechos",
            "description": (
                "Busca semântica no índice vetorial do edital. Retorna os trechos mais "
                "similares à consulta, com id, seção e score. Use consultas curtas e "
                "específicas (ex.: 'data de encerramento das propostas')."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Consulta em português."},
                    "top_k": {
                        "type": "integer",
                        "description": "Quantidade de trechos (padrão 5, máx. 10).",
                    },
                },
                "required": ["consulta"],
                "additionalProperties": False,
            },
        },
        {
            "name": "ler_trecho",
            "description": (
                "Lê um chunk pelo id, incluindo os chunks vizinhos para dar contexto. "
                "Use quando um trecho recuperado parecer cortado."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string"},
                    "janela": {
                        "type": "integer",
                        "description": "Vizinhos de cada lado (padrão 1, máx. 3).",
                    },
                },
                "required": ["chunk_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "registrar_extracao",
            "description": "Registra a extração final estruturada. Chame exatamente uma vez, ao terminar.",
            "input_schema": schema_ferramenta_extracao(),
            "strict": True,
        },
    ]


@dataclass
class ResultadoAgente:
    id_edital: str
    extracao: ExtracaoEdital
    contextos: list[dict[str, Any]]  # chunks recuperados (para RAGAS)
    iteracoes: int
    uso: dict[str, Any]
    latencia_s: float
    trace: list[dict[str, Any]] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "id_edital": self.id_edital,
            "extracao": self.extracao.model_dump(),
            "contextos": self.contextos,
            "iteracoes": self.iteracoes,
            "uso": self.uso,
            "latencia_s": round(self.latencia_s, 3),
            "trace": self.trace,
        }


class AgenteEdital:
    """Loop agêntico manual (request → tool_use → tool_result → ...)."""

    def __init__(self, llm, indice: IndiceVetorial, max_iteracoes: int = 12):
        self.llm = llm
        self.indice = indice
        self.max_iteracoes = max_iteracoes
        self._contextos: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ tools
    def _tool_buscar(self, consulta: str, top_k: int = 5) -> dict[str, Any]:
        top_k = max(1, min(int(top_k or 5), 10))
        resultados = self.indice.buscar(consulta, top_k=top_k)
        trechos = []
        for chunk, score in resultados:
            self._contextos[chunk.id] = {
                "chunk_id": chunk.id,
                "secao": chunk.secao,
                "texto": chunk.texto,
            }
            trechos.append(
                {
                    "chunk_id": chunk.id,
                    "secao": chunk.secao,
                    "score": round(score, 4),
                    "texto": chunk.texto,
                }
            )
        return {"consulta": consulta, "trechos": trechos}

    def _tool_ler(self, chunk_id: str, janela: int = 1) -> dict[str, Any]:
        janela = max(0, min(int(janela or 1), 3))
        chunks = self.indice.obter_chunk(chunk_id, janela=janela)
        if not chunks:
            return {"erro": f"chunk '{chunk_id}' não encontrado"}
        trechos = []
        for chunk in chunks:
            self._contextos[chunk.id] = {
                "chunk_id": chunk.id,
                "secao": chunk.secao,
                "texto": chunk.texto,
            }
            trechos.append({"chunk_id": chunk.id, "secao": chunk.secao, "texto": chunk.texto})
        return {"trechos": trechos}

    def _executar_ferramenta(self, nome: str, entrada: dict[str, Any]) -> tuple[str, bool]:
        try:
            if nome == "buscar_trechos":
                saida = self._tool_buscar(**entrada)
            elif nome == "ler_trecho":
                saida = self._tool_ler(**entrada)
            else:
                return json.dumps({"erro": f"ferramenta desconhecida: {nome}"}), True
            return json.dumps(saida, ensure_ascii=False), False
        except Exception as exc:
            logger.exception("Erro na ferramenta %s", nome)
            return json.dumps({"erro": str(exc)}, ensure_ascii=False), True

    # ------------------------------------------------------------------- loop
    def executar(self, id_edital: str) -> ResultadoAgente:
        inicio = time.monotonic()
        self._contextos = {}
        trace: list[dict[str, Any]] = []
        ferramentas = definicoes_ferramentas()
        mensagem_inicial = (
            f"Analise o edital '{id_edital}' e extraia os campos. O texto está indexado; "
            "comece com buscas semânticas pelos campos críticos (prazo de entrega das "
            "propostas, valor estimado, modalidade) e depois pelos demais."
        )
        mensagens: list[dict[str, Any]] = [{"role": "user", "content": mensagem_inicial}]
        extracao_bruta: dict[str, Any] | None = None
        iteracao = 0

        while iteracao < self.max_iteracoes:
            iteracao += 1
            resposta: RespostaLLM = self.llm.criar_mensagem(
                system=PROMPT_SISTEMA, messages=mensagens, tools=ferramentas
            )
            if resposta.stop_reason == "refusal":
                logger.warning("LLM recusou a requisição para %s", id_edital)
                break
            chamadas = resposta.chamadas_ferramenta
            if not chamadas:
                if resposta.stop_reason == "pause_turn":
                    mensagens.append({"role": "assistant", "content": resposta.conteudo_bruto})
                    continue
                logger.warning(
                    "Agente parou sem registrar_extracao (%s): %s",
                    id_edital, resposta.texto[:200],
                )
                break

            mensagens.append({"role": "assistant", "content": resposta.conteudo_bruto})
            resultados_ferramentas: list[dict[str, Any]] = []
            for chamada in chamadas:
                if chamada["name"] == "registrar_extracao":
                    extracao_bruta = chamada["input"]
                    trace.append({"iteracao": iteracao, "ferramenta": "registrar_extracao"})
                    resultados_ferramentas.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": chamada["id"],
                            "content": json.dumps({"status": "registrado"}),
                        }
                    )
                    continue
                saida, erro = self._executar_ferramenta(chamada["name"], chamada["input"])
                trace.append(
                    {
                        "iteracao": iteracao,
                        "ferramenta": chamada["name"],
                        "entrada": chamada["input"],
                        "erro": erro,
                    }
                )
                resultados_ferramentas.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": chamada["id"],
                        "content": saida,
                        **({"is_error": True} if erro else {}),
                    }
                )
            mensagens.append({"role": "user", "content": resultados_ferramentas})
            if extracao_bruta is not None:
                break

        extracao = self._pos_processar(extracao_bruta or {})
        return ResultadoAgente(
            id_edital=id_edital,
            extracao=extracao,
            contextos=list(self._contextos.values()),
            iteracoes=iteracao,
            uso=self.llm.uso.como_dict() if isinstance(self.llm.uso, UsoLLM) else {},
            latencia_s=time.monotonic() - inicio,
            trace=trace,
        )

    # --------------------------------------------------------- pós-validação
    def _pos_processar(self, bruto: dict[str, Any]) -> ExtracaoEdital:
        """Valida o schema e confere cada citação contra os chunks recuperados."""
        extracao = ExtracaoEdital.model_validate(bruto) if bruto else ExtracaoEdital()
        for nome in CAMPOS:
            campo = extracao.campo(nome)
            if campo.valor is None:
                campo.evidencia_valida = None
                continue
            ids_validos = [cid for cid in campo.chunks_evidencia if cid in self._contextos]
            if not ids_validos:
                campo.evidencia_valida = False
                continue
            if campo.citacao:
                citacao = normalizar_texto(campo.citacao)[:150]
                campo.evidencia_valida = any(
                    citacao in normalizar_texto(self._contextos[cid]["texto"])
                    for cid in ids_validos
                )
            else:
                campo.evidencia_valida = True  # cita chunk válido, sem trecho literal
        return extracao
