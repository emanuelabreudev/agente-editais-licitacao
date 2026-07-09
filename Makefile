# Pipeline end-to-end do Agente de Análise de Editais.
# Pré-requisito: `make setup` (cria .venv e instala dependências fixadas).

PY := .venv/bin/python
MODELO ?=            # vazio = usa configs/config.yaml (claude-opus-4-8)
JUIZ ?= llm

.PHONY: setup coletar processar indexar baseline agente agente-mock \
        avaliar avaliar-baseline avaliar-mock eda test smoke pipeline-offline tudo

setup:
	python3.12 -m venv .venv || python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e . --no-deps

coletar:
	$(PY) scripts/01_coletar.py

processar:
	$(PY) scripts/02_processar.py

indexar:
	$(PY) scripts/03_indexar.py

baseline:
	$(PY) scripts/04_extrair.py --executor baseline

agente:
	$(PY) scripts/04_extrair.py --executor agente $(if $(MODELO),--modelo $(MODELO),)

agente-mock:
	$(PY) scripts/04_extrair.py --executor agente --modelo mock

avaliar-baseline:
	$(PY) scripts/05_avaliar.py --alvo baseline

avaliar:
	$(PY) scripts/05_avaliar.py --alvo agente --juiz $(JUIZ)

avaliar-mock:
	$(PY) scripts/05_avaliar.py --alvo agente_mock --juiz heuristico

eda:
	$(PY) scripts/eda.py

data-card:
	$(PY) scripts/gerar_data_card.py

test:
	$(PY) -m pytest

# Smoke test offline: exercita o pipeline completo sem chave de API
smoke: baseline agente-mock avaliar-baseline avaliar-mock

# Reprodução completa sem LLM (dados reais do PNCP)
pipeline-offline: coletar processar indexar baseline avaliar-baseline eda data-card

# Reprodução completa com LLM (requer ANTHROPIC_API_KEY)
tudo: coletar processar indexar baseline agente avaliar-baseline avaliar eda data-card
