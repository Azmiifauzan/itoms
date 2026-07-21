FROM python:3.11-slim

WORKDIR /app

# Dependency sistem buat WeasyPrint (generate PDF Berita Acara).
# Tanpa ini, `pip install weasyprint` bakal jalan tapi importnya bakal error
# pas runtime (libpango/libcairo gak ketemu).
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
