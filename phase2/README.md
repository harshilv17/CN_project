# Phase 2 — Resilient private network service (three Macs)

**Course:** Computer Networks · **Team:** Sushant (Mac 1), Harshil (Mac 2), Piyush (Mac 3) · **Date of run:** 23 Nov 2026 (campus LAN `10.7.0.0/19`)

Phase 1 built a private, HTTPS-fronted, load-balanced service on three Macs. Phase 2 **breaks parts of it on purpose** and shows the platform keeps working, or recovers cleanly: DNS redundancy, DNS caching/TTL behaviour, backend isolation with a firewall, backend failover, and moving the HTTPS edge to a second machine.

- Backend code is unchanged from Phase 1: [`backend/backend.py`](backend/backend.py)
- Full command handbook (reconstructed from the session): [`docs/phase2-handbook.md`](docs/phase2-handbook.md)
- Machines/IPs: [`docs/ip-service-table.md`](docs/ip-service-table.md) · Configs: [`configs/`](configs/) · Troubleshooting runbook: [`docs/troubleshooting-runbook.md`](docs/troubleshooting-runbook.md)

---

## 1. What we set out to demonstrate

| # | Question | Mechanism | Verdict from evidence |
|---|---|---|---|
| A | Does name resolution survive losing the primary DNS server? | second `dnsmasq` on Mac 3, clients list both resolvers | **Shown** |
| B | What does a DNS record change look like to a client, and how does the TTL/cache matter? | `local-ttl=30`, repoint `api.team1.test`, flush cache, roll back | **Shown** (see caveat on caching) |
| C | Can backends be reachable *only* from the nginx edge? | macOS `pf` anchors on Mac 1 and Mac 3 | **Shown for Backend A**; Backend B rule loaded, block from Mac 3 not in the screenshots |
| D | Does the service survive a dead backend and heal afterward? | nginx passive failover (`max_fails`, `proxy_next_upstream`) | **Shown** |
| E | Can the HTTPS edge itself move to another machine? | standby nginx on Mac 3 + same cert + DNS cutover | **Shown for the cutover**; restore step not in the screenshots; backup-DNS update failed (see §4) |
| F | Can we diagnose a fault systematically? | layered runbook | **Prepared only** — no faculty-injected fault exercised |

## 2. Architecture

```
                 Private DNS (dnsmasq)
        primary Mac 1 10.7.27.143:53   backup Mac 3 10.7.26.181:53
                        |
          app.team1.test / api.team1.test
          normal -> 10.7.1.194      Ext E cutover -> 10.7.26.181
                        |
        Mac 2  nginx HTTPS :8443  (primary edge, TLS terminates here)
                 /                        \
   Mac 3 Backend A 10.7.26.181:3001   Mac 1 Backend B 10.7.27.143:3002

   Ext E: Mac 3 also runs a standby nginx :8443 -> A via 127.0.0.1:3001, B via 10.7.27.143:3002
```

Request path: client resolves the name (DNS) → TCP+TLS to nginx `:8443` → nginx picks A or B (round-robin) → backend returns `{"backend": "A|B", "status": "ok"}` with an `X-Backend` header.

## 3. Evidence layout

```
evidence/
  00-baseline/                    pings, IPs, backends, DNS, HTTPS, /cached 304 (before any change)
  extension-a-backup-dns/
  extension-b-dns-ttl/
  extension-c-service-isolation/
  extension-d-ha-failover/
  extension-e-edge-migration/
  extension-f-troubleshooting/    empty - not performed
```

Files are named `macN-owner-HHMMSS.png` (time in IST on 23 Nov 2026; `mac1`=Sushant, `mac2`=Harshil, `mac3`=Piyush). They were sorted from the three team archives by timestamp and content; three byte-identical duplicates were dropped. Captions below describe only what the screenshot visibly shows.

### Baseline (before Phase 2 changes)

