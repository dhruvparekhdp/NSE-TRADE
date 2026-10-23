# Runbook (skeleton — expand as errors are seen)

## Login fails (08:45)

1. Check Telegram for the login alert.
2. Confirm TOTP secret / MPIN on the server `.env` (never in chat).
3. Fallback: reply `/totp 123456` from the owner chat id (wired in P4).
4. Retries: 08:50, 08:55 (plan A12.1).

## WebSocket drops

- Engine reconnects with backoff 1, 2, 5, 10, 30 s (P1).
- If no tick for 30 s in market hours: pause new entries; alert after 60 s.

## Kill switch

- Portal Settings, `POST /api/kill`, Telegram `/kill`, capital floor, static-IP mismatch, parity faults.
- Open positions keep exchange stops; no new entries.

## Broker outage / AB1021

- Reads: backoff and retry (max 5).
- Orders: rejections are not retried; alert immediately.
- Log full message without tokens; append unknown codes here.

## Deploy during market hours

- Blocked Mon–Fri 09:00–15:45 IST unless workflow_dispatch `force=true`.
