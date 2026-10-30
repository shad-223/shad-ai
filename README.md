# shad-ai

A self-hosted FastAPI app combining a personal API-key vault with lightweight content-generation tools, running behind a Cloudflare Tunnel at `shad.bpda.site`.

## Features

- **Key Vault** — master-password-gated, Fernet-encrypted store for third-party API keys (`vault.py`), with one key per provider marked "active" at a time (no rotation/failover, by design).
- **Graphics Studio** (`graphics.py`) — generates banners, posters, and ID cards at SVG/Canvas quality.
- **Reel/Video Generator** (`video.py`) — script + TTS (via the vault's ElevenLabs key) + Ken Burns pans + captions. Generate-only: no Facebook or other social-platform tokens are ever requested or stored.
- **Downloads** — a unified library view over everything the app has generated.

## Stack

FastAPI, server-side session auth (`auth.py`), SQLite + Fernet for the vault, Playwright/Pillow for rendering, Docker Compose for deployment.

## Running it

```bash
cp .env.example .env   # fill in SHAD_MASTER_PASSWORD_HASH and SHAD_VAULT_SECRET
docker compose up -d
```

The app listens on `127.0.0.1:8150` and expects to sit behind a reverse proxy / tunnel.
