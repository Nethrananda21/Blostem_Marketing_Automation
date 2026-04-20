FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

COPY apps/api/requirements.txt ./apps/api/requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install -r apps/api/requirements.txt

COPY apps ./apps
COPY pytest.ini ./pytest.ini

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
