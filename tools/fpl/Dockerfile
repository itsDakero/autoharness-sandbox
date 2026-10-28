FROM python:3.12.15-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Solio's open-fpl-solver (Apache-2.0), pinned to a commit. Not pip-installed: its pyproject says Python >=3.14,
# but the code only needs 3.10+ syntax (checked by reading; the first real run is the test, see README).
# PYTHONPATH makes `dev`, `paths` and `utils` importable from /opt/solver/run.
ADD https://github.com/solioanalytics/open-fpl-solver/archive/ec65f5e2b2be34441cb4b2a9efafea1ec0fe3b79.tar.gz /tmp/solver.tar.gz
RUN mkdir -p /opt/solver \
 && tar -xzf /tmp/solver.tar.gz -C /opt/solver --strip-components=1 \
 && rm /tmp/solver.tar.gz \
 && chown -R 1000:1000 /opt/solver
ENV PYTHONPATH=/opt/solver SOLVER_DIR=/opt/solver
COPY collector/ ./collector/
COPY web/ ./web/
COPY model/ ./model/
COPY tests/ ./tests/
USER 1000:1000
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"
CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
