FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source
COPY app/ .

# Copy the contract source (needed for compilation via py-solc-x)
COPY contracts/ /app/contracts/

# Copy sample credential claims for demo scenarios
COPY samples/ /app/samples/

ENTRYPOINT ["python", "cli.py"]