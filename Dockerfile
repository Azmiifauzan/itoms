FROM python:3.11-slim-bookworm

WORKDIR /app

# Dependency sistem buat WeasyPrint (generate PDF Berita Acara).
# Base image dikunci ke "bookworm" (bukan cuma "slim") biar nama paket di
# bawah ini gak tiba-tiba berubah kalau tag "slim" pindah ke versi Debian
# yang lebih baru di kemudian hari.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .