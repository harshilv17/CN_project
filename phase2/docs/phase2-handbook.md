# Private Network Service Platform — Phase 2 Complete Setup & Operations Handbook

**Project:** Three-Mac private network service platform  
**Course:** Computer Networks  
**Scope:** Phase 2 Extensions A–E, Extension F preparation, testing, evidence, and safe rollback  
**Document date:** 25 November 2026  
**Status:** This is a reconstruction of the commands, configurations, and outcomes discussed during the project. It distinguishes confirmed tests from procedures provided for testing. It is **not** an assertion that every screenshot or demonstration was collected.

> **Important:** The experiment used a campus LAN. IP addresses may change when devices reconnect; verify them before rerunning. Do not run project-specific DNS or firewall changes on a different network without reviewing them. Keep private TLS keys and sensitive data out of GitHub.

---

## 1. Executive summary

The system uses three macOS laptops to host two HTTP backends, an nginx HTTPS edge, and redundant private DNS. The domain `app.team1.test` is resolved privately to the edge, which load-balances requests to Backend A and Backend B. Phase 2 added DNS failover, TTL-change demonstrations, backend isolation using `pf`, backend failure recovery through nginx, and a standby nginx edge on a second machine.

### Reported completion versus verification

| Extension | What was done | Evidence/status from the conversation |
|---|---|---|
| **A — Backup DNS** | Backup `dnsmasq` on Mac 3; clients configured with two resolvers; primary stopped and restored | **User confirmed completed:** backup continued resolving; normal client DNS and HTTPS worked |
| **B — TTL + controlled record change** | Primary DNS `api.team1.test` temporarily changed from `.194` to `.181`; TTL 30; cache and rollback tested | **User confirmed completed:** updated resolution, manual flush, original records and HTTPS restored. Note that observing a fresh answer does not alone prove a held cached answer |
| **C — Service isolation** | `pf` rules for Backend A and B allowing Mac 2 and blocking other LAN sources; rollback | **User confirmed completed** |
| **D — Backend failover** | Backend A stopped; nginx served requests through B; A restarted; load balancing resumed | **User confirmed completed** |
| **E — Standby edge + DNS migration** | Standby nginx on Mac 3 with transferred TLS certificate; DNS cutover and restoration procedure | **Standby HTTPS A/B responses visible in terminal screenshot.** Subsequent screenshot showed Mac 2's primary nginx was stopped and Homebrew startup failed during restoration; DNS again returned `.194`. Full successful DNS-cutover evidence was not independently established in available messages |
| **F — Faculty troubleshooting** | Diagnostic workflow and fault cases | **Preparation only**; actual faculty-injected fault not reported as completed |

---

## 2. Architecture and inventory

| Host | Owner | IP on project LAN | Services |
|---|---|---|---|
| **Mac 1** | Sushant | `10.7.27.143` | Primary `dnsmasq` on port 53; Backend B on TCP 3002 |
| **Mac 2** | Harshil | `10.7.1.194` | Primary nginx reverse proxy and TLS termination on TCP 8443; test client |
| **Mac 3** | Piyush | `10.7.26.181` | Backup `dnsmasq` on port 53; Backend A on TCP 3001; standby nginx on TCP 8443 for Extension E |

Historical LAN configuration: subnet `10.7.0.0/19` (`255.255.224.0`), gateway `10.7.0.1`. Confirm with `ifconfig` and `route -n get default` before assuming it is still valid.

```text
                       Private DNS
          Primary: Mac 1 10.7.27.143:53
          Backup:  Mac 3 10.7.26.181:53
                         |
                         v
         app.team1.test / api.team1.test
                         |
       Normal: 10.7.1.194    Migration: 10.7.26.181
                         |
          Mac 2 primary nginx HTTPS :8443
                         |
                  upstream pool
                /               \
               v                 v
     Mac 3 Backend A       Mac 1 Backend B
    10.7.26.181:3001      10.7.27.143:3002

     During E: Mac 3 also hosts standby nginx :8443
       -> Backend A using 127.0.0.1:3001
       -> Backend B using 10.7.27.143:3002
```

### Normal private DNS records

```ini
address=/app.team1.test/10.7.1.194
address=/api.team1.test/10.7.1.194
local-ttl=30
```

The experiment used `app.team1.test` and `api.team1.test` for the same HTTPS edge; nginx forwards `/api/status` to an upstream backend. The `local-ttl=30` value was used for Phase 2 experiments.

### Verification commands used throughout

```bash
# Run on Mac 2 (when private DNS is configured)
dig @10.7.27.143 app.team1.test +short
dig @10.7.26.181 app.team1.test +short
curl -i http://10.7.26.181:3001/api/status
curl -i http://10.7.27.143:3002/api/status
curl -i https://app.team1.test:8443/api/status
```

