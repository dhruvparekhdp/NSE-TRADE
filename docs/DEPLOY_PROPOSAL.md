# Deploy proposal — non-git `~/nse-engine` (V-NEXT N6)

**Status:** owner approval required before any production change. **Do not type keys until HTTPS or Tailscale is in place** (review R3 / `TRUSTED_PROXY`).

## Problem

`.github/workflows/deploy.yml` runs `git pull --ff-only` in `~/nse-engine`, but the server directory is **not a git checkout** (confirmed in `docs/reviews/REVIEW_V0-V6.md` §3). Deploys fail at pull; manual copies drift from CI-tested `main`.

## Recommended safe deploy (Option A — rsync artifact)

1. **CI job** (after tests on `main`):
   - `git archive` or `rsync --exclude .git` to a versioned tarball `nse-engine-${GITHUB_SHA}.tar.gz`.
   - Upload as a workflow artifact (or S3 if owner adds bucket later).
2. **Deploy job** (still blocked Mon–Fri 09:00–15:45 IST unless `workflow_dispatch` + `force`):
   - SSH to EC2.
   - Extract to `~/nse-engine/releases/${SHA}/`.
   - Atomically repoint `~/nse-engine/current` symlink.
   - `current/.venv/bin/pip install -r requirements.txt` (reuse existing venv path or one venv per release).
   - `sudo systemctl restart nse-engine`.
   - Health: `curl -fsS http://127.0.0.1:8090/api/health` (expect `book_b_slot_ok: true`).
3. **Rollback:** `ln -sfn ~/nse-engine/releases/<previous-sha> ~/nse-engine/current && sudo systemctl restart nse-engine`.

## Network / keys (before go-live)

| Step | Action |
|---|---|
| TLS | nginx `443` with real cert **or** Tailscale only (no public `:8090`) |
| Proxy | `proxy_set_header X-Real-IP $remote_addr;` and `X-Forwarded-Proto $scheme;` |
| App | `TRUSTED_PROXY=true` in `.env` **only** when nginx terminates TLS on loopback |
| Keys | Use `/keys` reveal only over HTTPS/Tailscale; never expose plain HTTP to the internet |

## Option B — convert server to git checkout (owner-maintained)

If the owner prefers `git pull`:

```bash
cd ~
mv nse-engine nse-engine.bak.$(date +%Y%m%d)
git clone git@github.com:dhruvparekhdp/NSE-TRADE.git nse-engine
cd nse-engine && git checkout main
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# copy .env from backup — never commit
sudo systemctl restart nse-engine
```

Requires deploy key on the server and a one-time `.env` migration.

## What not to do

- Do not `git init` inside the live tree without moving `.env` and `data/` aside (risk of overwriting local DB).
- Do not enable `live_orders` or change `mode` during deploy.
- Do not deploy during market hours without explicit owner override.

## Suggested workflow patch (sketch)

Replace the SSH `git pull` block with:

```yaml
- name: Pack release
  run: tar czf /tmp/nse-engine.tgz --exclude=.git --exclude=var --exclude=.env .
- name: Upload and extract on server
  # appleboy/scp-action + ssh extract + symlink swap (owner adds secrets)
```

Owner approves which option (A vs B) before Cursor edits `deploy.yml` on a branch.