| File | Shows |
|---|---|
| [`mac1-mac-1-ip.png`](evidence/00-baseline/mac1-mac-1-ip.png) | Mac 1 `en0` = `10.7.27.143`, mask `255.255.224.0`, router `10.7.0.1` |
| [`mac3-piyush-133706.png`](evidence/00-baseline/mac3-piyush-133706.png) | Mac 3 → Mac 1 ping **3/4 received (25 % loss)**; → Mac 2 4/4; DNS set to `10.7.27.143`; `dig app.team1.test` → `10.7.1.194` from `10.7.27.143#53` |
| [`mac3-piyush-140307.png`](evidence/00-baseline/mac3-piyush-140307.png) | `/api/status` over HTTPS returns 200, `X-Backend: A` |
| [`mac3-piyush-140401.png`](evidence/00-baseline/mac3-piyush-140401.png) | `/cached`: `Cache-Control: max-age=60`, `ETag`; `If-None-Match` → `304 Not Modified` |
| [`mac3-backenda-running.png`](evidence/00-baseline/mac3-backenda-running.png) | Backend A: `lsof` shows `*:3001 (LISTEN)`, local curl 200 `X-Backend: A` |
| [`mac1-sushant-134912.png`](evidence/00-baseline/mac1-sushant-134912.png) | Backend B: `*:3002 (LISTEN)`, local curl 200 `X-Backend: B` |
| [`mac1-sushant-131749.png`](evidence/00-baseline/mac1-sushant-131749.png) | `dig @10.7.27.143 app/api.teamX.test` → `10.7.1.194` (leftover Phase 1 name, TTL 0) |

Remaining files in the folder are the IP/ping captures for all three Macs and further terminal snapshots of the same checks.

### Extension A — backup DNS

**What we did.** Installed `dnsmasq` on Mac 3 listening on `127.0.0.1` and `10.7.26.181` with the same records ([`configs/dnsmasq-backup.conf.example`](configs/dnsmasq-backup.conf.example)); gave Mac 2 and Mac 3 both resolvers (`networksetup -setdnsservers Wi-Fi 10.7.27.143 10.7.26.181`); stopped dnsmasq on Mac 1; resolved and fetched HTTPS anyway; restarted Mac 1.

| File | Shows |
|---|---|
| [`mac3-piyush-141254.png`](evidence/extension-a-backup-dns/mac3-piyush-141254.png) | `dnsmasq --test` OK, service started; `lsof :53` → UDP/TCP on `10.7.26.181` and `127.0.0.1`; `dig` to both returns `10.7.1.194`, **TTL 30** |
| [`mac2-harshil-141719.png`](evidence/extension-a-backup-dns/mac2-harshil-141719.png) | `dig @10.7.27.143 … +time=1 +tries=1` → **connection timed out**; `dig @10.7.26.181` → `10.7.1.194`; after cache flush `dig app.team1.test` answered by `SERVER: 10.7.26.181` |
| [`mac1-sushant-141914.png`](evidence/extension-a-backup-dns/mac1-sushant-141914.png) / [`…142050.png`](evidence/extension-a-backup-dns/mac1-sushant-142050.png) | Mac 1: `brew services stop dnsmasq`, nothing on UDP 53; then started again, `dig @127.0.0.1` → `10.7.1.194` |
| [`mac1-sushant-141659.png`](evidence/extension-a-backup-dns/mac1-sushant-141659.png) | Mac 1 dnsmasq on `:53`; killing the PID makes launchd respawn it (hence `brew services stop` in the next shots); `dig @127.0.0.1` → `10.7.1.194`, TTL 0 |

**Takeaway.** A second resolver removes DNS as a single point of failure. It does **not** protect nginx or the backends. macOS resolver ordering is not a strict primary/secondary, so we queried each server directly with `dig @server` as well as through the system resolver.

### Extension B — TTL and a controlled record change

**What we did.** Set `local-ttl=30` on Mac 1 (before that, answers showed TTL 0 — see baseline), pinned Mac 2 to the primary only, changed only `api.team1.test` to `10.7.26.181`, observed it from the client, flushed the macOS cache, then restored `.194` and both resolvers ([`configs/dnsmasq-ttl-change.conf.example`](configs/dnsmasq-ttl-change.conf.example)).

