.PHONY: clean clean-test clean-pyc clean-build docs help run-dev
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

help:
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

clean: clean-build clean-pyc clean-test ## remove all build, test, coverage and Python artifacts

clean-build: ## remove build artifacts
	rm -fr build/
	rm -fr dist/
	rm -fr .eggs/
	find . -name '*.egg-info' -exec rm -fr {} +
	find . -name '*.egg' -exec rm -f {} +
	find . -name '.mypy_cache' -exec rm -fr {} +

clean-pyc: ## remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -fr {} +

clean-test: ## remove test and coverage artifacts
	rm -f .coverage
	rm -fr htmlcov/
	rm -fr .pytest_cache
	rm -fr testtemp/
	find . -name '*.log' -d 1 -exec rm -f {} +

lint: ## check style with flake8
	flake8 $(sources)

format:
	isort $(sources)
	black $(sources)

test: ## run tests quickly with the default Python
	pytest

test-performance: ## run tests quickly with the default Python
	pytest -m performance

# test-all: ## run tests on every Python version with tox
# 	tox

cov-path: ## check code coverage using pytest for a path (set with path=), report to terminal
	pytest --cov=$(path) --cov-report term:skip-covered $(path)

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

pre-commit:
	pre-commit run --all-files

release-minor: clean ## bump minor version and package for distribution
	bump2version minor
	poetry build -f wheel
	poetry export -f requirements.txt --without-hashes > requirements.txt

release-major: clean ## bump minmajoror version and package for distribution
	bump2version major
	poetry build -f wheel
	poetry export -f requirements.txt --without-hashes > requirements.txt

dist: clean ## builds source and wheel package
	format
	lint
	poetry build
	poetry export -f requirements.txt --without-hashes > requirements.txt
	poetry publish

install: clean ## install the package to the active Python's site-packages
	poetry install --remove-untracked
