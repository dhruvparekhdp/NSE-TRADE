# Reaching the portal

The engine listens on `127.0.0.1:8090` by default. That is the only safe bind.
`WEB_HOST` may name another address only when `EXPOSE_HTTP=true`. Without that
flag the process refuses to start, so a copied config cannot open the port on
`0.0.0.0` by accident.

Do not publish this port on the internet. Do not put plain HTTP on a public
address. The cookie and the admin token are not a substitute for a private
network.

## Ways in

Use one of these:

1. **Tailscale or WireGuard.** Join the box to the tailnet (or the VPN) and
   open `http://<tailscale-ip>:8090/` from a machine on that network. The
   listener can stay on localhost and you can `ssh -L 8090:127.0.0.1:8090` to
   the box. A Tailscale address (`100.64.0.0/10`) is treated as a private
   channel for key writes.
2. **A reverse proxy with HTTPS.** nginx (or Caddy) terminates TLS and proxies
   to `127.0.0.1:8090`. Set `X-Forwarded-Proto: https`. Keep `COOKIE_SECURE`
   at its default (`true`) so the session cookie is not sent over plain HTTP.

Leave `EXPOSE_HTTP` unset or `false` unless you have a reason to bind a
non-loopback address. Binding `0.0.0.0` still requires the proxy or the VPN in
front of it. Never forward port 8090 from the public firewall.

## Who may call admin routes

Admin routes (kill switch, keys, settings, tables, books, today, strategies,
quote refresh, universe edits, and `/keys`) answer `401` until one of these
checks passes:

- `POST /api/login` with the portal password. The compare is constant-time.
  Five failures in ten minutes return `429`.
- The `nse_session` cookie from that login.
- `Authorization: Bearer` matching `ADMIN_TOKEN`, also compared in constant time.

`GET /api/health` and `POST /api/login` stay open so a local probe and the
login form work. Health returns status only. It does not return secrets.

Market read APIs stay available on the localhost bind. They are not the admin
surface. Do not rely on that as a reason to open the port.