Expected healthy HTTP response includes `200 OK` and `X-Backend: A` or `X-Backend: B`. The application path is `/api/status`.

---

## 3. Baseline: Phase 1 working system

Phase 2 depends on the Phase 1 foundation. Historical checks reported successful LAN ping between every pair, private DNS resolution, two working backend servers, and trusted HTTPS to Mac 2.

### 3.1 Backends

- Backend A runs on Mac 3, port `3001`.
- Backend B runs on Mac 1, port `3002`.
- Each returns an HTTP 200 response on `/api/status`, with an `X-Backend` identifier.

Example **launch syntax only** (use the actual script path and arguments from your repository; the full original Python script is not reproduced here):

```bash
# Mac 3 — illustrative launch command if the script accepts these flags
python3 backend.py --backend A --port 3001

# Mac 1 — illustrative launch command
python3 backend.py --backend B --port 3002
```

Find the actual listening process:

```bash
lsof -nP -iTCP:3001 -sTCP:LISTEN   # Mac 3
lsof -nP -iTCP:3002 -sTCP:LISTEN   # Mac 1
```

### 3.2 Primary DNS: Mac 1

Homebrew `dnsmasq` configuration is usually located at:

```bash
$(brew --prefix)/etc/dnsmasq.conf
```

Relevant settings:

```ini
# Keep the original working listen-address and bind settings.
listen-address=127.0.0.1,10.7.27.143
bind-interfaces
address=/app.team1.test/10.7.1.194
address=/api.team1.test/10.7.1.194
local-ttl=30
```

> The snippet is the relevant target state, not a complete replacement for an existing configuration. Confirm interface and port settings before applying.

Validate and manage:

```bash
"$(brew --prefix)/sbin/dnsmasq" --test \
  --conf-file="$(brew --prefix)/etc/dnsmasq.conf"
sudo "$(command -v brew)" services restart dnsmasq

dig @127.0.0.1 app.team1.test +short
```

### 3.3 Primary nginx: Mac 2

Historical configuration path:

```text
/opt/homebrew/etc/nginx/nginx.conf
```

Relevant full example (verify certificate paths on the actual machine):

```nginx
worker_processes 1;

events { worker_connections 1024; }

http {
    upstream cn_backends {
        server 10.7.26.181:3001 max_fails=1 fail_timeout=5s;
        server 10.7.27.143:3002 max_fails=1 fail_timeout=5s;
    }

    server {
        listen 8443 ssl;
        server_name app.team1.test api.team1.test;

        ssl_certificate     /Users/harshilvalecha/cn-tls/app.team1.test.pem;
        ssl_certificate_key /Users/harshilvalecha/cn-tls/app.team1.test-key.pem;

        location / {
            proxy_pass http://cn_backends;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_connect_timeout 2s;
            proxy_read_timeout 5s;
            proxy_next_upstream error timeout http_502 http_503 http_504;
            proxy_next_upstream_tries 2;
        }
    }
}
```

Tests and manual management on Mac 2:

```bash
nginx -t
nginx                          # start only when not already running
nginx -s reload               # after editing config
nginx -s quit                 # graceful stop
lsof -nP -iTCP:8443 -sTCP:LISTEN
```

Check your actual Homebrew prefix before relying on the hard-coded path: `brew --prefix`.

### 3.4 TLS

The primary edge had an `mkcert`-issued certificate with SANs for `app.team1.test` and `api.team1.test`. Mac 2 and Mac 3 had trusted the issuing local CA, and HTTPS was confirmed without `curl -k`.

```bash
openssl x509 -in ~/cn-tls/app.team1.test.pem \
  -noout -subject -dates -ext subjectAltName
curl -i https://app.team1.test:8443/api/status
```

**Never commit** the server private key (`app.team1.test-key.pem`) or mkcert CA private key (`rootCA-key.pem`).

---

## 4. Extension A — Backup DNS and resolver failover

### Objective

Run a second private DNS server on Mac 3, configure the client machines to know both DNS servers, stop Mac 1 primary DNS, demonstrate continued resolution and HTTPS, and then restore primary DNS.

### 4.1 Backup DNS on Mac 3

Install `dnsmasq` if needed:

```bash
brew install dnsmasq
```

Edit on Mac 3:

```bash
nano "$(brew --prefix)/etc/dnsmasq.conf"
```

Relevant entries:

```ini
listen-address=127.0.0.1,10.7.26.181
bind-interfaces
address=/app.team1.test/10.7.1.194
address=/api.team1.test/10.7.1.194
local-ttl=30
```

Validate and start:

