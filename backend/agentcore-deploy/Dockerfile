FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 \
    AWS_REGION=us-east-1 \
    AWS_DEFAULT_REGION=us-east-1 \
    AGENT_MODULE=agent_template

# Install dependencies
COPY requirements.txt .
RUN uv pip install -r requirements.txt

# Install observability
RUN uv pip install aws-opentelemetry-distro>=0.10.0

# Create non-root user
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 9000
EXPOSE 8000
EXPOSE 8080

# Copy all source code
COPY . .

# Use AGENT_MODULE env var to select which agent to run
CMD opentelemetry-instrument python -m $AGENT_MODULE
