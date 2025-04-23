# Use Python 3.13 base image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Expose port for Cloud Run
EXPOSE 8080

# Command to run the app (adjust if using Flask/Django)
CMD ["python", "main.py"]