| File | Shows |
|---|---|
| [`mac2-harshil-142222.png`](evidence/extension-b-dns-ttl/mac2-harshil-142222.png) | `dig @10.7.27.143 api.team1.test` → `30 IN A 10.7.1.194` (original) |
| [`mac2-harshil-142733.png`](evidence/extension-b-dns-ttl/mac2-harshil-142733.png) | Mac 2 DNS pinned to `10.7.27.143`; `dscacheutil` / Python resolve `.194`; then `dig` shows primary now answers **`10.7.26.181`** |
| [`mac2-harshil-143001.png`](evidence/extension-b-dns-ttl/mac2-harshil-143001.png) | Python resolves `10.7.26.181` before and after flush; resolvers restored (`networksetup -getdnsservers` → both); both servers back to `.194`; HTTPS 200 `X-Backend: A` |
| [`mac1-sushant-142417.png`](evidence/extension-b-dns-ttl/mac1-sushant-142417.png) | Mac 1: `cp dnsmasq.conf ~/dnsmasq-before-ttl.conf`; `grep` shows live `listen-address`, `address=` lines |
| [`mac1-sushant-143622.png`](evidence/extension-b-dns-ttl/mac1-sushant-143622.png) | Mac 1: edit, `dnsmasq --test` OK, service restarted |

**Takeaway / caveat.** The TTL bounds how long a resolver may keep an answer, so different clients can briefly disagree after a change. Our captures show the new answer arriving and the rollback working; they do **not** show a held cache entry expiring at exactly 30 s, and the post-flush answer alone does not prove the flush sped anything up.

### Extension C — backend isolation with `pf`

**What we did.** On Mac 1 (Backend B) and Mac 3 (Backend A) saved `/etc/pf.conf`, created anchor `cn_phase2` allowing only Mac 2 (`10.7.1.194`) to the backend port and blocking everyone else on `en0` ([`configs/firewall/`](configs/firewall/)), enabled PF, tested, rolled back.

| File | Shows |
|---|---|
| [`mac3-piyush-143511.png`](evidence/extension-c-service-isolation/mac3-piyush-143511.png) | Mac 3 `networksetup -getdnsservers` → both resolvers; `/etc/pf.conf` backed up; `en0` confirmed as Wi-Fi |
| [`mac3-piyush-143533.png`](evidence/extension-c-service-isolation/mac3-piyush-143533.png) | Mac 3 `pfctl -si` → **Status: Disabled** before; rules saved to `~/pf-rules-before-phase2.txt` |
| [`mac1-sushant-143830.png`](evidence/extension-c-service-isolation/mac1-sushant-143830.png) | Mac 1 `pfctl -E` → *pf enabled* + token; `pfctl -a cn_phase2 -sr` → pass from `10.7.1.194` to `…143 port 3002`, block from any |
| [`mac3-piyush-144313.png`](evidence/extension-c-service-isolation/mac3-piyush-144313.png) | Mac 3 `pfctl -E` + token; `-a cn_phase2 -sr` → pass `10.7.1.194` / `block drop … any to 10.7.26.181 port = 3001`; rollback attempt (`-X YOUR_SAVED_TOKEN` rejected) |
| [`mac1-sushant-144258.png`](evidence/extension-c-service-isolation/mac1-sushant-144258.png) | Mac 1 → Backend A: 200 *before* Mac 3's rule, then `curl: (28) Failed to connect to 10.7.26.181 port 3001 after 3006 ms: Timeout was reached` **after** — Mac 1 is blocked from A |
| [`mac2-harshil-144035.png`](evidence/extension-c-service-isolation/mac2-harshil-144035.png), [`…144127.png`](evidence/extension-c-service-isolation/mac2-harshil-144127.png) | Mac 2 (the allowed edge) reaches A directly on `:3001` (200, `X-Backend: A`), HTTPS via nginx returns B, and a 10-request loop alternates A/B |
| [`mac1-sushant-144314.png`](evidence/extension-c-service-isolation/mac1-sushant-144314.png) | Rollback: `/etc/pf.conf` restored, `pfctl -sr` back to Apple defaults, Mac 1 reaches A again (200) |
| [`mac3-piyush-145044.png`](evidence/extension-c-service-isolation/mac3-piyush-145044.png) | after rollback Mac 3 reaches local A and Mac 1's B (200) |
| [`mac2-harshil-144419.png`](evidence/extension-c-service-isolation/mac2-harshil-144419.png) | after rollback Mac 2 reaches A `:3001` and B `:3002` directly (200) |

