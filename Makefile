# Nimbus Voice Agent — dev commands.
.PHONY: install dev api web test scrape

VENV := backend/.venv/bin

install:
	cd backend && python3 -m venv --clear .venv && ./.venv/bin/python -m pip install -r requirements.txt

# Start backend (:8100) + static site (:8092) together. Ctrl-C stops both.
dev:
	./scripts/dev.sh

api:
	cd backend && ./.venv/bin/python -m uvicorn app.main:app --reload --port 8100

web:
	python3 scripts/serve.py 8092

test:
	cd backend && ./.venv/bin/python -m pytest -q

# Build the RAG/RAGless corpus from the catalog (Phase 1).
scrape:
	cd backend && ./.venv/bin/python -m app.scraping.scrape && ./.venv/bin/python -m app.scraping.build_context
