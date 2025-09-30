# Splunk AI Agent

A production-ready FastAPI service that converts natural language questions into Splunk SPL queries using Azure OpenAI, executes them against Splunk, and returns structured results with an LLM-generated summary.

## Features

- REST API built with FastAPI and Uvicorn
- Azure OpenAI integration for SPL generation and result summarization
- Splunk REST API integration for executing SPL searches
- Dockerized deployment and GitHub Actions workflow for automated builds and pushes

## Getting Started

### Prerequisites

- Python 3.10+
- Access to Azure OpenAI (endpoint, API key, deployment name)
- Splunk instance with REST API access

### Setup

1. Clone the repository and navigate into the project directory.
2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and populate it with your Azure OpenAI and Splunk credentials.
4. Run the API locally using Uvicorn:

   ```bash
   uvicorn app.main:app --reload
   ```

5. Access the interactive docs at [http://localhost:8000/docs](http://localhost:8000/docs).

### Example Request

```bash
curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question":"Show failed logins last 24h"}'
```

To temporarily target a different Splunk instance without editing `.env`, supply the
`splunk_host` field in the request body:

```bash
curl -X POST http://localhost:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question":"Show failed logins last 24h","splunk_host":"splunk.backup.local"}'
```

### Docker

Build and run the Docker image locally:

```bash
docker build -t splunk-ai-agent:latest .
docker run --rm -p 8000:8000 --env-file .env splunk-ai-agent:latest
```

### Troubleshooting Splunk Connectivity

If the `/ask` endpoint returns a `502` error with the message `Failed to communicate with Splunk API`, use the following steps to debug:

1. **Enable debug logging**

   Set `LOG_LEVEL=DEBUG` in your environment before starting the app. This prints the exact Splunk endpoint that is being called.

2. **Validate credentials and network access**

   Use `curl` or `requests` from the same machine running the FastAPI service to ensure you can reach the Splunk management port:

   ```bash
   curl -k -u "$SPLUNK_USERNAME:$SPLUNK_PASSWORD" \
        "$SPLUNK_SCHEME://$SPLUNK_HOST:$SPLUNK_PORT/services/server/info"
   ```

   A successful response returns XML describing the Splunk server. If the command times out or fails, check firewall rules or VPN connectivity.

3. **Check SSL settings**

   The app honours the `SPLUNK_VERIFY_SSL` flag. Set it to `false` when Splunk uses self-signed certificates. When the certificate chain is valid, keep it as `true` to avoid MITM issues.

4. **Confirm Splunk REST API availability**

   Make sure the Splunk instance has the REST API enabled and that the user has the `search` capability. Refer to the Splunk docs for enabling the management port (default `8089`).

### Manual Azure Container Registry Push

```bash
az acr login --name <your-acr-name>
docker tag splunk-ai-agent:latest <acr_login_server>/splunk-ai-agent:latest
docker push <acr_login_server>/splunk-ai-agent:latest
```

## GitHub Actions CI/CD

The repository includes a GitHub Actions workflow that builds the Docker image and pushes it to Azure Container Registry on every push to the `main` branch.

Required repository secrets:

- `AZURE_CREDENTIALS`: Service principal credentials in JSON format for `az login`.
- `ACR_NAME`: Name of the Azure Container Registry.
- `ACR_LOGIN_SERVER`: Login server of the Azure Container Registry (e.g., `myregistry.azurecr.io`).

Workflow steps:

1. Check out the repository.
2. Log in to Azure using the provided service principal credentials.
3. Build the Docker image.
4. Tag and push the image to the specified Azure Container Registry.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | – |
| `AZURE_OPENAI_KEY` | Azure OpenAI API key | – |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI deployment name | `gpt-35-turbo` |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version | `2024-02-15-preview` |
| `SPLUNK_HOST` | Splunk host (can be overridden per request via `splunk_host`) | – |
| `SPLUNK_PORT` | Splunk management port | `8089` |
| `SPLUNK_USERNAME` | Splunk username | – |
| `SPLUNK_PASSWORD` | Splunk password | – |
| `SPLUNK_SCHEME` | Protocol to reach Splunk (`http` or `https`) | `https` |
| `SPLUNK_VERIFY_SSL` | Whether to verify Splunk SSL certificates | `true` |
| `SPLUNK_REQUEST_TIMEOUT` | Timeout (seconds) for Splunk API requests | `60` |

## API Reference

- `GET /health` → `{ "status": "ok" }`
- `POST /ask` → `{ "question": "...", "splunk_host": "...", "spl_query": "...", "results": [...], "summary": "..." }`

---

Built with ❤️ using FastAPI, Azure OpenAI, and Splunk.
