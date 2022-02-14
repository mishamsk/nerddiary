.DEFAULT_GOAL := help

sources = nerddiary

define BROWSER_PYSCRIPT
import os, webbrowser, sys

from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

BROWSER := python -c "$$BROWSER_PYSCRIPT"

.PHONY: help
help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

.PHONY: clean
clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

.PHONY: clean-build
clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +
	find . -name '.mypy_cache' -exec rm -fr {} +
	find . -name 'requirements-*.txt' -exec rm -fr {} +

.PHONY: clean-pyc
clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

.PHONY: clean-test
clean-test: ## remove test and coverage artifacts
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache
	rm -fr testtemp/
	find . -name '*.log' -d 1 -exec rm -f {} +
	find . -name '*.session' -d 1 -exec rm -f {} +

.PHONY: lint
lint: ## check style with flake8
	flake8 $(sources)

.PHONY: format
format:
	isort $(sources)
	black $(sources)

.PHONY: test
test: ## run tests quickly with the default Python
	pytest

.PHONY: test-performance
test-performance: ## run tests quickly with the default Python
	pytest -m performance

# test-all: ## run tests on every Python version with tox
# 	tox

.PHONY: cov-path
cov-path: ## check code coverage using pytest for a path (set with path=), report to terminal
	pytest --cov=$(path) --cov-report term:skip-covered $(path)

.PHONY: coverage
coverage: ## check code coverage quickly with the default Python
	pytest --cov=nerddiary --cov-report html --cov-report term:skip-covered
# 	$(BROWSER) htmlcov/index.html

# docs: ## generate Sphinx HTML documentation, including API docs
# 	rm -f docs/nerddiary.rst
# 	rm -f docs/modules.rst
# 	sphinx-apidoc -o docs/ nerddiary
# 	$(MAKE) -C docs clean
# 	$(MAKE) -C docs html
# 	$(BROWSER) docs/_build/html/index.html

# servedocs: docs ## compile the docs watching for changes
# 	watchmedo shell-command -p '*.rst' -c '$(MAKE) -C docs html' -R -D .

# run-dev: ## if dist/ has docker-compose - docker-compose up
#	[[ -f dist/docker-compose.yml ]] && docker-compose up

.PHONY: pre-commit
pre-commit:
	pre-commit run --all-files

.PHONY: release-minor
release-minor: clean ## bump minor version and package for distribution
	bump2version minor
	poetry build -f wheel
	poetry export -f requirements.txt --without-hashes > requirements.txt

.PHONY: release-major
release-major: clean ## bump minmajoror version and package for distribution
	bump2version major
	poetry build -f wheel
	poetry export -f requirements.txt --without-hashes > requirements.txt

.PHONY: dist
dist: clean ## builds source and wheel package
	format
	lint
	poetry build
	poetry export -f requirements.txt --without-hashes > requirements.txt
	poetry publish

.PHONY: install
install: clean ## install the package to the active Python's site-packages
	poetry install --remove-untracked

.PHONY: pip-req
pip-req: ## generate requirements-full.txt file will all dependencies (dev included)
	poetry export -f requirements.txt --output requirements-full.txt -E full --dev --without-hashes

.PHONY: pip-req-ext
pip-req-ext: ## generate requirements-$(extras).txt file will one of the extras dependencies (dev excluded). Use extras=[client|tgbot|server]
	poetry export -f requirements.txt --output requirements-$(extras).txt -E $(extras) --without-hashes

.PHONY: docker-build
docker-build: docker-stop ## Build dev docker images
	@docker-compose -f docker/docker-compose-dev.yml -p nerddiary build

.PHONY: docker-run
docker-run: docker-stop  ## Run dev docker containers
	@docker-compose -f docker/docker-compose-dev.yml -p nerddiary up --remove-orphans -d

.PHONY: docker-stop
docker-stop: ## Stop dev docker containers
	@docker-compose -f docker/docker-compose-dev.yml -p nerddiary down --remove-orphans
