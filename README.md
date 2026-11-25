# Private Network Service Platform — Computer Networks project

Three MacBooks on a campus LAN form a small private "internet service": private DNS, two Python backends, an nginx HTTPS reverse proxy that load-balances them, caching headers, and packet captures. Phase 2 then stresses it with failures and recovery.

| Machine | Owner | Role |
|---|---|---|
| Mac 1 | Sushant | primary DNS (`dnsmasq`), Backend B |
| Mac 2 | Harshil | nginx HTTPS edge, test client |
| Mac 3 | Piyush | Backend A; Phase 2: backup DNS and standby edge |

## What we demonstrate

**Phase 1 — build the platform**
- Private LAN reachability (ping between all Macs)
- Private DNS: `app.teamX.test` / `api.teamX.test` → the edge, via `dnsmasq`
- Two HTTP backends (`backend/backend.py`) identifying themselves with `X-Backend: A|B`
- nginx reverse proxy with round-robin load balancing
- HTTPS with a locally trusted mkcert certificate (TLS 1.3 seen in Wireshark)
- HTTP caching: `Cache-Control`, `ETag`, conditional `304 Not Modified`
- Wireshark captures of DNS and TCP/TLS traffic

**Phase 2 — make it resilient** (details: [`phase2/README.md`](phase2/README.md))
- A: backup DNS server, resolution survives primary outage
- B: DNS TTL and a controlled record change with rollback
- C: backend isolation with macOS `pf`
- D: backend failover through nginx passive health handling
- E: standby nginx edge and DNS-based migration
- F: troubleshooting runbook (prepared)

## Request path

```
client -> DNS (dnsmasq) -> nginx :8443 (TLS) -> Backend A (:3001) | Backend B (:3002)
```

## Repository map

```
backend/        backend.py - shared by both phases (--backend A|B --port N)
configs/        Phase 1 dnsmasq / nginx examples
docs/           Phase 1 IP and service table
evidence/       Phase 1 screenshots, numbered 01-lan ... 08-failures
tls/            TLS notes (never commit private keys)
phase2/         Phase 2: README/report, configs, docs, evidence per extension
```

## Run it

```bash
python3 backend/backend.py --backend A --port 3001     # Mac 3
python3 backend/backend.py --backend B --port 3002     # Mac 1
# dnsmasq on Mac 1 from configs/, nginx on Mac 2 from configs/ with a trusted cert, then:
curl -i https://app.teamX.test:8443/api/status         # 200, X-Backend: A or B
```

Phase 2 uses the names `app.team1.test` / `api.team1.test` and different DHCP addresses; see [`phase2/docs/ip-service-table.md`](phase2/docs/ip-service-table.md). Always verify IPs with `ipconfig getifaddr en0` before rerunning.

## Phase 1 summary

#

Open items from Phase 1: live `dnsmasq.conf` capture, `dig @8.8.8.8` output, and the original topology/pcap artifacts are not in the repo.

## Phase 2 summary

Extensions A–E were run on 23 Nov 2026 and are evidenced in `phase2/evidence/`. F is a prepared runbook. Limitations (including PF enable tokens not released, a Mac 3 dnsmasq config error during the cutover, and no captured restore step for E) are listed in [`phase2/README.md`](phase2/README.md#4-limitations-and-follow-ups).

## Security note

Never commit TLS private keys or the mkcert root key. `tls/app.teamX.test+1-key.pem` is currently tracked from Phase 1 and should be removed and the certificate rotated.
