# Selling Hermes: Managed Per-Company Deployments

> **Status:** Strategy / architecture doc. No code changes yet.
> **Model chosen:** Managed per-company deployments — you stand up and operate a
> dedicated Hermes instance for each client, billed as setup + recurring managed
> hosting (consulting-flavored, not self-serve SaaS).
> **Your "main" Hermes agent** acts as the operator's control plane: it
> provisions, configures, monitors, and runs day-2 ops across all client
> instances.

---

## 0. TL;DR

- Each client = **one isolated Hermes instance** (its own `~/.hermes` state,
  its own model keys, its own gateway, its own skills/memory).
- You run a **golden template** (your tuned config) and stamp a copy per client.
- Your **main Hermes agent is the orchestrator** — it drives provisioning and
  monitoring via subagents + a terminal backend (Docker/SSH/Daytona).
- Charge **one-time onboarding + monthly managed fee**, pass through model spend
  with a margin.
- **Rebrand before you sell.** "Hermes" is Nous Research's name; the code is MIT
  (you can sell it) but the brand isn't yours. White-label it.

---

## 1. Why this model fits the codebase

Managed per-company deploys are the lowest-friction way to start, and Hermes is
already built for it:

| Capability | Where it lives | Why it matters for selling |
|---|---|---|
| Per-install isolated state | `~/.hermes` (mounted as `/opt/data` in Docker) | One client = one state dir = one container/VPS. Clean tenant boundary. |
| Multiple deploy backends | `local, docker, ssh, singularity, modal, daytona, vercel_sandbox` (`environments/`, `TERMINAL_ENV`) | Start with Docker/VPS per client; move idle clients to Daytona/Modal hibernation to cut cost. |
| Multi-channel gateway | `gateway/` (`hermes gateway run`) | Non-technical clients talk to *their* agent from Slack/Telegram/WhatsApp/email. Huge selling point. |
| Skills + memory + cron | skills system, `hermes_state.py`, `cron/` | Each instance accumulates company-specific skills + a deepening org model = stickiness / moat. |
| Subagents + RPC tools | spawn isolated subagents | Your **main** agent orchestrates the fleet without you typing every command. |
| Dashboard | `hermes dashboard` (binds `127.0.0.1`) | Per-client admin UI behind an SSH tunnel / authenticated reverse proxy. |

**Reuse, don't rebuild.** The provisioning unit already exists as
`docker-compose.yml`. The managed business is mostly *operations and packaging*
around primitives the repo ships.

---

## 2. Reference architecture

```
                 ┌─────────────────────────────────────────────┐
                 │  YOUR OPERATOR PLANE                          │
                 │                                               │
                 │  Main Hermes Agent (orchestrator)             │
                 │   ├─ provisioning skill  → spins up instances │
                 │   ├─ monitoring cron     → health/usage/bill  │
                 │   └─ subagents           → per-client tasks   │
                 │                                               │
                 │  Golden template repo (your tuned config)     │
                 │  Client registry (clients.yaml / DB)          │
                 │  Secrets vault (per-client model keys)        │
                 └───────────────┬───────────────────────────────┘
                                 │ provisions / manages
        ┌────────────────┬───────┴────────┬────────────────┐
        ▼                ▼                ▼                ▼
  ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
  │ Acme Inc  │    │ Globex    │    │ Initech   │    │  ...      │
  │ container │    │ VPS       │    │ Daytona   │    │           │
  │ ~/.hermes │    │ ~/.hermes │    │ (idle)    │    │           │
  │ gateway → │    │ gateway → │    │           │    │           │
  │ their     │    │ their     │    │           │    │           │
  │ Slack     │    │ Telegram  │    │           │    │           │
  └───────────┘    └───────────┘    └───────────┘    └───────────┘
```

Each client box is fully isolated: own state volume, own model credentials, own
allowed-users list, own gateway token. Nothing is shared at runtime — that's
your security and billing boundary.

---

## 3. The tenant unit

One client deployment =

1. **A host** — start with a small VPS or a Docker container on your fleet host.
   Migrate low-traffic clients to **Daytona/Modal** later (hibernate when idle,
   near-zero cost between sessions — see `TERMINAL_LIFETIME_SECONDS`).
2. **An isolated state dir** — `~/.hermes` per client, mounted as `/opt/data`.
   This is the entire tenant: config, skills, memory, sessions, cron.
3. **A config layer** — `config.yaml` + env vars. Note the repo already bridges
   `model.*` config keys and `HERMES_MEMORY_PROVIDER` from env vars at Docker
   build/boot (see recent commits), so per-client config can be driven by env.
4. **A gateway** — `hermes gateway run`, wired to *the client's* Slack/Telegram
   bot token and *their* allowed-users list.
5. **Model credentials** — ideally the client's own provider key (you operate,
   they pay the model bill directly), or your key with metered pass-through.

The cleanest stamp of this today is a per-client `docker-compose.yml` derived
from the repo's, with a client-specific `~/.hermes` volume and `.env`.

---

## 4. Provisioning flow (what the main agent automates)

A "provision a new client" routine your main agent can own as a **skill**:

1. **Intake** — collect: client name, channels (Slack/Telegram/…), model
   provider + key, allowed users, working directory, branding.
2. **Allocate host** — pick container slot / VPS / Daytona workspace.
3. **Seed state** — copy the **golden template** `~/.hermes` (skills,
   personality, toolset, AGENTS.md) into the new tenant dir.
