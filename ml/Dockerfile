FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8001
# Un solo worker: el modelo se entrena una vez al arrancar y vive en memoria
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
