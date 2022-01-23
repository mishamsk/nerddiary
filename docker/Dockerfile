FROM python:3.10.1
ARG NERDDIARY_VERSION
WORKDIR /app
COPY nerddiary-$NERDDIARY_VERSION-py3-none-any.whl requirements.txt config.json auth_tokens.json credentials.json ./
RUN if [ -e requirements.txt ]; then \
    python3 -m pip install --no-cache-dir \
    --disable-pip-version-check \
    -r requirements.txt; \
    fi \
    && python3 -m pip install \
    --no-cache-dir --disable-pip-version-check \
    nerddiary-$NERDDIARY_VERSION-py3-none-any.whl
# ENTRYPOINT ["nerddiary", "-v"]
