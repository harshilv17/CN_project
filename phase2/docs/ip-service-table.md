# Machines, IPs and services (Phase 2)

LAN: `10.7.0.0/19` (mask `255.255.224.0`), gateway `10.7.0.1` (seen in Mac 1 and Mac 3 `networksetup -getinfo` / `ifconfig` captures). DHCP - addresses differ from Phase 1 (`10.7.7.x`) and may change again.

| Machine | Owner | IP | Services | Evidence |
|---|---|---|---|---|
| Mac 1 | Sushant | `10.7.27.143` | primary dnsmasq `:53`, Backend B `:3002`, PF anchor for B | [IP](../evidence/00-baseline/mac1-mac-1-ip.png), [ping](../evidence/00-baseline/mac1-mac1-ping.png), [Backend B](../evidence/00-baseline/mac1-sushant-134912.png) |
| Mac 2 | Harshil | `10.7.1.194` | primary nginx HTTPS `:8443`, test client | [IP](../evidence/00-baseline/mac2-mac2ip.png), [ping](../evidence/00-baseline/mac2-mac2-ping.png) |
| Mac 3 | Piyush | `10.7.26.181` | backup dnsmasq `:53`, Backend A `:3001`, standby nginx `:8443` (Ext E), PF anchor for A | [IP](../evidence/00-baseline/mac3-mac3-ip.png), [ping](../evidence/00-baseline/mac3-mac3-ping.png), [Backend A](../evidence/00-baseline/mac3-backenda-running.png) |

Names: `app.team1.test`, `api.team1.test` (both -> Mac 2 normally; -> Mac 3 during Ext E cutover).
Three physical MacBooks, no VMs or cloud.
