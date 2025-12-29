FROM python:3.11-slim

# =========================
# DEPENDENCIAS DEL SISTEMA
# =========================
RUN apt-get update && apt-get install -y \
    build-essential \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# =========================
# WORKDIR
# =========================
WORKDIR /app

# =========================
# PYTHON DEPENDENCIES
# =========================
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# =========================
# PROYECTO
# =========================
COPY . .

# =========================
# VARIABLES DJANGO
# =========================
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# =========================
# STATIC FILES
# =========================
RUN python manage.py collectstatic --noinput

# =========================
# START
# =========================
EXPOSE 10000
CMD ["python", "-m", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:10000"]