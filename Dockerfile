FROM python:3.10-slim

# Install system compilation packages for tgcrypto (C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set up a new user named "user" with UID 1000 (required by Hugging Face Spaces)
RUN useradd -m -u 1000 user

WORKDIR /app

# Copy dependency specifications and install them globally
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt tgcrypto

# Copy application files and change ownership to the non-root user
COPY --chown=user:user . .

# Switch to the non-root user
USER user

# Expose port (Hugging Face Spaces runs on 7860)
EXPOSE 7860

# Command to run the addon dynamically reading the PORT environment variable
CMD ["sh", "-c", "uvicorn addon:app --host 0.0.0.0 --port ${PORT:-7860}"]
