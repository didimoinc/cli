FROM python:3-alpine

WORKDIR /app

COPY didimo_cli*.whl .
RUN pip3 install didimo_cli*.whl && rm didimo_cli*.whl