4. **Write config** — generate `config.yaml` + `.env` (model, memory provider,
   gateway tokens, allowed users) from the intake form.
5. **Harden** — dashboard bound to `127.0.0.1`; API server **off** unless needed
   (and then `API_SERVER_KEY` mandatory); per-client allowed-users enforced.
6. **Launch** — `docker compose up -d` (or `hermes gateway run` on the VPS).
7. **Smoke test** — main agent sends a test message through the client's channel
   and verifies a reply.
8. **Register** — append the client to your registry (host, channel, key ref,
   plan, start date) for monitoring + billing.

Steps 2–8 are scriptable; the main agent runs them via subagents so onboarding a
new client is one command/conversation, not a manual checklist.

---

## 5. Day-2 operations (recurring, where the money is)

Managed hosting is sold on *operations*, not the binary. A cron-driven routine
on your main agent should, per client:

- **Health** — gateway alive? last message processed? error rate?
- **Usage** — model tokens/spend per client (for billing + abuse detection).
- **Updates** — roll `hermes update` across the fleet on a cadence, after
  testing on a canary client.
- **Backups** — nightly snapshot of each `~/.hermes` (skills + memory are the
  irreplaceable client asset). The repo even pitches "nightly backups" as a
  built-in cron use case.
- **Reports** — weekly per-client digest (what the agent did, value delivered) —
  this is your renewal/retention artifact.

---

## 6. Security & isolation (this is what companies are buying)

Selling to companies means the security story *is* the product. Non-negotiables:

- **Hard tenant isolation.** Separate containers/VPSs and separate `~/.hermes`
  volumes per client. Never co-mingle state. Prefer separate hosts for clients
  with sensitive data.
- **Dashboard never public.** It stores API keys. Keep `--host 127.0.0.1`;
  remote access only via SSH tunnel or authenticated reverse proxy. The compose
  file's security notes spell this out — follow them verbatim.
- **API server off by default.** Only enable with `API_SERVER_KEY` set; review
  `docs/user-guide/api-server.md` before any internet-facing host.
- **Per-client allowed-users** on every gateway platform (DM pairing /
  allowed-users) so only the client's people can talk to their agent.
- **Secrets handling.** Per-client model keys in a vault, never in the repo,
  injected as env at boot. Drop root in containers (entrypoint already uses
  `gosu` + `HERMES_UID/GID`).
- **Command approval.** Keep Hermes' command-approval/allowlist conservative on
  client instances; document what the agent is permitted to execute.
- **Data handling contract.** Be explicit with clients about where their data
  and memory live, retention, and deletion on offboarding.

See `SECURITY.md` and the security docs before the first paid deployment.

---

## 7. Branding / legal

- **License:** MIT — you may use, modify, and **sell** the software. Keep the
  MIT `LICENSE` / attribution intact in the code you ship.
- **Trademark:** "Hermes" / Nous Research branding is **not** yours to sell
  under. White-label: your product name, your banner (`assets/`), your docs.
  Strip/replace user-facing "Hermes" branding in the gateway, TUI, and
  dashboard for client-facing surfaces.
- **Model provider terms:** if you resell model access, comply with each
  provider's commercial/reseller terms. Cleanest path early on is "bring your
  own key" — the client pays the provider, you operate.
- **Contracts:** MSA + per-client SOW covering uptime, data handling, support
  SLA, and offboarding (state export + deletion).

---

## 8. Pricing shape (starting point, not gospel)

Managed deploys bill like consulting + hosting, not like SaaS seats:

- **One-time onboarding** — intake, golden-template customization, channel +
  integration setup, training the client. This is most of your early revenue.
- **Monthly managed fee** — hosting, monitoring, updates, backups, support.
  Tier by # of channels, # of users, custom skills/integrations, SLA.
- **Model spend** — pass through (BYO key) or meter + margin.
- **Change requests** — new skills / integrations billed as add-ons.

Land with onboarding + retainer; expand via custom skills (which also deepen
lock-in).

---

## 9. Suggested build order

1. **Golden template** — take your current tuned `~/.hermes` (skills,
   personality, toolset, AGENTS.md) and freeze it as the seed. *(no new code)*
2. **Per-client compose + `.env` generator** — a script/template that stamps
   `docker-compose.yml` + `.env` from an intake form. *(thin wrapper over what
   ships)*
3. **Client registry** — `clients.yaml` (or small DB): host, channel, key ref,
   plan, dates.
4. **Provisioning skill** — teach the main agent the §4 flow so it runs
   onboarding end-to-end.
5. **Monitoring cron** — §5 health/usage/backup/report routine across the fleet.
6. **White-label pass** — rebrand client-facing surfaces (§7).
7. **First pilot client** — ideally free/cheap, to harden the runbook before you
   charge.

Start at 1–2 with **one** real (or pilot) client. Don't build the fleet
orchestrator before you've provisioned a single instance by hand and learned
where it hurts.

---

## 10. Open questions to resolve before building

- Hosting substrate: your own VPS fleet, a cloud (which?), or Daytona/Modal
  serverless from day one?
- BYO model key vs. you-resell-with-margin?
- Which channels do target companies actually want first (Slack? Telegram?)?
- Target client profile (size, industry, use case) — shapes the golden template.
- Final product name for the white-label.

Answer these and the next step is scaffolding items §9.1–§9.2.
