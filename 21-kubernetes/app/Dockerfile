FROM python:3.12-slim

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app
RUN pip install --no-cache-dir redis==5.* pika==1.*
COPY app.py .

EXPOSE 8080
CMD ["python", "app.py"]
