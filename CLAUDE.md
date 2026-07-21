# CLAUDE.md — working on this repo

This is a **personal fork of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)**,
kept as a near-exact mirror of upstream and deployed to Railway. For Hermes'
own codebase conventions and architecture, see `AGENTS.md` (upstream-owned) —
don't duplicate it here.

## Fork & sync model
- Remotes: `origin` = `Folken2/hermes-agent` (my fork), `upstream` = `NousResearch/hermes-agent`.
- **Goal: stay synced with upstream.** To update:
  ```bash
  git fetch upstream
  git rebase upstream/main       # replays our divergence commits on top
  git push --force-with-lease origin main
  ```
- **Intentional divergence from upstream = keep it minimal.** Currently just:
  - `Dockerfile`: the `VOLUME [ "/opt/data" ]` line is commented out — Railway's
    builder rejects Dockerfile `VOLUME` directives ("use Railway Volumes"), which
    fails the build before any instruction runs. Persistence comes from a Railway
    Volume mounted at `/opt/data` instead. **Do not re-add the VOLUME directive.**
- Old fork customizations were **dropped in favor of stock upstream** ("go native").
  Do **not** reintroduce them:
  - supermemory memory provider (needs SDK baked into the image; lazy installs are
    disabled in-container).
  - `HERMES_MODEL_PROVIDER` / `_BASE_URL` / `_DEFAULT` env-var bridge (upstream
    does not read these — model config comes from `config.yaml`/OpenRouter).
  - The old `docker/entrypoint.sh`-based startup (upstream uses s6-overlay `/init`).
  - These are preserved on the `backup/railway-work` branch if ever needed.

## Deployment (Railway)
- Project `aware-education`, service `hermes-agent`, environment `production`.
- Builds from this repo's `/Dockerfile` (s6-overlay; `/init` is PID 1).
- **Start command** (Railway service setting, not in repo):
  `/init /opt/hermes/docker/main-wrapper.sh gateway run`
  (must go through `/init` so s6 sets up the environment, incl. `s6-setuidgid`).
- **Volume** mounted at `/opt/data` (= `HERMES_HOME`) — the single source of truth
  for all runtime state.
- Public URL: `https://hermes-agent-production-2e60.up.railway.app` (dashboard + the
  Desktop app's "remote gateway" endpoint; behind basic auth).
- Model provider: **OpenRouter** (`OPENROUTER_API_KEY`). Dashboard exposed on port
  `8080` (`HERMES_DASHBOARD=1`, `HERMES_DASHBOARD_PORT=8080`, `PORT=8080`, basic-auth
  vars). All secrets live in Railway env vars — never commit them here.

## What lives where (do NOT put these in the repo)
- **Runtime state / config / persona live on the Railway volume `/opt/data`, NOT git:**
  `config.yaml`, `.env`, `SOUL.md` (agent persona/preferences), `auth.json`,
  `state.db` / `kanban.db` (SQLite). Editing these never touches the repo and never
  conflicts with upstream.
- Agent persona and "how I use Hermes" preferences → `/opt/data/SOUL.md` (edit via
  Railway Console or the Desktop app), **not** this file.

## GitHub auth caveat
- Two `gh` accounts are configured: `Folken2` (owns the fork; use for pushes) and
  `albertf-sapira` (Sapira work). `Folken2` needs the `workflow` scope to push
  changes that touch `.github/workflows/**` (e.g. large upstream syncs):
  `gh auth switch -u Folken2 && gh auth refresh -h github.com -s workflow`.

## My preferences (fill in)
- <!-- e.g. tone, when to ask before acting, languages/units, PR/commit style -->
