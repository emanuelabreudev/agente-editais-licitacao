"""Camada de acesso ao LLM: cliente Anthropic real + mock determinístico.

O agente conversa com o LLM por um protocolo mínimo (RespostaLLM com blocos
normalizados), o que permite:
  - trocar o modelo por configuração (EDITAL_AGENT_LLM_MODELO);
  - rodar o pipeline inteiro offline com MockLLM (testes/CI, smoke test);
  - medir custo (tokens, chamadas, USD) e latência por edital (objetivo 6).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

# Preço USD por milhão de tokens (entrada, saída) — tabela Anthropic, jun/2026.
PRECOS_USD_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "mock": (0.0, 0.0),
}


@dataclass
class UsoLLM:
    """Acumulador de uso: tokens, chamadas, custo estimado e latência."""

    modelo: str = "mock"
    chamadas: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    latencia_total_s: float = 0.0

    def registrar(self, entrada: int, saida: int, latencia_s: float) -> None:
        self.chamadas += 1
        self.tokens_entrada += entrada
        self.tokens_saida += saida
        self.latencia_total_s += latencia_s

    @property
    def custo_usd(self) -> float:
        preco_in, preco_out = PRECOS_USD_MTOK.get(self.modelo, (0.0, 0.0))
        return (
            self.tokens_entrada * preco_in + self.tokens_saida * preco_out
        ) / 1_000_000

    def como_dict(self) -> dict[str, Any]:
        return {
            "modelo": self.modelo,
            "chamadas": self.chamadas,
            "tokens_entrada": self.tokens_entrada,
            "tokens_saida": self.tokens_saida,
            "custo_usd": round(self.custo_usd, 6),
            "latencia_total_s": round(self.latencia_total_s, 3),
        }


@dataclass
class RespostaLLM:
    """Resposta normalizada: blocos como dicts + conteúdo bruto p/ eco no histórico."""

    blocos: list[dict[str, Any]]
    stop_reason: str
    conteudo_bruto: Any  # o que deve voltar como mensagem assistant no histórico

    @property
    def chamadas_ferramenta(self) -> list[dict[str, Any]]:
        return [b for b in self.blocos if b.get("type") == "tool_use"]

    @property
    def texto(self) -> str:
        return "\n".join(b.get("text", "") for b in self.blocos if b.get("type") == "text")


class AnthropicLLM:
    """Cliente da API da Anthropic (Messages API com tool use)."""

    def __init__(self, modelo: str = "claude-opus-4-8", max_tokens: int = 4096):
        import anthropic

        self.modelo = modelo
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()
        self.uso = UsoLLM(modelo=modelo)

    def criar_mensagem(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
    ) -> RespostaLLM:
        inicio = time.monotonic()
        kwargs: dict[str, Any] = dict(
            model=self.modelo,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
        )
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
            # thinking adaptativo é incompatível com tool_choice forçado
            kwargs.pop("thinking", None)
        resposta = self._client.messages.create(**kwargs)
        latencia = time.monotonic() - inicio
        self.uso.registrar(
            resposta.usage.input_tokens, resposta.usage.output_tokens, latencia
        )
        blocos: list[dict[str, Any]] = []
        for b in resposta.content:
            if b.type == "text":
                blocos.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocos.append(
                    {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                )
        return RespostaLLM(
            blocos=blocos,
            stop_reason=resposta.stop_reason or "end_turn",
            conteudo_bruto=resposta.content,  # inclui blocos de thinking p/ eco
        )


class MockLLM:
    """LLM determinístico para testes/CI e smoke test offline.

    Simula o comportamento do agente: 1º turno emite buscas semânticas para os
    campos-alvo; ao receber os resultados, extrai valores dos trechos
    recuperados com as heurísticas do baseline e chama `registrar_extracao`.
    Não usa rede. Custo zero. Resultados NÃO representam o agente real.
    """

    CONSULTAS = [
        ("prazo_entrega_proposta", "data limite para entrega e abertura das propostas"),
        ("valor_estimado", "valor total estimado da contratação"),
        ("modalidade", "modalidade da licitação pregão concorrência dispensa"),
        ("objeto", "objeto da licitação descrição"),
        ("criterio_julgamento", "critério de julgamento menor preço"),
        ("prazo_execucao", "prazo de execução vigência do contrato"),
    ]

    def __init__(self, modelo: str = "mock", max_tokens: int = 0):
        self.modelo = "mock"
        self.uso = UsoLLM(modelo="mock")

    def criar_mensagem(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
    ) -> RespostaLLM:
        # custo/latência simbólicos: proporcionais ao tamanho do prompt
        tamanho = sum(len(json.dumps(m, default=str, ensure_ascii=False)) for m in messages)
        self.uso.registrar(entrada=tamanho // 4, saida=200, latencia_s=0.0)

        resultados = self._coletar_resultados_ferramentas(messages)
        if not resultados:
            blocos = [
                {
                    "type": "tool_use",
                    "id": f"mock_busca_{i}",
                    "name": "buscar_trechos",
                    "input": {"consulta": consulta, "top_k": 4},
                }
                for i, (_, consulta) in enumerate(self.CONSULTAS)
            ]
            return RespostaLLM(blocos=blocos, stop_reason="tool_use", conteudo_bruto=blocos)

        extracao = self._extrair_dos_resultados(resultados)
        bloco = {
            "type": "tool_use",
            "id": "mock_final",
            "name": "registrar_extracao",
            "input": extracao,
        }
        return RespostaLLM(blocos=[bloco], stop_reason="tool_use", conteudo_bruto=[bloco])

    @staticmethod
    def _coletar_resultados_ferramentas(messages: list[dict[str, Any]]) -> list[dict]:
        resultados = []
        for m in messages:
            if m.get("role") != "user" or not isinstance(m.get("content"), list):
                continue
            for bloco in m["content"]:
                if isinstance(bloco, dict) and bloco.get("type") == "tool_result":
                    try:
                        resultados.append(json.loads(bloco.get("content") or "{}"))
                    except (TypeError, json.JSONDecodeError):
                        pass
        return resultados

    def _extrair_dos_resultados(self, resultados: list[dict]) -> dict[str, Any]:
        from ..baseline.regex_extractor import extrair_por_regex

        trechos: list[dict] = []
        for r in resultados:
            trechos.extend(r.get("trechos", []))
        texto = "\n\n".join(t.get("texto", "") for t in trechos)
        base = extrair_por_regex(texto)

        def campo(valor: Any) -> dict[str, Any]:
            evidencias = []
            if valor is not None:
                alvo = _normalizar(str(valor))
                for t in trechos:
                    if alvo and alvo.split()[0] in _normalizar(t.get("texto", "")):
                        evidencias = [t.get("chunk_id")]
                        break
            return {
                "valor": valor,
                "chunks_evidencia": evidencias,
                "citacao": None,
                "confianca": 0.5 if valor is not None else 0.0,
            }

        return {c: campo(getattr(base, c)) for c in (
            "prazo_entrega_proposta", "valor_estimado", "modalidade", "objeto",
            "orgao_responsavel", "uf", "criterio_julgamento", "prazo_execucao",
        )}


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.lower()).strip()


def criar_llm(modelo: str, max_tokens: int = 4096):
    """Fábrica: `mock` → MockLLM; qualquer outro id → AnthropicLLM."""
    if modelo == "mock":
        return MockLLM()
    return AnthropicLLM(modelo=modelo, max_tokens=max_tokens)
