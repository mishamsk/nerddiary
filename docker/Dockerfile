FROM python:3.10.1

RUN mkdir /app
WORKDIR /app

RUN mkdir data

COPY .env ./

RUN python -m pip install nerddiary[server]==0.3.1a
