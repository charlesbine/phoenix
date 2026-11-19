# Split Deployment (Controller + Display Node)

Run the Phoenix dashboard and renderer on a home server, and keep a lightweight native `phoenix node` process on the host connected to a Matrix Portal M4.

```bash
docker compose -f deploy/split/docker-compose.yml up -d --build
```

For full pairing, TLS, reverse-proxy, and systemd instructions, see [`docs/deployment.md`](../../docs/deployment.md).
