# Split deployment

Run the Phoenix dashboard and renderer on a server and a native display node
on the host connected to a Matrix Portal M4. The example Compose file starts
a dashboard on server loopback and stores its database and artwork in named
volumes.

```sh
docker compose -f deploy/europa/docker-compose.yml up -d --build
```

For remote browser access, put the dashboard behind your existing
authenticated reverse proxy. On the same Docker network, target the
dashboard container on port 7002 and remove the loopback port mapping.
Run a WLED player with access to its panel's LAN address.

## Pair the serial player

Register a serial panel on the dashboard. Use its Phoenix device ID in
`PHOENIX_NODE_DEVICE` on both hosts. Generate one random token for the pair and
set `PHOENIX_NODE_TOKEN_FILE` to the path of its owner-only copy on each host.

On the player, set:

| Setting | Value |
|---|---|
| `PHOENIX_NODE_BIND` | Player's private LAN listen address |
| `PHOENIX_NODE_PORT` | HTTPS listener port, default 7443 |
| `PHOENIX_NODE_PEER` | Dashboard's expected LAN source address |
| `PHOENIX_NODE_TLS_CERT` | Server certificate with a SAN for the player address |
| `PHOENIX_NODE_TLS_KEY` | Owner-only TLS private key |
| `PHOENIX_SERIAL_PORT` | Local Matrix Portal serial device |

Run `phoenix node` under the player's service manager. It starts the HTTPS
listener and independently plays the rotation from disk. To use a local mic
for the audio visualizer, install PortAudio and the `audio` Python extra on
the player.

On the dashboard, set `PHOENIX_NODE_URL` to the player's private HTTPS origin
and `PHOENIX_NODE_CA_FILE` to the trusted certificate for that player. Mount
these and the token file read-only if the dashboard runs in a container.

The receiver permits state and native WebP uploads only from the paired source
address with the token. Aurora stores its accepted rotation, Night Mode settings,
and WebPs on disk so it can restart and play during a Europa outage. To upgrade
an existing split deployment, update the player before the dashboard.
