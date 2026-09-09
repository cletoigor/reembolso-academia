# reembolso-academia

A personal automation that submits a monthly gym-membership reimbursement
claim to an employer via their Google Form, so it doesn't have to be filled in by
hand every month.

## Architecture

![Architecture](docs/architecture.svg)

The thing worth noticing: launchd does not run a Python script here — it runs an agent.
`run.sh` invokes `claude -p` with a fixed MCP tool allowlist, and `ptax.py` and
`enviar_dedicado.py` are that agent's tools. Two gates are enforced in code (the
`enviados.json` idempotency check and `anexo_presente()`, which verifies the upload
actually attached); the USD cap is enforced only in the agent's prose, which is why it
is drawn as a soft gate.

## What it does

Once a month, the flow is:

1. Fetch the gym receipt from Gmail (done at the orchestration layer, see
   [Automation](#automation) below — not by the Python code in this repo).
2. Convert the receipt's BRL amount to USD using the Central Bank of
   Brazil's PTAX exchange rate (`ptax.py`), applying the reimbursement's
   USD 20/month cap.
3. Fill out and submit the reimbursement Google Form with Playwright:
   name, email, gym name, amount, and the receipt file upload.
4. Record the month in `enviados.json` so a re-run in the same month is a
   no-op instead of a duplicate submission.

## Files

| File | Role |
|---|---|
| `enviar_dedicado.py` | Current production script. Drives a dedicated, persistent Chrome profile (`chrome-dedicado/`) to fill and submit the form. Detects login walls, fills form fields with a JS snippet dispatching native input events (Google Forms needs this to register the values), uploads the receipt through the form's file picker, and confirms the upload actually attached before submitting. |
| `login_dedicado.py` | One-time interactive login: opens the dedicated Chrome profile and waits for a human to log in manually — the script never types the password itself — then verifies the session persisted. |
| `ptax.py` | Standalone module/CLI that fetches the USD/BRL PTAX "sell" rate from the Central Bank's Olinda OData API, walking back up to 7 days to skip weekends/holidays with no quote. Shared with the `/nf-mensal` automation so both stay in sync. Usable on its own: `python3 ptax.py [YYYY-MM-DD]`. |
| `run.sh` | Cron entry point. Invokes the Claude Code CLI (`claude -p`) with a `/reembolso-academia` skill prompt and a restricted tool allowlist. |
| `preencher_form.py`, `enviar_oneshot.py` | Earlier alternate implementations (different profile-management strategies) kept for reference; superseded by `enviar_dedicado.py`. |
| `enviar_perfil_real.py` | **Retired**, guarded by a hard exit at import time. It drove the user's real personal Chrome profile via remote debugging; that broke saved logins across the browser, which is why the design moved to an isolated, dedicated profile instead. |

## Setup

```bash
pip install playwright requests
playwright install chrome
```

Establish the persistent session once:

```bash
python3 login_dedicado.py
```

A Chrome window opens; log in manually. The session is saved to
`chrome-dedicado/` and lasts for months without needing to repeat this step.

## Usage

```bash
python3 enviar_dedicado.py --valor 20.00 --comprovante /path/to/receipt.pdf
python3 enviar_dedicado.py --valor 20.00 --comprovante /path/to/receipt.pdf --dry-run    # checks login/fields, sends nothing
python3 enviar_dedicado.py --valor 20.00 --comprovante /path/to/receipt.pdf --headless   # no visible window
python3 enviar_dedicado.py --valor 20.00 --comprovante /path/to/receipt.pdf --force      # bypass the enviados.json idempotency guard
```

`ptax.py` can be run standalone to check the exchange rate for any date:

```bash
python3 ptax.py            # most recent available rate
python3 ptax.py 2026-08-06 # rate for a specific date
```

## Automation

A monthly cron job runs `run.sh`, which invokes the Claude Code CLI running
the `/reembolso-academia` skill. That skill layer (not this repo's Python
code) searches Gmail for the month's receipt, calls `ptax.py` for the
conversion rate, runs `enviar_dedicado.py` to submit the form, then posts a
Slack notification and logs a Google Calendar event.

## Notes

- No automated tests — this is a small personal script, verified by
  `--dry-run` runs and manual checks.
- `chrome-dedicado/`, `chrome-profile/`, `.env`, `enviados.json`, and
  `cron.log` are all gitignored: they hold local session cookies, credential
  placeholders, and personal submission history that shouldn't be committed
  or shared.
