FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py .

RUN chmod +x monitor.py

USER nobody

CMD ["python", "monitor.py"]
