FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Optional Claude provider: docker compose build --build-arg WITH_ANTHROPIC=1
ARG WITH_ANTHROPIC=0
RUN if [ "$WITH_ANTHROPIC" = "1" ]; then pip install --no-cache-dir anthropic; fi

COPY app ./app
COPY static ./static
RUN useradd --create-home app && chown -R app /srv
USER app

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=12 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
