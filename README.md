# higgsfield-plugin

Claude Code plugin + `higgsfield` CLI for the [Higgsfield API](https://docs.higgsfield.ai):
text-to-image (SOUL 2), text-to-video and image-to-video (Seedance 2.0). Polish docs: `README_PL.md`.

```powershell
uv tool install --editable .
higgsfield setup --output-dir .\output   # stores key ID + secret in ~/.higgsfield/config.json
higgsfield check                         # validates credentials + estimates each endpoint (no credits)
higgsfield video "A cinematic tracking shot along a sunlit coastal road" --duration 5
higgsfield image "Editorial portrait in soft daylight" --aspect-ratio 3:4
higgsfield animate ./photo.jpg --prompt "gentle wind"
```

Credentials: `HF_API_KEY_ID` / `HF_API_KEY_SECRET` env vars or `~/.higgsfield/config.json`
(never in the repo). Generation POSTs are sent exactly once (no idempotency key upstream);
status polling uses 2 s × 1.5 backoff capped at 10 s with jitter and a deadline; a local
ledger (`~/.higgsfield/jobs.json`) tracks request IDs, blocks duplicate submissions and
restricts `status/wait/cancel` to requests created by this tool. Results are downloaded
without credentials to `output_dir`.

Tests: `python -m pytest -q` (offline, real SDK over `httpx.MockTransport`).
