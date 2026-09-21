# Production deployment

Run these commands on the target only after uploading this repository without
local state, `.env`, or credentials:

```sh
cd /root/match5
python3 -m venv .venv
.venv/bin/pip install .
install -m 600 /dev/null .env
# edit .env with a generated enrollment token
set -a; . ./.env; set +a
pm2 start deploy/ecosystem.config.cjs
pm2 save
```

Install `deploy/nginx-mach5.conf` as an isolated Nginx site and test it with
`nginx -t` before reloading. Obtain the certificate only after the HTTP site is
reachable: `certbot --nginx -d mach5.jvjsc.com`. Then verify
`curl https://mach5.jvjsc.com/health` and a WebSocket session. Roll back by
disabling only the Mach5 site and `pm2 delete m5`; never delete unrelated PM2
applications.

The relay process needs `MACH5_ENROLLMENT_TOKEN` in its runtime environment.
Do not put that value in PM2 config, repository files, shell history, or logs.
