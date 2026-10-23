# Server setup (one-time) — plan A14.1

Owner runs or approves each step. Do not paste secrets into chat or git.

1. **Elastic IP** — AWS console `ap-southeast-2`: confirm EC2 has an Elastic IP (or allocate one). Record it as `EXPECTED_STATIC_IP` in server `.env`.
2. **Tailscale** — install on the EC2; owner logs in. Portal via `tailscale serve 8090` (bind stays `127.0.0.1:8090`).
3. **Clone** — `/home/ubuntu/nse-engine`, create `.venv`, `pip install -r requirements.txt`.
4. **`.env`** — owner types secrets on the server only; `chmod 600 .env`.
5. **systemd** — copy `deploy/nse-engine.service` to `/etc/systemd/system/`, then `systemctl enable --now nse-engine`.
6. **GitHub secrets** — `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY` (deploy key for this repo only).
7. **Angel SmartAPI app** — static IP = Elastic IP; TOTP enabled (plan A3).

Working directory in the unit file is `/home/ubuntu/nse-engine`. If the clone path differs, edit the unit before enabling.

## Nginx reverse proxy (portal HTTPS gate — review R3)

App binds `127.0.0.1:8090`. Set `TRUSTED_PROXY=true` in server `.env` so the portal trusts
proxy headers **only** from that loopback peer. Nginx must forward real client IP and scheme:

```nginx
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

Without `X-Forwarded-Proto: https`, `/api/keys/*` returns 403. Do not set `TRUSTED_PROXY`
when clients talk to the app directly (local pytest / Tailscale serve without nginx).
