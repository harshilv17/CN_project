# Extension F - troubleshooting runbook (prepared, not yet exercised)

Work bottom-up the request path: **DNS -> client resolver -> TCP -> TLS -> nginx -> backend**. Change one thing, re-test, note the symptom, the hypothesis, the command that proved it, and the fix.

| Layer | Command | Failure suggests |
|---|---|---|
| DNS | `dig @10.7.27.143 app.team1.test`, `dig @10.7.26.181 app.team1.test` | dnsmasq down, wrong A record, primary/backup disagree |
| Client resolver | `networksetup -getdnsservers Wi-Fi`; `python3 -c 'import socket;print(socket.gethostbyname("app.team1.test"))'` | wrong resolver list, stale cache (`sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`) |
| TCP | `nc -vz 10.7.1.194 8443`; `nc -vz 10.7.26.181 3001`; `nc -vz 10.7.27.143 3002` | listener down, PF block (timeout), wrong IP |
| TLS | `curl -v https://app.team1.test:8443/api/status`; `openssl s_client -connect 10.7.1.194:8443 -servername app.team1.test` | CA not trusted, SAN mismatch, wrong cert |
| nginx | `nginx -t`; `lsof -nP -iTCP:8443 -sTCP:LISTEN`; error log | bad config, not started, bad upstream IP |
| Backends | `curl -i http://10.7.26.181:3001/api/status`; `curl -i http://10.7.27.143:3002/api/status` | process down, PF isolation |

Fault ideas to rehearse: wrong A record, primary dnsmasq stopped, PF block on a backend port, Backend A killed, SAN mismatch, wrong upstream IP in nginx, edge nginx stopped.

Symptom hints seen in this project: PF `block drop` -> `curl: (28) ... Timeout was reached`; stopped dnsmasq -> `dig ... connection timed out; no servers could be reached`; stopped backend -> nginx still answers (`X-Backend` = the survivor).
