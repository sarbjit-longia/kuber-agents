---
description: Run the quantum (home server) deploy script. Usage `/quantum <subcommand>` where subcommand is ship, status, health, migrate, rollback, sync, logs, observability, or full.
---

# /quantum — Home Server Deploy

The user invoked `/quantum $ARGUMENTS`.

This command wraps `deploy/local/deploy.sh` (the existing home-server deploy script) so deploys to the quantum server (SSH alias `quantum`, IP 192.168.1.188) can be invoked from chat without leaving the conversation.

## Subcommand routing

Parse `$ARGUMENTS`. The first token is the subcommand. Anything after is passed through as args.

| Subcommand | What it does | Bash to run |
|-----------|--------------|-------------|
| `ship` | **Full one-shot deploy.** Build all 5 images locally, transfer to quantum, sync config + .env.prod + nginx, restart all app services, run alembic migrations + seed, health-check backend. Estimated 5-15 min. | `./deploy/local/deploy.sh ship` |
| `status` | Show server status (containers, disk, resource use) | `./deploy/local/deploy.sh status` |
| `health` | Run health checks on all services (backend, data-plane, grafana, prometheus, langfuse) | `./deploy/local/deploy.sh health` |
| `migrate` | Run alembic migrations + seed_database on quantum | `./deploy/local/deploy.sh migrate` |
| `rollback` | Roll back containers to `:previous` images | `./deploy/local/deploy.sh rollback` |
| `sync` | Sync config files (compose, .env.prod, nginx, signal-generator config, grafana dashboards) to quantum | `./deploy/local/deploy.sh sync` |
| `logs` | Tail logs for a service. Pass service name as second arg, e.g. `/quantum logs backend` | `./deploy/local/deploy.sh logs <service>` |
| `observability` | Bring up the Langfuse + Grafana + Prometheus stack (idempotent, uses `docker compose up -d --no-recreate`). First-time setup requires LANGFUSE_* env vars in `.env.prod` on the server. | `./deploy/local/deploy.sh observability` |
| `full` | Open the interactive deploy menu (for "Deploy Images", "Deploy Database", "Deploy Nginx", "Restart Containers" — these require human confirmation and are not safe to automate) | Tell the user: run `./deploy/local/deploy.sh` directly in their terminal — the interactive menu can't run inside the chat. |
| `help` or no args | Show this command's subcommand list | List the table above |

## Behavior rules

1. **Verify the subcommand is in the list before running.** If the user typed something not in the table (e.g., `/quantum deploy`), tell them which subcommands exist and what `full` is for. Do not invent subcommands.
2. **Run the bash command and show output to the user.** Use the standard Bash tool. Don't dangerously disable sandbox unless the command itself fails with a sandbox-related error (the deploy script needs SSH and rsync to network paths, which may require `dangerouslyDisableSandbox: true`).
3. **For `logs`:** if the user didn't provide a service name (just `/quantum logs`), the underlying script will prompt interactively. Tell the user to specify a service: `/quantum logs <service>` (common services: `backend`, `celery-worker`, `signal-generator`, `trigger-dispatcher`, `data-plane`, `frontend`, `redis`, `kafka`).
4. **For destructive subcommands (`rollback`, `ship`):** confirm with the user before running. Show what the operation does and ask for explicit go-ahead. These are hard-to-reverse production-modifying operations.
5. **For `migrate`:** mention that this runs against the production database on quantum. Ask the user to confirm the migrations are intended for production before running.
6. **For interactive prompts in the script:** the `ship_all` and `rollback` functions use the `confirm` helper which calls `read -rp "(y/N) "`. When invoked from chat, pipe `yes` into the command to auto-answer after the user has approved at the chat level: `yes "y" | ./deploy/local/deploy.sh ship`. Do NOT do this without first getting explicit user approval in the chat — bypassing the interactive confirm without prior chat approval skips a safety gate the script designed in.
7. **After running:** if the command succeeded, show a brief summary line (e.g., "Status check complete — all services healthy"). If it failed, surface the error verbatim and suggest next steps (often: run `/quantum logs <service>` for the failing service).
8. **For `ship` specifically:** the build phase takes 5-15 minutes and emits a lot of output (docker build progress per image). Don't tail with `| tail -N` — surface the FULL output so the user can see build progress and any errors. If the user invokes `/quantum ship` and you've already confirmed, run as `yes "y" | ./deploy/local/deploy.sh ship 2>&1` and let it stream.

## Example invocations

- `/quantum status` → Run `./deploy/local/deploy.sh status`
- `/quantum logs backend` → Run `./deploy/local/deploy.sh logs backend`
- `/quantum sync` → Run `./deploy/local/deploy.sh sync`
- `/quantum rollback` → Confirm with user first, then run `yes "y" | ./deploy/local/deploy.sh rollback`
- `/quantum ship` → **Confirm with user first** (build + transfer + restart is destructive and takes 5-15 min). Then run `yes "y" | ./deploy/local/deploy.sh ship 2>&1` and stream the full output.
- `/quantum observability` → Confirm with user (modifies prod), then run `yes "y" | ./deploy/local/deploy.sh observability`
- `/quantum full` → Tell the user to run the script directly in their terminal
- `/quantum` → Show the subcommand list

## Why this command exists vs `/ship`

- **`/ship`** is the gstack production-deploy skill. For kuber-agents it targets Fly.io (per `docs/office-hours-design-20260427.md`). Use it for production demo deploys.
- **`/quantum`** targets the home development server. Use it for fast inner-loop iteration during dev work, where the home server is the dev/staging environment.

The two don't conflict; they target different deploy environments.