```bash
"$(brew --prefix)/sbin/dnsmasq" --test \
  --conf-file="$(brew --prefix)/etc/dnsmasq.conf"
sudo "$(command -v brew)" services start dnsmasq
```

Direct verification from Mac 2:

```bash
dig @10.7.27.143 app.team1.test +short
dig @10.7.26.181 app.team1.test +short
```

Both should answer `10.7.1.194`.

### 4.2 Configure two resolvers on Mac 2 and Mac 3

```bash
sudo networksetup -setdnsservers Wi-Fi 10.7.27.143 10.7.26.181
networksetup -getdnsservers Wi-Fi
```

> Resolver order is not a perfect strict-primary/fallback guarantee on macOS. For convincing evidence, also query both servers directly and test actual application resolution.

### 4.3 Primary DNS outage test

On **Mac 1**, stop DNS only; **leave Backend B running**:

```bash
sudo "$(command -v brew)" services stop dnsmasq
```

On **Mac 2**, demonstrate that the primary is unavailable and backup still works:

```bash
dig @10.7.27.143 app.team1.test +time=1 +tries=1
dig @10.7.26.181 app.team1.test +short
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
python3 -c 'import socket; print(socket.gethostbyname("app.team1.test"))'
curl -i https://app.team1.test:8443/api/status
```

On **Mac 1**, restore primary DNS:

```bash
sudo "$(command -v brew)" services start dnsmasq
```

Check both direct DNS queries again. **Confirmed outcome from user:** Backup continued resolving, normal client DNS and HTTPS still worked, and primary was restored.

---

## 5. Extension B — DNS TTL and controlled record change

### Objective

Show a 30-second TTL and demonstrate what happens when a DNS answer changes. We changed only `api.team1.test` so the main app hostname could remain on Mac 2 during the experiment.

### 5.1 Backup and set TTL on Mac 1

```bash
cp "$(brew --prefix)/etc/dnsmasq.conf" ~/dnsmasq-before-ttl.conf
nano "$(brew --prefix)/etc/dnsmasq.conf"
```

Original relevant records:

```ini
local-ttl=30
address=/app.team1.test/10.7.1.194
address=/api.team1.test/10.7.1.194
```

Validate and restart:

```bash
"$(brew --prefix)/sbin/dnsmasq" --test \
  --conf-file="$(brew --prefix)/etc/dnsmasq.conf"
sudo "$(command -v brew)" services restart dnsmasq
```

From Mac 2:

```bash
dig @10.7.27.143 api.team1.test +noall +answer
```

Expected answer contains `30 IN A 10.7.1.194`.

### 5.2 Isolate the resolver for a controlled test

On Mac 2:

```bash
sudo networksetup -setdnsservers Wi-Fi 10.7.27.143
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
python3 -c 'import socket; print(socket.gethostbyname("api.team1.test"))'
```

Expected original answer: `10.7.1.194`.

### 5.3 Change API DNS record on Mac 1

```ini
# Unchanged:
address=/app.team1.test/10.7.1.194
# Temporary controlled change:
address=/api.team1.test/10.7.26.181
local-ttl=30
```

Validate/restart as above. Verify directly from Mac 2:

```bash
dig @10.7.27.143 api.team1.test +noall +answer
```

Expected new answer: `10.7.26.181`.

### 5.4 Observe resolution, TTL and cache

```bash
# System API resolution, which may use macOS DNS caching:
python3 -c 'import socket; print(socket.gethostbyname("api.team1.test"))'

# After the TTL has elapsed, query again:
python3 -c 'import socket; print(socket.gethostbyname("api.team1.test"))'

# Manual cache flush:
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
python3 -c 'import socket; print(socket.gethostbyname("api.team1.test"))'
```

Important interpretation:

- `dig @10.7.27.143 ...` shows the **current DNS server response**, not proof of a cached macOS client response.
- `python3 socket.gethostbyname()` uses normal system hostname resolution.
- Seeing the new IP after a flush confirms current resolution; **by itself** it does not prove that the old answer remained cached exactly 30 seconds or that flushing accelerated an update.
- The conversation showed a troubleshooting point where *both* DNS servers returned `.194`: at that moment, the primary had not yet been observed serving the new record. The later change succeeded, and the user confirmed completion.

### 5.5 Restore normal DNS

On Mac 1 restore:

```ini
address=/app.team1.test/10.7.1.194
address=/api.team1.test/10.7.1.194
local-ttl=30
```

Validate/restart dnsmasq. On Mac 2 restore both resolvers and flush:

```bash
sudo networksetup -setdnsservers Wi-Fi 10.7.27.143 10.7.26.181
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder

dig @10.7.27.143 api.team1.test +short
dig @10.7.26.181 api.team1.test +short
curl -i https://app.team1.test:8443/api/status
```

