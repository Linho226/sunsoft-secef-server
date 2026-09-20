FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install .

RUN useradd \
    --create-home \
    --uid 10001 \
    --shell /usr/sbin/nologin \
    secef

USER secef

EXPOSE 9000

CMD ["python", "-m", "sunsoft_secef_server"]