# TLS (Phase 2)

Same mkcert certificate as Phase 1 for `app.team1.test` / `api.team1.test`, issued by the local mkcert CA that Mac 2 and Mac 3 trust.

- Primary edge (Mac 2): `~/cn-tls/app.team1.test.pem` + `app.team1.test-key.pem`.
- Standby edge (Mac 3, Extension E): same two files, moved by AirDrop (`scp` failed - see `evidence/extension-e-edge-migration/mac2-harshil-151359.png`) into `~/cn-standby/certs/`, key `chmod 600`.
- The cert authenticates the **hostname**, so it validates on the standby with no change after DNS repoints.

Check SANs: `openssl x509 -in app.team1.test.pem -noout -subject -dates -ext subjectAltName`

**Do not commit** `*-key.pem` or mkcert's `rootCA-key.pem`. They are intentionally absent from this folder.