Both DNS answers should be `10.7.1.194`. **User confirmed Extension B complete.**

---

## 6. Extension C — Backend isolation with macOS PF

### Objective

Restrict remote access to each backend so that only the nginx edge (Mac 2) may connect to Backend A or B, while DNS and HTTPS remain available.

### 6.1 Save the original firewall state **on both Mac 1 and Mac 3**

```bash
sudo cp /etc/pf.conf /etc/pf.conf.cn-phase2-backup
sudo pfctl -si
sudo pfctl -sr > ~/pf-rules-before-phase2.txt
networksetup -listallhardwareports
```

Check that the active Wi-Fi interface is actually `en0`. Substitute the real interface in the rules if needed. Keep access to the **local terminal** for recovery.

### 6.2 Mac 1 PF anchor protects Backend B `3002`

Create `/etc/pf.anchors/cn_phase2`:

```pf
# Mac 2 may reach Backend B on Mac 1
pass in quick on en0 inet proto tcp from 10.7.1.194 to 10.7.27.143 port 3002
# Other remote sources may not
block in quick on en0 inet proto tcp from any to 10.7.27.143 port 3002
```

In `/etc/pf.conf`, add the following **in a valid anchor/rule position** rather than blindly appending if the existing file has ordering constraints:

```pf
anchor "cn_phase2"
load anchor "cn_phase2" from "/etc/pf.anchors/cn_phase2"
```

**macOS PF caveat:** PF rule section ordering and Apple's existing anchors matter; if `pfctl -nf` reports a rules-order error, reposition the anchor correctly instead of forcing a load. Existing states may persist after a rules change; use fresh connections and, only if safe and necessary, inspect state with `pfctl -ss`. Avoid globally flushing states or rules on a shared machine.

Validate and load:

```bash
sudo pfctl -nf /etc/pf.conf
sudo pfctl -f /etc/pf.conf
sudo pfctl -si
sudo pfctl -a cn_phase2 -sr
```

If PF was previously disabled and must be enabled for the demo:

```bash
sudo pfctl -E
```

**Record the returned enable-reference token** so that this specific enable can later be released. Do not assume you should disable PF globally afterward.

From **Mac 2**, Backend B should work:

```bash
curl --connect-timeout 3 -i http://10.7.27.143:3002/api/status
```

From **Mac 3**, the same remote request should fail. (A timeout is typical for a dropped packet; a connection refusal or another failure can occur depending on the effective rule and networking.)

### 6.3 Mac 3 PF anchor protects Backend A `3001`

On Mac 3 create `/etc/pf.anchors/cn_phase2`:

```pf
pass in quick on en0 inet proto tcp from 10.7.1.194 to 10.7.26.181 port 3001
block in quick on en0 inet proto tcp from any to 10.7.26.181 port 3001
```

Add/load the anchor to Mac 3's own PF configuration using the same validation steps.

From **Mac 2**, Backend A should work:

```bash
curl --connect-timeout 3 -i http://10.7.26.181:3001/api/status
```

From **Mac 1**, a direct remote connection to Backend A should fail.

### 6.4 Test the integrated platform

On Mac 2:

```bash
for i in {1..10}; do
  curl -sS -D - https://app.team1.test:8443/api/status -o /dev/null \
    | grep -Ei '^HTTP/|^X-Backend:'
done
```

Expect healthy HTTP 200 responses through both upstreams. Verify DNS remains available on ports 53. PF rules on `en0` do not ordinarily block Backend A's own `127.0.0.1:3001` loopback access.

### 6.5 Safe rollback (independently on Mac 1 and Mac 3)

```bash
sudo test -f /etc/pf.conf.cn-phase2-backup
sudo cp /etc/pf.conf.cn-phase2-backup /etc/pf.conf
sudo pfctl -nf /etc/pf.conf
sudo pfctl -f /etc/pf.conf
sudo pfctl -sr
```

If the project used `sudo pfctl -E` and a reference token was recorded, release **that** reference with `sudo pfctl -X <saved-token>`. Do not run `pfctl -F all`, and do not indiscriminately disable the machine's firewall.

Re-test previously blocked cross-Mac backend calls to confirm access was restored. **User confirmed Extension C complete.**

> **Extension E interaction:** If Mac 1's PF rules still only allow Mac 2 to reach port 3002, then standby nginx on Mac 3 cannot use Backend B. For the edge-migration demo, either safely roll back Mac 1's test rules or explicitly add a narrow allowance for Mac 3 to Backend B. Do not silently leave the architecture in a broken state.

---

## 7. Extension D — High-availability backend failover

### Objective

Demonstrate that nginx continues to serve Backend B when Backend A fails, then automatically resumes balancing traffic after A recovers.

