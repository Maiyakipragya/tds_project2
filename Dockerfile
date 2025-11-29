FROM python:3.10

WORKDIR /app

# Set browser path
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install system certificates to fix DNS/SSL issues
RUN apt-get update && apt-get install -y ca-certificates

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install browsers
RUN playwright install --with-deps chromium

COPY . .

# Setup user permissions (Required for Hugging Face)
RUN useradd -m -u 1000 user
RUN chown -R user:user /app
RUN chown -R user:user /ms-playwright

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
