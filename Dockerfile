FROM python:3.12-alpine as builder

# Install build dependencies
RUN apk add --no-cache build-base git && rm -rf /var/cache/apk/*
RUN pip install "poetry<2.0.0"

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Install dependencies
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root && rm -rf $POETRY_CACHE_DIR

# Build runtime image
FROM python:3.12-alpine as runtime
LABEL maintainer="David Sn <divad.nnamtdeis@gmail.com>"

# Add virtualenv to PATH
ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv \
    DEBUG=false

# Copy app files
WORKDIR /app
COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY trainz_dl ./trainz_dl
CMD ["uvicorn", "trainz_dl:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
