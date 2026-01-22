#!/usr/bin/env bash

set -e

if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y \
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
    fonts-liberation
  rm -rf /var/lib/apt/lists/*
fi

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