### 7.1 nginx passive-failover settings on Mac 2

The configured upstream was:

```nginx
upstream cn_backends {
    server 10.7.26.181:3001 max_fails=1 fail_timeout=5s;
    server 10.7.27.143:3002 max_fails=1 fail_timeout=5s;
}
```

In the proxy location:

```nginx
proxy_connect_timeout 2s;
proxy_read_timeout 5s;
proxy_next_upstream error timeout http_502 http_503 http_504;
proxy_next_upstream_tries 2;
```

Validate after edits:

```bash
nginx -t && nginx -s reload
```

This is **passive** upstream failure detection—not continuous active health probing.

### 7.2 Baseline (Mac 2)

```bash
for i in {1..10}; do
  curl -sS -D - https://app.team1.test:8443/api/status -o /dev/null \
    | grep -Ei '^HTTP/|^X-Backend:'
done
```

Look for successful responses from A and B.

### 7.3 Stop Backend A only (Mac 3)

Stop only the Backend A Python process (for example with `Control-C` in the Terminal that launched it). **Do not stop Mac 3 itself** because backup DNS must continue running.

```bash
lsof -nP -iTCP:3001 -sTCP:LISTEN
```

No listener indicates port 3001 is closed.

### 7.4 Test failover (Mac 2)

```bash
for i in {1..10}; do
  echo "Request $i"
  curl -sS -D - https://app.team1.test:8443/api/status -o /dev/null \
    | grep -Ei '^HTTP/|^X-Backend:'
done
```

Expected steady-state success through `X-Backend: B`. Note any transient error instead of claiming flawless failover if errors occur.

### 7.5 Restore Backend A and retest

Start the same Backend A process as in Phase 1, check locally:

```bash
curl -i http://127.0.0.1:3001/api/status
```

After nginx's fail window has elapsed, rerun the 10-request test and confirm both A/B responses. **User confirmed Extension D complete.**

### Remaining single point of failure

Mac 2 nginx remains the sole default HTTPS entry. If it fails, DNS can still point to `.194` while both backends are healthy, but clients cannot reach the application. **Extension E** addresses this with a preconfigured standby edge and a **manual DNS cutover**, not automatic edge failover.

---

## 8. Extension E — Standby nginx and DNS-based edge migration

### Objective

Run standby nginx on Mac 3, verify it can reach both backends, prove HTTPS using the existing domain and certificate, change DNS from Mac 2 to Mac 3, and later restore the original edge.

### 8.1 Prepare networking and firewall

On **Mac 3**:

```bash
curl -i http://127.0.0.1:3001/api/status
curl -i http://10.7.27.143:3002/api/status
```

Both must work. If Backend B is blocked, review Mac 1's Extension C PF rules/rollback before proceeding.

### 8.2 Install and stage standby nginx on Mac 3

```bash
brew list --versions nginx || brew install nginx
mkdir -p ~/cn-standby/{certs,logs}
lsof -nP -iTCP:8443 -sTCP:LISTEN
whoami
```

Use `~/cn-standby/nginx.conf` with a custom prefix, rather than overwriting Mac 3's global nginx config.

### 8.3 Transfer the existing TLS certificate

The two required files from Mac 2 were:

```text
/Users/harshilvalecha/cn-tls/app.team1.test.pem
/Users/harshilvalecha/cn-tls/app.team1.test-key.pem
```

`scp` was suggested initially but was not usable in the user's environment. **The selected workaround was to send the files directly (e.g., AirDrop).** The user reported that both independent `.pem` files were present in **Mac 3's Downloads** and had correct permissions.

Recommended organization on Mac 3:

```bash
mkdir -p ~/cn-standby/certs
mv ~/Downloads/app.team1.test.pem ~/cn-standby/certs/
mv ~/Downloads/app.team1.test-key.pem ~/cn-standby/certs/
chmod 600 ~/cn-standby/certs/app.team1.test-key.pem
chmod 644 ~/cn-standby/certs/app.team1.test.pem
```

If keeping them in `~/Downloads/`, adjust nginx's `ssl_certificate` and `ssl_certificate_key` paths accordingly. Check certificate SANs:

```bash
openssl x509 -in ~/cn-standby/certs/app.team1.test.pem \
  -noout -subject -dates -ext subjectAltName
```

The client must trust the certificate's issuing CA. Do not copy `rootCA-key.pem`. Remove the private-key copy from Downloads after moving it.

### 8.4 Example standby nginx config (Mac 3)

Create `~/cn-standby/nginx.conf`; replace `PIYUSH_USERNAME` with `whoami` output.

