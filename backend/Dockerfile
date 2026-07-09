FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data

ENV DATABASE_URL=sqlite:////data/casino.db
ENV PORT=7777

EXPOSE 7777

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7777/api/health')"

CMD ["gunicorn", "--bind", "0.0.0.0:7777", "--workers", "4", "--timeout", "60", "app:app"]