**Takeaway.** A drop rule makes the blocked client see a **timeout**, not a refusal. DNS and the HTTPS edge kept working because only the backend ports were filtered.

### Extension D — backend failover

**What we did.** Edited Mac 2's nginx upstream to `max_fails=1 fail_timeout=5s` with `proxy_next_upstream error timeout http_502 http_503 http_504` ([`configs/nginx-primary.conf.example`](configs/nginx-primary.conf.example)); stopped only Backend A; ran 10 HTTPS requests; restarted A; ran 10 more.

| File | Shows |
|---|---|
| [`mac2-harshil-144526.png`](evidence/extension-d-ha-failover/mac2-harshil-144526.png) | `nano /opt/homebrew/etc/nginx/nginx.conf`, then a 10-request HTTPS loop alternating A/B (both backends up) |
| [`mac2-harshil-144617.png`](evidence/extension-d-ha-failover/mac2-harshil-144617.png) | Backend A stopped: 10 requests, every one `X-Backend: B` |
| [`mac2-harshil-144654.png`](evidence/extension-d-ha-failover/mac2-harshil-144654.png) | Verbose run: Request 1–10 each `HTTP/1.1 200 OK`, `X-Backend: B` — **no client-visible errors** with A down; after A restarted: `B B A B A B A B A B` — balancing resumes |

**Takeaway.** This is *passive* failover: nginx learns A is dead from a failed attempt and retries on B. It is not an active health check, and the single nginx edge is still a single point of failure → Extension E.

### Extension E — standby edge and DNS-based migration

**What we did.** Installed a second nginx on Mac 3 with a private prefix (`~/cn-standby`) and the same TLS certificate ([`configs/nginx-standby.conf.example`](configs/nginx-standby.conf.example), [`tls/tls-setup.md`](tls/tls-setup.md)); tested it with `curl --resolve` before touching DNS; repointed `app/api.team1.test` to `10.7.26.181` on Mac 1; pinned Mac 2 to Mac 1's DNS; fetched `https://app.team1.test:8443` with **no `-k` and no `--resolve`**; watched the standby access log.

| File | Shows |
|---|---|
| [`mac2-harshil-151359.png`](evidence/extension-e-edge-migration/mac2-harshil-151359.png) | `scp` to Mac 3 **failed** (`no such file or directory: Piyush` — wrong remote user), so the cert was AirDropped instead; `curl --resolve app.team1.test:8443:10.7.26.181` → 200 `X-Backend: A`, then `B` |
| [`mac2-harshil-151435.png`](evidence/extension-e-edge-migration/mac2-harshil-151435.png) | 8 requests via the standby (`--resolve …:10.7.26.181`) alternating A/B, then `--resolve …:10.7.1.194` (primary) A vs `…:10.7.26.181` (standby) A, B — trusted TLS both ways |
| [`mac2-harshil-152148.png`](evidence/extension-e-edge-migration/mac2-harshil-152148.png) | Both DNS servers still answer `.194`; Mac 2 pinned to `10.7.27.143`; primary now answers **`10.7.26.181`** (cutover applied on Mac 1) |
| [`mac2-harshil-152219.png`](evidence/extension-e-edge-migration/mac2-harshil-152219.png), [`…152248.png`](evidence/extension-e-edge-migration/mac2-harshil-152248.png) | After flush, Python resolves `app.team1.test` → **`10.7.26.181`**; plain `curl https://app.team1.test:8443/api/status` (no `-k`, no `--resolve`) → 200; 10-request loop alternates A/B |
| [`mac3-piyush-152239.png`](evidence/extension-e-edge-migration/mac3-piyush-152239.png) | `tail -f ~/cn-standby/logs/access.log`: `10.7.1.194 … GET /api/status 200 … curl/8.7.1` — **the standby served the client's requests**; also the Mac 3 dnsmasq problems noted in §4 |

