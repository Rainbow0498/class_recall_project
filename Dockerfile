FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DEBUG=0
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data /app/staticfiles && DEBUG=1 python manage.py collectstatic --noinput && useradd --uid 10001 --create-home teacher && chown -R teacher:teacher /app && chmod 755 /app/deploy/entrypoint.sh
USER teacher
EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
