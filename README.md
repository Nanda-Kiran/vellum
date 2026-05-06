# Vellum

Vellum is an always-on AI finance controller for SMB/startup teams. It monitors Plaid, Stripe, Gmail, and Google Workspace, detects fraud/duplicate/policy issues, pushes actionable findings to Slack, and generates audit-ready summaries in Google Docs.

## Architecture

![Vellum architecture](./Architecture_Vellum.png)

## Project overview

- **Ingest + detect:** Scheduler-driven ingestion collects transactions/emails/expense rows and runs deterministic rules (duplicate, zombie SaaS, policy-cap, domain mismatch).
- **Agent orchestration:** A supervisor coordinates reconciliation, compliance, forensics enrichment, and reporting.
- **Slack-first operations:** Findings are posted as cards with `Why` and approval actions, plus CFO DM/app-mention chat for quick questions.
- **Trust ledger:** Findings/actions are persisted in SQLite for traceability, approvals, and reporting.
- **Audit output:** `/audit` generates a Google Doc with executive summary, total revenue saved, and business impact.

## Quickstart (clone and run)

### 1) Clone and install

```bash
git clone <your-repo-url>
cd vellum
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2) Configure environment

```bash
cp .env.example .env
```

Fill in `.env` with your own values:

- `GROQ_API_KEY`
- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `PLAID_CLIENT_ID`
- `PLAID_SECRET`
- `STRIPE_API_KEY`
- `GOOGLE_CREDENTIALS_PATH`

How to get each value:

- `GROQ_API_KEY`
  - Go to [Groq Console](https://console.groq.com/keys).
  - Create an API key.
  - Put it in `.env` as:
    - `GROQ_API_KEY=...`

- `SLACK_BOT_TOKEN`
  - Go to [Slack API Apps](https://api.slack.com/apps) -> your app -> **OAuth & Permissions**.
  - Install/Reinstall app to workspace.
  - Copy **Bot User OAuth Token** (`xoxb-...`).
  - Put it in `.env`:
    - `SLACK_BOT_TOKEN=xoxb-...`

- `SLACK_APP_TOKEN`
  - In Slack app settings -> **Basic Information** -> **App-Level Tokens**.
  - Create token with `connections:write` scope.
  - Copy token (`xapp-...`).
  - Put it in `.env`:
    - `SLACK_APP_TOKEN=xapp-...`

- `PLAID_CLIENT_ID` and `PLAID_SECRET`
  - Go to [Plaid Dashboard](https://dashboard.plaid.com/).
  - Use Sandbox credentials from Team Settings / API Keys.
  - Put in `.env`:
    - `PLAID_CLIENT_ID=...`
    - `PLAID_SECRET=...`
    - `PLAID_ENV=sandbox`

- `STRIPE_API_KEY`
  - Go to [Stripe Dashboard](https://dashboard.stripe.com/apikeys).
  - Use a **test** secret key (`sk_test_...`) for demos.
  - Put it in `.env`:
    - `STRIPE_API_KEY=sk_test_...`

- `GOOGLE_CREDENTIALS_PATH`
  - Create/download a local Google credential JSON file (OAuth user token JSON or service account JSON) with required scopes used by this app.
  - Save the file inside your local repo (recommended: `./secrets/google_token.json`, and keep it gitignored).
  - Put path in `.env`:
    - `GOOGLE_CREDENTIALS_PATH=./secrets/google_token.json`

Local file placement checklist:

- Keep secrets only in your local checkout:
  - `.env`
  - Google credential JSON file (path referenced by `GOOGLE_CREDENTIALS_PATH`)
- Do not commit these files to git.

Defaults that usually work as-is:

- `PLAID_ENV=sandbox`
- `VELLUM_DB_PATH=./vellum.db`
- `VELLUM_POLICY_PATH=./data/policy.md`

### 3) Start the app

```bash
.venv/bin/python -m uvicorn vellum.main:app
```

You should see:

- `scheduler.started`
- `slack.socket_mode.started`
- `Bolt app is running!`

### 4) (Optional) Run the live demo seeder

```bash
PYTHONPATH=. .venv/bin/python data/seed/live_demo_four_issues.py --reset-ledger
```

This seeds 4 scenarios and posts findings to Slack:

- Plaid recurring Datadog (zombie SaaS signal)
- Stripe duplicate Acme charges
- Gmail vendor-domain mismatch scenario
- Google Sheet policy-cap violation

## Slack usage

- Findings post to `SLACK_FINANCE_ALERTS_CHANNEL`.
- `Why` button returns LLM reasoning (with fallback when quota is exhausted).
- `Approve/Reject` appears for policy-cap findings.
- DM or mention the bot for CFO chat, for example:
  - `What's the most urgent thing you found today?`
- Run audit pack generation in Slack with:
  - `/audit last_30_days`
  - `/audit 2026-05`

### `/audit` Slack command

What it does:

- Triggers audit-pack generation via the app API.
- Returns a Google Doc URL when ready.

Examples:

- `/audit` -> defaults to `last_30_days`
- `/audit last_30_days`
- `/audit 2026-05` (year-month period)

## Slack app requirements

In your Slack app config:

- **Socket Mode** enabled
- **App Home**:
  - Messages tab enabled
  - "Allow users to send messages" enabled
- **Event Subscriptions** bot events include:
  - `app_mention`
  - `message.im`
- **Slash Commands**:
  - create `/audit`
  - request URL should point to your app endpoint if using HTTP mode
  - for this Socket Mode setup, keep the command configured in app + scopes and the Bolt handler will process it
- **OAuth scopes** include at least:
  - `chat:write`
  - `im:read`
  - `im:history`
  - `commands`

After changing scopes/events, reinstall the app to workspace.
