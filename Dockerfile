FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=core.settings
ENV PORT=7860

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
RUN chown -R user:user /app

COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user:user . .

USER user

EXPOSE 7860

# collectstatic بقى هنا في وقت التشغيل، بعد ما الـ Secrets تبقى متاحة
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate && python manage.py createsuperuser --noinput || true && daphne -b 0.0.0.0 -p 7860 core.asgi:application"]