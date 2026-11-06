# One-command setup, lint, typecheck, and offline tests (NSE-001).
# Uses .venv when it exists. CI installs into the runner and leaves PY=python3.

ifeq ($(origin PY), undefined)
  ifneq ($(wildcard .venv/bin/python),)
    PY := .venv/bin/python
  else
    PY := python3
  endif
endif

.DEFAULT_GOAL := help

.PHONY: help setup lint typecheck test audit secrets secrets-history check ci

help:
	@echo "setup            create .venv and install pinned requirements"
	@echo "lint             ruff check ."
	@echo "typecheck        mypy (see pyproject.toml)"
	@echo "test             pytest offline; paper mode, live orders off"
	@echo "audit            pip-audit; new advisory IDs fail, baselined IDs do not"
	@echo "secrets          gitleaks on the working tree (blocking)"
	@echo "secrets-history  gitleaks on git history (CI treats this as report-only)"
	@echo "check            lint + typecheck + test + audit"
	@echo "ci               check + working-tree secret scan"

setup:
	@$(PY) -c 'import sys; assert sys.version_info >= (3, 12), sys.version'
	$(PY) -m venv .venv
	.venv/bin/python -m pip install -U pip
	.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

lint:
	$(PY) -m ruff check .

typecheck:
	$(PY) -m mypy

test:
	NSE_FORCE_PAPER=1 MODE=paper LIVE_ORDERS=false $(PY) -m pytest -q

audit:
	$(PY) -m pip_audit -r requirements.txt -r requirements-dev.txt --progress-spinner off \
		$$(awk 'NF && $$1 !~ /^#/ {printf "--ignore-vuln %s ", $$1}' security/pip-audit-baseline.txt)

secrets:
	bash scripts/install_gitleaks.sh
	./tools/gitleaks detect --no-git --source . --redact --config .gitleaks.toml

secrets-history:
	bash scripts/install_gitleaks.sh
	./tools/gitleaks detect --source . --redact --log-opts="--all" --config .gitleaks.toml

check: lint typecheck test audit

ci: check secrets
