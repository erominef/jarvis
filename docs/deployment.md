# Deployment

## Overview

The agent runs as a Docker container on the Ubuntu PC. The Mac is the development machine — files are edited on Mac, deployed via rsync + SSH.

**Mac = source of truth. Never edit files on the server directly.**

---

## Deploy Workflow

```bash
# 1. Rsync source (excluding node_modules, dist, .git)
rsync -av --exclude='.git' --exclude='node_modules' --exclude='dist' \
  ./jarvis/ user@server:~/jarvis/

# 2. Build and restart container
ssh user@server "cd ~/jarvis && npm run build && docker compose up -d --build"
```

One command. Container restarts in ~15 seconds.

---

## Docker Compose

```yaml
services:
  jarvis:
    build: .
    network_mode: host          # direct localhost access to Ollama
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./workspace:/app/workspace   # persistent memory files
```

`network_mode: host` is deliberate — it means `localhost` inside the container IS the host machine's localhost, giving direct zero-hop access to Ollama without any port forwarding or NAT.

---

## Environment Variables

See `templates/env.example` for the full list. Required at minimum:

| Variable | Purpose |
|---------|---------|
| `OLLAMA_PC_URL` | Primary Ollama endpoint |
| `OLLAMA_XEON_URL` | Heavy reasoning Ollama endpoint |
| `TELEGRAM_BOT_TOKEN` | grammY bot token |
| `TELEGRAM_OWNER_ID` | Allowlisted Telegram user ID |
| `MCP_MONTEGALLO_URL` | Knowledge base MCP SSE endpoint |
| `MCP_MONTEGALLO_TOKEN` | Knowledge base auth token |

---

## Multi-Machine Setup

The system spans two physical machines connected via Tailscale VPN:

```
Mac (dev)
  │
  └── rsync/SSH ──▶ Ubuntu PC (openclaw@)
                        │
                        ├── Docker container (Jarvis agent)
                        ├── Ollama :11434 (fast models)
                        └── HTTP ──▶ Xeon :11434 (heavy models)
```

**SSH to Xeon:** Direct SSH from Mac to Xeon doesn't work due to Tailscale ACL policy. Must proxy through Ubuntu PC:

```bash
ssh user@ubuntu-pc "ssh user@xeon-ip '<command>'"
```

For model pulls and benchmarks on Xeon, use the Ollama HTTP API via the Ubuntu relay (not SSH):

```bash
ssh user@ubuntu-pc "curl -s http://xeon-ip:11434/api/pull -d '{\"name\":\"model\"}'"
```

---

## Startup Validation

On container start, `src/config/validate.ts` pings both Ollama endpoints and verifies all 6 routing tiers have a reachable model. If any tier fails, the process exits with a clear error message before the bot comes online.

This prevents silent degradation where the bot starts but some routing paths silently fail.

---

## Ollama Configuration (Ubuntu PC)

Systemd service override at `/etc/systemd/system/ollama.service.d/override.conf`:

```ini
[Service]
Environment="OLLAMA_MAX_LOADED_MODELS=3"
Environment="OLLAMA_NUM_THREADS=8"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KEEP_ALIVE=30m"
```

`OLLAMA_MAX_LOADED_MODELS=3` keeps qwen3:0.6b + qwen3:4b + qwen2.5:7b simultaneously resident — the three most-used models never need a cold load.

**Vulkan is disabled on this machine.** The integrated GPU (Intel HD 530) loads models successfully but crashes mid-inference with `vk::DeviceLostError`. Do not re-enable.
