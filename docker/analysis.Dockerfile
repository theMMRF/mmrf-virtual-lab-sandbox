FROM python:3.9-slim
WORKDIR /app
RUN pip install --no-cache-dir poetry==2.1.4
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && poetry install --only main --no-root --no-interaction
COPY gen3analysis ./gen3analysis
COPY README.md ./README.md
RUN poetry install --only main --no-interaction
CMD ["uvicorn", "gen3analysis.main:app_instance", "--host", "0.0.0.0", "--port", "8000"]