**Takeaway.** The certificate authenticates the *hostname*, so it works unchanged on the standby once DNS points there. The cutover is **manual** and subject to resolver caches — this is controlled migration, not automatic zero-downtime failover.

### Extension F — troubleshooting

Not performed. The layered method is in [`docs/troubleshooting-runbook.md`](docs/troubleshooting-runbook.md); `evidence/extension-f-troubleshooting/` is empty on purpose.

## 4. Known gaps and things to fix before submitting

Found while reading the screenshots; these are real, not hypothetical.

1. **PF may still be enabled on Mac 1 and Mac 3.** Both ran `pfctl -E` (tokens `15615191004642521571` on Mac 1, `10469740470778522208` on Mac 3) and the rollback ran `pfctl -X YOUR_SAVED_TOKEN` — the *literal placeholder* — which pfctl rejected (`Invalid token value`). Rules were restored but the enable reference was never released. Fix: `sudo pfctl -X <token>` on each Mac, then `sudo pfctl -si`.
2. **Mac 3 backup dnsmasq failed during Extension E.** [`mac3-piyush-152239.png`](evidence/extension-e-edge-migration/mac3-piyush-152239.png) shows `dnsmasq: bad option at line 518 of /opt/homebrew/etc/dnsmasq.conf` and `dig @10.7.26.181 …` ending in *connection timed out*. Cutover still worked only because Mac 2 was pinned to Mac 1. So the backup DNS was **not** shown consistent with the primary during migration. Re-run with a fixed config if the rubric needs both servers updated.
3. **No restore evidence for Extension E.** The zips contain nothing after the cutover (DNS back to `.194`, primary nginx restart, standby stop). The handbook describes a restore screenshot from the chat that is not in the archives.
4. **Backend B isolation (Mac 3 → B blocked) is not in the screenshots reviewed;** only the rule listing and Mac 2's allowed access are.
5. **Ping loss:** Mac 3 → Mac 1 showed 25 % loss (3/4) in the baseline capture; Mac 3 → Mac 2 was 4/4.
6. **Phase 1 repo hygiene:** `tls/app.teamX.test+1-key.pem` (a private key) is committed in the top-level `tls/` folder. `.gitignore` only ignores `*.key`. Remove it from history/rotate the cert, and ignore `*.pem` (this folder's `.gitignore` already does).
7. Backend A first crashed with `NameError: name '_name_' is not defined` (typo for `__name__`) and was fixed before the runs; the committed `backend.py` is the working version.
8. DNS names are `team1`, while Phase 1 evidence used the literal `teamX`.

## 5. How to reproduce

```bash
# Mac 3
python3 backend/backend.py --backend A --port 3001
# Mac 1
python3 backend/backend.py --backend B --port 3002
# Mac 1 / Mac 3: dnsmasq with configs/dnsmasq-*.conf.example, then
#   dnsmasq --test --conf-file="$(brew --prefix)/etc/dnsmasq.conf" && sudo brew services restart dnsmasq
# Mac 2: nginx with configs/nginx-primary.conf.example, trusted mkcert cert, then
sudo networksetup -setdnsservers Wi-Fi 10.7.27.143 10.7.26.181
curl -i https://app.team1.test:8443/api/status          # expect 200 and X-Backend A or B
```

IPs are DHCP-assigned; verify with `ipconfig getifaddr en0` and update the configs if they changed. Each extension's exact commands and rollback are in [`docs/phase2-handbook.md`](docs/phase2-handbook.md).

## 6. Viva quick answers

- **Why two DNS servers?** Resolution survives one server dying; nothing else is protected.
- **What does TTL do?** Caps how long a cache may reuse an answer; clients can briefly disagree after a change.
- **Why `pf` on backends?** Only the reverse proxy should reach them; other LAN hosts time out.
- **Passive failover?** nginx marks a server failed after a real failed request (`max_fails`/`fail_timeout`) and retries another (`proxy_next_upstream`); no background probes.
- **Why does the cert still work on the standby?** It binds to the hostname, not the IP.
- **Why not "zero downtime"?** DNS change is manual and caches vary.
