# Proposta (síntese) — Agente Autônomo para Análise de Editais de Licitação

Síntese da proposta da disciplina que este repositório implementa.

## Contexto

No ecossistema de compras públicas brasileiro, a participação em licitações exige analisar
editais extensos, com informações críticas (prazos, modalidade, valor estimado, critérios
de julgamento, habilitação) fragmentadas e não padronizadas. A análise manual é demorada e
propensa a erros; soluções de busca textual não oferecem extração estruturada com
rastreabilidade de evidências.

## Pergunta de pesquisa

> Em que medida um agente autônomo baseado em RAG consegue extrair campos críticos
> (prazo, valor estimado, modalidade) de editais de licitação com **Faithfulness ≥ 0,85**
> e **Answer Correctness ≥ 0,80** (métricas RAGAS), utilizando o próprio texto do edital
> como referência, com **taxa de alucinação controlada ≤ 10%**?

## Hipótese

O agente alcançará os três limiares nos campos críticos.

## Objetivos específicos

1. Coletar amostra de editais e metadados das APIs oficiais (Compras.gov.br/PNCP),
   abrangendo diferentes modalidades e órgãos.
2. Construir benchmark piloto incremental (10 → até 20 editais conforme estabilização do
   desvio-padrão), com o texto integral como referência de validação.
3. Pipeline de extração documental com OCR (Tesseract), chunking semântico e indexação
   vetorial (FAISS).
4. Agente autônomo single-agent com orquestração de ferramentas (busca semântica, leitura
   de trechos, extração estruturada com function calling).
5. Avaliação RAGAS — Faithfulness e Answer Correctness — com médias por campo e por edital.
6. Custo operacional (tokens, chamadas) e latência por edital.
7. Documentação reproduzível: dependências fixadas, instalação e execução end-to-end.

## Campos de extração

| Campo | Tipo | Crítico (meta RAGAS)? |
|---|---|---|
| prazo_entrega_proposta | Data | ✅ |
| valor_estimado | Monetário | ✅ |
| modalidade | Categórico | ✅ |
| objeto | Texto | descritivo |
| orgao_responsavel | Texto | descritivo |
| uf | Categórico | descritivo |
| criterio_julgamento | Categórico | descritivo |
| prazo_execucao | Data/duração | descritivo |

## Riscos de dados e tratamentos (seção 2.4 da proposta)

| Risco | Tratamento implementado |
|---|---|
| PDF escaneado | Fallback OCR via Tesseract (`extracao/pdf.py`) |
| Anexos extensos | Chunking seletivo por seção + limite de páginas no piloto |
| Orçamento sigiloso | Valor nulo = indisponibilidade, não erro (comparador trata abstenção) |
| Campos ausentes | Schema flexível com confiança + anotação `gt_presente_no_texto` |
| Amostra homogênea | Cotas por modalidade e por UF na coleta |

## Baseline e meta comparativa

Extração por regex sobre o texto do edital; meta de referência ≥ 80% de acurácia em
prazo, valor e modalidade.