```nginx
worker_processes 1;
pid /Users/PIYUSH_USERNAME/cn-standby/nginx.pid;
error_log /Users/PIYUSH_USERNAME/cn-standby/logs/error.log;

events { worker_connections 1024; }

http {
    access_log /Users/PIYUSH_USERNAME/cn-standby/logs/access.log;

    upstream cn_backends {
        server 127.0.0.1:3001 max_fails=1 fail_timeout=5s;
        server 10.7.27.143:3002 max_fails=1 fail_timeout=5s;
    }

    server {
        listen 8443 ssl;
        server_name app.team1.test api.team1.test;
        ssl_certificate /Users/PIYUSH_USERNAME/cn-standby/certs/app.team1.test.pem;
        ssl_certificate_key /Users/PIYUSH_USERNAME/cn-standby/certs/app.team1.test-key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;

        location / {
            proxy_pass http://cn_backends;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 2s;
            proxy_read_timeout 5s;
            proxy_next_upstream error timeout http_502 http_503 http_504;
            proxy_next_upstream_tries 2;
        }
    }
}
```

Validate, start, inspect:

```bash
nginx -t -c "$HOME/cn-standby/nginx.conf" -p "$HOME/cn-standby/"
nginx    -c "$HOME/cn-standby/nginx.conf" -p "$HOME/cn-standby/"
lsof -nP -iTCP:8443 -sTCP:LISTEN
```

### 8.5 Test standby without changing DNS (Mac 2)

```bash
curl -i --resolve app.team1.test:8443:10.7.26.181 \
  https://app.team1.test:8443/api/status

for i in {1..8}; do
  curl -sS -D - --resolve app.team1.test:8443:10.7.26.181 \
    https://app.team1.test:8443/api/status -o /dev/null \
    | grep -Ei '^HTTP/|^X-Backend:'
done
```

Expected trusted HTTPS 200 and backend A/B across requests. **The supplied terminal screenshot contains earlier sequences of HTTP 200 responses with alternating A/B headers**, supporting that a load-balanced HTTPS edge was working. To conclusively attribute those responses to standby nginx, retain the command containing `--resolve` and/or standby access logs.

### 8.6 Back up both DNS servers and make the cutover

On both Mac 1 and Mac 3:

```bash
cp "$(brew --prefix)/etc/dnsmasq.conf" \
  ~/dnsmasq-before-edge-migration.conf
```

For controlled testing on Mac 2, optionally use only primary DNS temporarily:

```bash
sudo networksetup -setdnsservers Wi-Fi 10.7.27.143
```

Update both DNS servers (Mac 1 first, Mac 3 immediately afterward):

```ini
local-ttl=30
address=/app.team1.test/10.7.26.181
address=/api.team1.test/10.7.26.181
```

Each DNS server validates/restarts separately:

```bash
"$(brew --prefix)/sbin/dnsmasq" --test \
  --conf-file="$(brew --prefix)/etc/dnsmasq.conf"
sudo "$(command -v brew)" services restart dnsmasq
```

On Mac 2 verify both DNS servers now agree:

```bash
dig @10.7.27.143 app.team1.test +short
dig @10.7.26.181 app.team1.test +short
```

Expected `10.7.26.181` from each.

### 8.7 Verify the actual migration (Mac 2)

```bash
python3 -c 'import socket; print(socket.gethostbyname("app.team1.test"))'
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
python3 -c 'import socket; print(socket.gethostbyname("app.team1.test"))'
curl -i https://app.team1.test:8443/api/status
```

Expected: system resolution to `.181` and trusted HTTP 200 without `-k` or `--resolve`.

On Mac 3, confirm requests land on standby:

```bash
tail -f ~/cn-standby/logs/access.log
```

To demonstrate reduced dependence on Mac 2, stop the original nginx **only after** the standby and DNS cutover are verified, then repeat the client request and check Mac 3's access log. This is still **manual migration**, not instantaneous automatic edge failover.

### 8.8 Restore original DNS records and edge

On Mac 1 and Mac 3, restore their independent backups:

```bash
sudo cp ~/dnsmasq-before-edge-migration.conf \
  "$(brew --prefix)/etc/dnsmasq.conf"
"$(brew --prefix)/sbin/dnsmasq" --test \
  --conf-file="$(brew --prefix)/etc/dnsmasq.conf"
sudo "$(command -v brew)" services restart dnsmasq
```

On Mac 2 restore both resolvers and flush the cache:

```bash
sudo networksetup -setdnsservers Wi-Fi 10.7.27.143 10.7.26.181
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder

dig @10.7.27.143 app.team1.test +short
dig @10.7.26.181 app.team1.test +short
```

Expected: both `.194` again. Restart primary nginx on Mac 2, **if it had been stopped**:

