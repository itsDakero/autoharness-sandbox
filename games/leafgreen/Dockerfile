FROM python:3.12.15-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY src/ ./src/
COPY data/ ./data/
COPY scripts/assemble.py ./scripts/
RUN python scripts/assemble.py
COPY server.py .
USER 1000:1000
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"
CMD ["python", "server.py"]
