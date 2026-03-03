FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy dependency files and README (required by hatchling build)
COPY pyproject.toml ./
COPY uv.lock* ./
COPY README.md ./

# Install dependencies using uv (allow pre-release for fastmcp)
# --no-install-project installs only deps first for better layer caching
RUN uv sync --frozen --prerelease=allow --no-install-project

# Copy application code
COPY . ./

# Install the project itself
RUN uv sync --frozen --prerelease=allow

# Install Playwright browsers (Chromium only for notebooklm automation)
RUN uv run playwright install chromium --with-deps

ENV BASE_DATA_DIR=/data

VOLUME ["/data"]

EXPOSE 8000

# Run the MCP server using uv
CMD ["uv", "run", "--prerelease=allow", "notebooklm-mcp", \
     "--transport", "http", "--multi-tenant", "--host", "0.0.0.0", "--port", "8000"]
