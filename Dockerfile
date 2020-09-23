FROM python:3-alpine as builder
WORKDIR /app
ARG CLI_VERSION=dev
COPY . .
RUN echo "__version__ = \"${CLI_VERSION}\"" > cli/_version.py \
    && python3 setup.py bdist_wheel

FROM python:3-alpine
WORKDIR /app
COPY --from=builder /app/dist/ /app/
RUN pip3 install didimo_cli*.whl && rm didimo_cli*.whl
ENTRYPOINT ["/usr/local/bin/didimo"]
