FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY recovery_tester /app/recovery_tester

RUN python -m pip install --upgrade pip && \
    pip install .[dev]

ENV ARTIFACTS_DIR=/app/output
VOLUME ["/app/output"]

CMD ["python", "-m", "recovery_tester", "demo", "--artifacts-dir", "/app/output"]
