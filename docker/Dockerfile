FROM python:3.10.1
ARG extras=full

RUN mkdir /app
WORKDIR /app

COPY pyproject.toml poetry.lock .env README.md ./
COPY nerddiary/ nerddiary/

RUN python -m pip install poetry \
    && poetry config virtualenvs.create false --local \
    && poetry install -E ${extras}
