FROM python:3.12-slim

WORKDIR /app

# Display virtual + acceso VNC por navegador
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# install-deps: librerías del sistema que Chromium necesita.
# install chromium: descarga el build que coincide EXACTAMENTE con la versión de playwright resuelta por pip
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install-deps chromium \
    && python -m playwright install chromium

COPY . .

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/data/exports

ENV PYTHONUNBUFFERED=1 \
    DISPLAY=:99

EXPOSE 5000 6080

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--timeout", "0", "--bind", "0.0.0.0:5000", "app:app"]
