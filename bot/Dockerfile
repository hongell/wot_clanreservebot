FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and bot code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .

# Run bot
CMD ["python", "bot.py"]
