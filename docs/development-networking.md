# Development networking

The repository's [Compose file](../docker-compose.yml) publishes development
services on IPv4 loopback by default. This document intentionally describes local
development networking, not a production topology or deployment procedure.

| Service | Default host address | Container port |
| --- | --- | --- |
| PostgreSQL (`db`) | `127.0.0.1:5432` | `5432` |
| Backend | `127.0.0.1:8000` | `8000` |
| Frontend | `127.0.0.1:5173` | `5173` |

`DEV_HOST_IP` controls the host address of all three existing port mappings.
Unset and empty values both resolve to `127.0.0.1`. Each service still publishes
exactly one port; scheduler has no published port. Local browser URLs are
`http://127.0.0.1:5173` and `http://127.0.0.1:8000`.

## Intentional remote development access

Set `DEV_HOST_IP` in your local `.env` or exported shell environment to an IPv4
address assigned to the Docker host, for example:

```dotenv
# Example only: replace with your host's intended LAN interface address.
DEV_HOST_IP=192.168.1.50
```

An exported value takes precedence over `.env`. `DEV_HOST_IP=0.0.0.0` explicitly
opts into all IPv4 host interfaces. This shared override exposes **all three
ports**, including PostgreSQL and the Flask development server, on the selected
interface; use it only for intentional access on a trusted development network
with appropriate host/network access controls. Use the selected host IP in remote
browser URLs. This setting does not provide authentication, TLS, a reverse proxy,
or production serving.

Host publication is separate from container networking. Backend and scheduler
still connect to `db:5432`; the frontend's `/api` proxy still targets
`http://backend:8000`. Vite continues listening on `0.0.0.0:5173` **inside its
container**, including the existing `--host 0.0.0.0` command. Changing Vite to
loopback inside the container would prevent the published port from reaching it.
No Vite configuration change is needed for this host-binding setting.

## Applying and checking configuration

Editing Compose or `.env` does not change existing containers. Live containers
keep their old port bindings until a **separately authorized recreation** applies
the new configuration; a restart alone does not update those bindings. Review
service startup effects before that operation: backend startup runs migrations,
and scheduler startup can enable scheduled generation. This networking change
does not change service commands, scheduler defaults, provider selection, or
[paid-execution guards](paid-execution.md).

For a read-only default configuration check from the repository root, use a clean
environment and an unused Docker client configuration path (choose a different
path if the example directory already exists):

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin \
  DOCKER_CONFIG=/tmp/horoscope-compose-config-unused \
  docker compose --env-file /dev/null -f docker-compose.yml config --quiet
```

`config --quiet` validates without starting containers or printing the resolved
environment. `--env-file /dev/null` skips local dotenv settings, and the clean
environment prevents inherited overrides or credentials. To check an explicit
value, add `DEV_HOST_IP=192.168.1.50` after `env -i` alongside the other assignments;
`DEV_HOST_IP=` checks the empty-value loopback default. These checks render
configuration only; they do not verify or alter live bindings, connectivity, or
firewall behavior. Do not print full resolved configuration from an operator
environment, which may contain credentials.
