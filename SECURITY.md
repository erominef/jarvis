# Security Policy

## What's in this repo

This repository contains **sanitized documentation and reference code only**.

- No API keys, tokens, or credentials of any kind
- No real IP addresses or hostnames
- No production configuration files
- All `.env` examples use clearly fake placeholder values

## If you find a real secret

This repository should contain no real credentials. If you find something that looks like a real API key, token, or password, please open an issue immediately so it can be rotated.

## Production security posture (for reference)

The production system this case study documents uses:

- SSH key-only authentication (password auth disabled)
- UFW firewall — SSH restricted to VPN subnet only
- Tailscale for all inter-machine communication (no open ports to internet)
- fail2ban on all SSH-exposed surfaces
- Docker with non-root user
- No cloud inference — all LLM traffic stays on-premise

## Threat model

Primary concern is the Telegram bot surface (public internet). Mitigation: owner-only allowlist checked on every message before any tool execution.

Shell tool (`shell_run`) is restricted to an explicit command allowlist — arbitrary shell execution is not exposed to the agent.
