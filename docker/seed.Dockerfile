FROM python:3.12-slim
WORKDIR /app
COPY synthetic/seed_es.py ./seed_es.py
COPY synthetic/watch_seed.py ./watch_seed.py
COPY generated /data
ENV DATA_DIR=/data
CMD ["python", "seed_es.py"]
