# VoidCrypt

Privacy-first AI proxy. Encrypt PII before it leaves your infrastructure.

VoidCrypt sits between your AI clients (Claude Code, Cursor, OpenAI SDK, etc.) and any LLM API provider. It automatically detects and encrypts sensitive data (names, emails, SSNs, API keys) using AES-256-GCM, ensuring providers never see your real data.

## Features

- AES-256-GCM encryption for all detected PII
- Semantic tokens like `{namep1}`, `{email_1}` preserve context for AI quality
- Works transparently - responses restored automatically
- Mappings API to see exactly what was encrypted
- Three privacy levels: paranoid, smart, minimal
- Vision support for multimodal messages
- Optional Tor support for IP anonymization
- Zero-log upstream AI (coming soon)
- High-performance private inference (coming soon)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env

# Generate your vault key
python3 voidcrypt.py --init

# Add your API key to .env
# PROVIDER_API_KEY=sk-or-v1-...

# Start the proxy
python3 voidcrypt.py
```

## Usage

### OpenAI-Compatible Clients

```bash
# Set your client to use VoidCrypt
export OPENAI_API_BASE=http://localhost:8400/v1
export OPENAI_API_KEY=any-key

# Or with curl
curl http://localhost:8400/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{
    "model": "openrouter/auto",
    "messages": [{"role": "user", "content": "My name is Maria and SSN is 123-45-6789"}]
  }'
```

### Claude Native API

```bash
curl http://localhost:8400/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: dummy" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "My name is Maria"}]
  }'
```

### CLI Client

```bash
# Interactive chat through the proxy
python3 cli.py

# Or with custom model
python3 cli.py --model lumyxai_plus_v1 --no-stream
```

## Privacy Levels

| Level | What Gets Encrypted |
|-------|---------------------|
| paranoid | All detected PII: names, emails, phones, SSNs, addresses, IPs, UUIDs |
| smart | Critical only: SSNs, API keys, passwords, credit cards, phones, addresses (default) |
| minimal | Credentials only: API keys, passwords, tokens, secrets |

## How It Works

```
Client -> VoidCrypt -> API Provider -> LLM Model
   ^       (encrypts)   (sees only     (response)
   |                      {tokens})
   +---- (restores tokens) ----+
```

Example:
- You send: `"My name is Maria, email maria@test.com"`
- Provider sees: `"My name is {namep1}, email {email_1}"`
- You receive: Original message with `_voidcrypt.mappings`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI-compatible chat |
| `/v1/messages` | POST | Claude API compatible |
| `/v1/models` | GET | List available models |
| `/v1/mappings` | GET | Current token -> original mappings |
| `/v1/vault/stats` | GET | Encryption statistics |
| `/v1/vault/clear` | POST | Clear session mappings |
| `/v1/level` | POST | Change privacy level |
| `/health` | GET | Health check |

## Response Format

```json
{
  "choices": [{"message": {"content": "Hello Maria, ..."}}],
  "_voidcrypt": {
    "request_id": "abc12345",
    "entities_redacted": 2,
    "level": "smart",
    "privacy": "protected",
    "mappings": {
      "{namep1}": "Maria",
      "{email_1}": "maria@test.com"
    }
  }
}
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VOIDCRYPT_KEY` | Yes | - | Run `--init` to generate |
| `PROVIDER_API_KEY` | Yes | - | Your upstream API key |
| `UPSTREAM_PROVIDER_ENDPOINT` | No | `https://lumyx-ai.site/api` | Upstream API URL |
| `VOIDCRYPT_PORT` | No | `8400` | Local proxy port |
| `VOIDCRYPT_LEVEL` | No | `smart` | Privacy level |
| `VOIDCRYPT_TOR_PROXY` | No | - | Tor SOCKS5h proxy |
| `VOIDCRYPT_ANONYMOUS` | No | `false` | Disable audit logs |
| `VOIDCRYPT_OBFUSCATE` | No | `false` | Inject decoy noise |

## Docker

```bash
docker-compose up -d
```

## Security

- Your vault key never leaves your machine
- Encryption happens locally before data is sent upstream
- Session-based: tokens expire when session clears
- No external services or third-party calls

## Testing

```bash
# Run test suite
python3 -m pytest tests/tests.py -v

# Test with running server
curl http://localhost:8400/health
```

## Updates

```bash
# Update to latest version (preserves .env and vault files)
./update.sh
```

**Note:** If you've made custom changes to core files (voidcrypt.py, cli.py, etc.), those changes will be overwritten by the update. Your backup will be saved to `.voidcrypt_backup_TIMESTAMP/` so you can restore them manually if needed.

## Roadmap

We're actively improving VoidCrypt based on community feedback:

- **Zero-Log Private AI** - A dedicated upstream that doesn't log requests. Free access via the Nabzclan Developer Program (based on project feedback)
- **Fast Local Inference** - High-performance private inference layer to prevent any data leaks
- **Control Panel** - Web UI for managing vault, viewing mappings, and configuring privacy levels
- **Enterprise Scale** - Support for high-volume requests and framework integrations (maybe)
- **Additional Entity Types** - More PII detection patterns based on user needs
- **CLI Enhancements** - Richer interactive features and better tooling

## License

MIT License - Copyright (c) 2026 Nabzclan

---

Built by Nabzclan
