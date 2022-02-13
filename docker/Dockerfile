FROM python:3.10.1
ARG extras=full

RUN mkdir /app
WORKDIR /app

RUN mkdir data

COPY pyproject.toml .env README.md ./
COPY nerddiary/ nerddiary/

RUN python -m pip install poetry \
    && poetry config virtualenvs.create false --local \
    && poetry install -E ${extras}