```bash
nginx -t
nginx
lsof -nP -iTCP:8443 -sTCP:LISTEN
curl -i https://app.team1.test:8443/api/status
```

Stop standby only when primary is confirmed healthy:

```bash
# On Mac 3
nginx -s quit -c "$HOME/cn-standby/nginx.conf" -p "$HOME/cn-standby/"
```

### 8.9 Actual restoration issue observed on Mac 2

A terminal screenshot later showed:

```text
nginx -s stop
...
dig @10.7.27.143 app.team1.test +short  -> 10.7.1.194
dig @10.7.26.181 app.team1.test +short -> 10.7.1.194
brew services start nginx -> Bootstrap failed: 5: Input/output error
curl -i https://app.team1.test:8443/api/status -> Couldn't connect
```

That indicates DNS was back to `.194` but Mac 2's primary nginx service was unavailable at that moment. The suggested diagnostic was:

```bash
nginx -t
nginx
lsof -nP -iTCP:8443 -sTCP:LISTEN
curl -i https://app.team1.test:8443/api/status
```

Subsequently, Mac 2 showed nginx PIDs `7444` and `7445` listening on `*:8443`, demonstrating nginx had started or remained running. The user then requested a **full project cleanup on Mac 2**, detailed below. Do not infer that final DNS-based migration evidence is complete solely from the restart screenshot.

---

## 9. Extension F — Troubleshooting / fault injection preparation

**Status:** The faculty-injected troubleshooting challenge was described as mandatory, but its actual execution has **not** been confirmed.

Follow the sequence **DNS → TCP → TLS → nginx → backend**.

| Layer | Main diagnostic | What a failure suggests |
|---|---|---|
| DNS | `dig @10.7.27.143 app.team1.test`; `dig @10.7.26.181 ...` | DNS process down, incorrect A record, inconsistent resolvers |
| Client resolver | `networksetup -getdnsservers Wi-Fi`; Python `socket.gethostbyname()` | Wrong resolver configuration, cached answer |
| TCP | `nc -vz 10.7.1.194 8443`; `nc -vz 10.7.26.181 3001`; `nc -vz 10.7.27.143 3002` | Listener down, firewall rule, bad address, routing |
| TLS | `curl -v https://app.team1.test:8443/api/status`; `openssl s_client -connect 10.7.1.194:8443 -servername app.team1.test` | Certificate trust/SAN mismatch, wrong certificate, nginx SSL listener issue |
| nginx | `nginx -t`; `lsof -nP -iTCP:8443 -sTCP:LISTEN`; inspect error log | Invalid nginx config, start failure, bad upstream |
| Backend A | `curl -i http://10.7.26.181:3001/api/status` | Backend A down or isolated |
| Backend B | `curl -i http://10.7.27.143:3002/api/status` | Backend B down or isolated |

**Fault practice examples:** wrong DNS record, stopped primary DNS, blocked backend port, stopped Backend A, certificate SAN mismatch, broken nginx upstream IP, stopped edge nginx. For each: note the symptom, form a hypothesis, run evidence-producing commands, apply the smallest safe fix, and verify recovery.

---

## 10. Mac 2 cleanup for normal everyday macOS operation

**This section records the user's later request to undo project-specific changes on Mac 2.** It is **not** the same as restoring the project to an operational Phase 1 state.

### 10.1 Stop project nginx

```bash
brew services stop nginx
nginx -s quit
lsof -nP -iTCP:8443 -sTCP:LISTEN
```

The user subsequently showed two nginx processes still listening:

```text
nginx 7444 ... TCP *:8443 (LISTEN)
nginx 7445 ... TCP *:8443 (LISTEN)
```

The suggested graceful stop of the then-current PIDs was:

```bash
kill -QUIT 7444
lsof -nP -iTCP:8443 -sTCP:LISTEN
```

If still running, inspect whether the other process belongs to the same nginx instance before stopping it:

```bash
ps -o pid,ppid,command -p 7444,7445
```

Those PID values were **from that historical screenshot**. **Never reuse them later without confirming which processes currently own the port.** Prefer `nginx -s quit` for the intended instance, then targeted termination of the actual current master PID if needed.

### 10.2 Restore automatic Wi-Fi DNS

```bash
sudo networksetup -setdnsservers Wi-Fi Empty
networksetup -getdnsservers Wi-Fi
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
```

A response like `There aren't any DNS Servers set on Wi-Fi` means there are no **manual** DNS servers; DHCP/network-supplied DNS can still be active.

### 10.3 Test normal internet

```bash
ping -c 3 google.com
curl -I https://www.google.com
```

Uninstalling nginx or deleting project files is not required to restore normal internet use. It is safer to preserve the configurations and screenshots for submission.

### 10.4 If you later want the private project working again on Mac 2

