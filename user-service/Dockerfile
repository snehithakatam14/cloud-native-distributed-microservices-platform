# python:3.11-slim is the minimal Debian-based Python image.
# 'slim' removes dev tools, docs, and unnecessary packages.
# Smaller images = faster pulls, smaller attack surface, less storage.
FROM python:3.11-slim

WORKDIR /app

# Copy requirements FIRST, then source code.
# Docker builds in layers. If requirements.txt hasn't changed,
# Docker uses the cached pip install layer — much faster rebuilds.
# If we copied all source first, any code change would re-run pip install.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

# 0.0.0.0 binds to all network interfaces inside the container.
# Without this, the service only listens on localhost and Docker
# networking can't route external traffic to it.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
