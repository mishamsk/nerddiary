FROM python:3.10.1
ARG extras=full

RUN mkdir /app
WORKDIR /app

RUN mkdir data

COPY .env ./

RUN python -m pip install nerddiary[server]==0.2.0a0