1. Reconnect all Macs to a network where the same LAN IPs are valid (or update all configuration addresses).
2. Set Mac 2 DNS back to `10.7.27.143 10.7.26.181`.
3. Confirm both backends and DNS servers are running.
4. Validate `nginx -t`, start nginx if not already running, verify port `8443`.
5. Request `https://app.team1.test:8443/api/status` and confirm A/B headers.

---

## 11. Recommended evidence folder structure

```text
project/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── phase2-report.md
│   ├── phase2-edge-migration.md
│   └── troubleshooting-runbook.md
├── configs/
│   ├── nginx-primary.conf.example
│   ├── nginx-standby.conf.example
│   ├── dnsmasq-primary.conf.example
│   ├── dnsmasq-backup.conf.example
│   └── firewall/
│       ├── mac1-backend-b.pf
│       ├── mac3-backend-a.pf
│       └── rollback.md
└── evidence/
    └── phase2/
        ├── extension-a-backup-dns/
        ├── extension-b-dns-ttl/
        ├── extension-c-service-isolation/
        ├── extension-d-ha-failover/
        ├── extension-e-edge-migration/
        └── extension-f-troubleshooting/
```

Collect actual terminal outputs, timestamps, and screenshots. Never fabricate evidence. Store only redacted example configs in the repo; do not commit credentials or private keys.

### Suggested per-extension screenshots

| Extension | Screenshots |
|---|---|
| A | Both DNS respond; primary DNS stopped; backup responds; client HTTPS works; primary restored |
| B | Original TTL 30; changed A record; client resolver observation; flush; restored records |
| C | PF config validated; allowed Mac 2 traffic; blocked cross-Mac backend traffic; HTTPS still works; rollback success |
| D | Normal A/B; A process stopped; B serves requests; A restarted; A/B resumes |
| E | Standby config; valid certificate; `--resolve` test; primary and backup DNS changes; successful non-overridden HTTPS; standby log; restore |
| F | Injected symptom; layer-by-layer diagnostics; fix; post-fix success |

---

## 12. Report/viva concepts to be able to explain

**Why two DNS servers?** A secondary resolver allows name resolution to continue if one DNS service goes down. It does not itself protect the nginx edge or application processes.

**What does TTL protect or delay?** A TTL limits how long a resolver may cache an answer. During a DNS change, different clients can temporarily use different addresses until their caches refresh. The 30-second TTL does not guarantee every client holds the answer for exactly 30 seconds.

**Why `pf` isolation?** Backend ports should be accessible from the reverse proxy, not arbitrary machines on the LAN. DNS, TLS, and internal backend communication can remain available independently.

**What is passive upstream failover?** nginx can mark an upstream as unavailable after certain request failures and route to another configured server; this is not an active external health-check system.

**Why a standby nginx?** It provides an alternative HTTPS entry point if the original edge is unavailable. DNS repointing changes where the name resolves, but the cutover is manual and subject to caching.

**Why does the TLS certificate still work after changing IP?** The certificate authenticates the hostname (`app.team1.test`), not the old IP. If the same trusted certificate is correctly installed on the standby, clients can validate the unchanged hostname there too.

**Why can't Extension E claim zero downtime automatically?** DNS changes are manual, resolver caches differ, and connection behavior varies. The experiment demonstrates controlled migration, not automatic edge HA or guaranteed zero downtime.

---

## 13. End-state checklist

### When keeping the project operational

- [ ] Both backends running (`3001` and `3002`)
- [ ] Primary and backup DNS running (`53`) and serving the same expected records
- [ ] Both clients have the intended private DNS settings
- [ ] Primary nginx listening on Mac 2 (`8443`)
- [ ] Certificate validates without `-k`
- [ ] HTTPS requests reach Backend A and Backend B
- [ ] PF status is intentional and documented
- [ ] Standby nginx remains staged but doesn't conflict with ordinary service operation

### When returning Mac 2 to ordinary use

- [ ] Project nginx not running on Mac 2
- [ ] Wi-Fi DNS reset to automatic (`Empty`)
- [ ] macOS DNS cache flushed
- [ ] Public DNS and HTTPS internet access verified
- [ ] Project source files and evidence retained for submission

### Confirmed versus outstanding

- **Confirmed by user:** A, B, C, D complete.
- **E:** Standby HTTPS traffic visible; the full DNS migration should be marked complete only if the actual cutover and restore tests were recorded.
- **F:** Practice runbook prepared; actual faculty challenge remains to be performed or documented.
- **Final work:** Consolidate evidence, submit report, and prepare viva/demo.

---

*This handbook is intended as both an execution guide and an accurate record. It preserves the known project topology and the important operational distinction between “work performed,” “expected output,” and “verified result.”*
