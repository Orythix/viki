# AI Security Learning Lab — API (defensive / educational only)
FROM python:3.11-slim-bookworm

RUN useradd -m -u 10001 labuser
WORKDIR /srv

COPY security /srv/security
COPY monitoring /srv/monitoring
COPY backend /srv/backend

RUN pip install --no-cache-dir -r /srv/backend/requirements.txt \
    && chown -R labuser:labuser /srv

USER labuser
ENV PYTHONPATH=/srv
WORKDIR /srv/backend

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
