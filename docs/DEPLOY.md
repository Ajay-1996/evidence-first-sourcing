# Hosting the live link (Render, free tier)

The container serves everything from one process: the React app at `/`, the fallback UI at
`/shell`, and the API. On a server the agents run on the raw Anthropic API
(`FORCE_PROVIDER=anthropic` is set in the Dockerfile), so the console key needs a few
dollars of credits. The repo ships with the demo event pre-processed, so the hosted link
shows the full comparison instantly — live Process / decisions / analyst work once the key
is set.

## One-time steps (~10 min)

1. Push this repo to GitHub:
   ```bash
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
2. On render.com → **New → Web Service** → connect the repo.
   - Runtime: **Docker** (it auto-detects the Dockerfile). Instance: **Free**.
3. Environment variables:
   - `ANTHROPIC_API_KEY` = your fresh console key
   - `ANTHROPIC_WORKSPACE_ID` = `wrkspc_…` (only if the key is identity-linked)
4. Deploy. The URL Render gives you (`https://<name>.onrender.com`) is the live link.

## Verify after deploy

- `https://<name>.onrender.com/` → the app, comparison already populated
- `/health` → `key_present: true`, all four agents `provider: anthropic`
- Ask the analyst one question → confirms live loops work on the API

## Known free-tier behaviours (say them, don't hide them)

- Cold start: the free instance sleeps after idle; first visit takes ~60 s to wake.
- Ephemeral disk: decisions made on the hosted demo reset on redeploy/restart — the event
  returns to its staged state. For a reviewer demo this is a feature, not a bug.
- Each live Process/analyst click costs a few cents of API credit on your key.

## Alternative (no cloud account): tunnel your laptop

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8014
```

Gives a public URL to the locally-served build (Max plan, no API credits) — but it only
lives while your Mac is awake, so it is NOT suitable as the submitted link.
