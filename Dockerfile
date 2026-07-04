# Use Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=core.settings
ENV PORT=7860 

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# create a non-root user for Hugging Face
RUN useradd -m -u 1000 user
RUN chown -R user:user /app

# Install Python dependencies
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY --chown=user:user . .

# Switch to non-root user
USER user

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port 7860
EXPOSE 7860

# تشغيل الـ Migrations، وإنشاء السوبر يوزر بأمان، ثم تشغيل السيرفر
CMD ["sh", "-c", "python manage.py migrate && python manage.py createsuperuser --noinput || true && daphne -b 0.0.0.0 -p 7860 core.asgi:application"]