Built and tested in `C:\tmp\skills-eval\arm-a\t13-r1`. Summary of what's there:

**`sales_summary_agent.py`** — stdlib-only Python script that:
- Reads a sales CSV (flexible column matching: `product`, `category`, `quantity`/`unit_price` or a `total`/`revenue` column, optional `order_id`)
- Computes total revenue, orders, units, avg order value, revenue by category, top-N products, and an optional vs.-yesterday delta
- Emails the team a plain-text + HTML summary over SMTP (STARTTLS or SSL)
- On failure (missing CSV, bad parse, SMTP error), logs to `logs/agent.log` and emails the team a short failure alert instead of failing silently
- Supports `--dry-run` (prints instead of sending) and `--date` for testing/backfills

**`config.json`** — CSV path, SMTP server, recipients, etc. (placeholders — needs your real values). SMTP password intentionally isn't stored here; it's read from the `SALES_AGENT_SMTP_PASSWORD` env var.

**`setup_task.ps1`** — registers a Windows Scheduled Task to run it every morning (default 7:00 AM, `-Time` to override).

**`sample_sales.csv`** + **`README.md`** — example data and full setup/testing/scheduling instructions.

I verified both the happy path (dry-run against `sample_sales.csv`, math checks out) and the failure/alert path (missing CSV → logs error, exits 1, sends alert email) actually run correctly.

Assumptions I made since these weren't specified — flag if wrong:
- **Email transport**: generic SMTP (Gmail/Office365-style), not a specific provider or API (e.g., SendGrid, SES). Easy to swap if the team uses something else.
- **Scheduling**: Windows Task Scheduler, since the CSV lives on this local machine — not a cloud/CI cron, which couldn't reach a local file.
- **CSV schema**: order-level rows with product/category/quantity/price, not pre-aggregated daily totals.

Still needed from you before this actually sends mail: real SMTP credentials/host in `config.json`, the real recipient list, and the real CSV path (or `csv_path_template` if you keep one file per day, e.g. `sales_{date}.csv`).

---

## Files written by the session

### `config.json`

````json
{
  "csv_path": "C:/tmp/skills-eval/arm-a/t13-r1/sample_sales.csv",
  "csv_path_template": null,
  "date_format": "%Y-%m-%d",

  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "use_tls": true,
  "smtp_user": "reports@yourcompany.com",
  "sender_name": "Sales Reporting Bot",
  "sender_email": "reports@yourcompany.com",

  "recipients": ["team@yourcompany.com"],

  "subject_prefix": "Daily Sales Summary",
  "top_n_products": 5,
  "compare_previous_day": true,
  "alert_recipients_on_failure": true
}

````

### `logs/agent.log`

````log
2026-09-15 07:47:20,973 [INFO] Reading sales CSV: C:\tmp\skills-eval\arm-a\t13-r1\sample_sales.csv
2026-09-15 07:47:20,981 [INFO] [DRY RUN] Would send email to: ['team@yourcompany.com']
2026-09-15 07:47:20,982 [INFO] Done.
2026-09-15 07:47:25,605 [INFO] Reading sales CSV: C:\tmp\skills-eval\arm-a\t13-r1\sample_sales.csv
2026-09-15 07:47:25,610 [INFO] [DRY RUN] Would send email to: ['team@yourcompany.com']
2026-09-15 07:47:25,611 [INFO] Done.
2026-09-15 07:47:32,104 [INFO] Reading sales CSV: C:\tmp\skills-eval\arm-a\t13-r1\does_not_exist.csv
2026-09-15 07:47:32,105 [ERROR] Failed to generate/send daily sales summary
Traceback (most recent call last):
  File "C:\tmp\skills-eval\arm-a\t13-r1\sales_summary_agent.py", line 370, in main
    raise FileNotFoundError(f"CSV file not found: {csv_path}")
FileNotFoundError: CSV file not found: C:\tmp\skills-eval\arm-a\t13-r1\does_not_exist.csv
2026-09-15 07:47:32,108 [INFO] [DRY RUN] Would send email to: ['team@yourcompany.com']

````

### `README.md`

````md
# Daily Sales Summary Agent

Reads the day's sales CSV, builds a summary (total revenue, units sold,
revenue by category, top products, and a vs.-yesterday comparison), and
emails it to the team every morning. Pure Python standard library — no
`pip install` required.

## Files

| File | Purpose |
|---|---|
| `sales_summary_agent.py` | The agent. Reads CSV → builds report → sends email. |
| `config.json` | Your settings: CSV location, SMTP server, recipients. **Edit this.** |
| `sample_sales.csv` | Example CSV matching the expected schema, for testing. |
| `setup_task.ps1` | Registers a Windows Scheduled Task to run it every morning. |
| `logs/agent.log` | Created on first run. Check here if a scheduled run didn't arrive. |

## 1. Expected CSV schema

Column names are matched case-insensitively and a few synonyms are
accepted (see `REQUIRED_COLUMNS_ANY_OF` in the script if you need to add
more). At minimum you need a `product` column and either a `total`
(revenue) column or both `quantity` and `unit_price`:

```csv
date,order_id,product,category,quantity,unit_price
2026-09-14,1001,Wireless Mouse,Electronics,3,19.99
```

If your export uses different column names, either rename them in the
export or add the alias to `REQUIRED_COLUMNS_ANY_OF` in
`sales_summary_agent.py`.

## 2. Configure

Edit `config.json`:

- `csv_path` — full path to the CSV that gets refreshed daily, **or**
- `csv_path_template` — a path containing `{date}`, e.g.
  `C:/sales/exports/sales_{date}.csv`, if you keep one file per day
  (also enables the vs.-yesterday comparison).
- `smtp_host` / `smtp_port` / `smtp_user` — your mail provider's SMTP
  settings (port 587 = STARTTLS, port 465 = SSL). Examples:
  - Gmail: `smtp.gmail.com`, port `587`, requires an [App Password](https://myaccount.google.com/apppasswords) (not your normal password).
  - Office 365: `smtp.office365.com`, port `587`.
- `recipients` — list of team email addresses.

**Do not put the SMTP password in `config.json`.** Set it as an
environment variable instead:

```powershell
setx SALES_AGENT_SMTP_PASSWORD "your-app-password"
```

Open a new terminal after running `setx` for it to take effect (or use
`setup_task.ps1`, which prints a reminder).

## 3. Test it

```powershell
python sales_summary_agent.py --dry-run
```

This prints the report to the console instead of emailing it — use it
to confirm the CSV parses correctly before sending real email. Try it
against a specific date/CSV with `--date 2026-09-14`. Once it looks
right, drop `--dry-run` to actually send.

If something goes wrong (CSV missing, bad SMTP credentials, etc.), the
agent logs the error to `logs/agent.log` and — unless
`alert_recipients_on_failure` is `false` in `config.json` — emails the
team a short "report failed" alert instead of silently doing nothing.

## 4. Schedule it to run every morning

From this folder, in PowerShell:

```powershell
.\setup_task.ps1               # registers a daily 7:00 AM run
.\setup_task.ps1 -Time 06:30   # or pick your own time
```

This creates a Windows Scheduled Task named `DailySalesSummaryAgent`
that runs `python sales_summary_agent.py` daily. Manage it later with:

```powershell
Start-ScheduledTask -TaskName DailySalesSummaryAgent   # run it now
Get-ScheduledTaskInfo -TaskName DailySalesSummaryAgent # last run result
Unregister-ScheduledTask -TaskName DailySalesSummaryAgent -Confirm:$false
```

**Note:** by default the task only runs while the registering user is
logged on. If this needs to run on a server / unattended machine that's
sometimes logged out, open Task Scheduler GUI → find the task →
Properties → General tab → check "Run whether user is logged on or
not" (it will prompt for the Windows account password once).

## Customizing the summary

- `top_n_products` in `config.json` controls how many products are
  listed.
- `compare_previous_day: false` disables the vs.-yesterday line (only
  applies when using `csv_path_template`, since a static `csv_path`
  has no way to find "yesterday's" file).
- The email is sent as both plain text and HTML (most clients show the
  HTML version with tables); edit `build_email_body()` in the script to
  change formatting.

````

### `sales_summary_agent.py`

````py
#!/usr/bin/env python3
"""
Daily Sales Summary Agent
==========================

Reads a daily sales CSV, builds a summary (total revenue, units sold,
revenue by category, top products, and a comparison to the previous day
when available), and emails it to the team over SMTP.

Designed to run unattended once a day via Windows Task Scheduler
(see setup_task.ps1). Uses only the Python standard library.

Usage:
    python sales_summary_agent.py                  # run for today, send email
    python sales_summary_agent.py --dry-run         # print the report, don't send
    python sales_summary_agent.py --date 2026-09-14 # run for a specific date
    python sales_summary_agent.py --config C:\\path\\to\\config.json

Expected CSV columns (case-insensitive, order doesn't matter):
    date, order_id, product, category, quantity, unit_price
    (a "total" column is used instead of quantity*unit_price if present)

See README.md for full setup instructions.
"""

import argparse
import csv
import json
import logging
import os
import smtplib
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.json"
LOG_DIR = SCRIPT_DIR / "logs"

REQUIRED_COLUMNS_ANY_OF = {
    "product": ["product", "item", "product_name"],
    "category": ["category", "product_category"],
    "quantity": ["quantity", "qty", "units"],
    "unit_price": ["unit_price", "price", "unit price"],
    "total": ["total", "revenue", "amount", "line_total"],
    "order_id": ["order_id", "order", "order_number", "invoice_id"],
    "date": ["date", "order_date", "sale_date"],
}


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / "agent.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. Copy config.json and fill it in."
        )
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    required = ["smtp_host", "smtp_port", "smtp_user", "recipients"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        raise ValueError(f"Config is missing required field(s): {', '.join(missing)}")
    if not config.get("csv_path") and not config.get("csv_path_template"):
        raise ValueError("Config must set either 'csv_path' or 'csv_path_template'")
    return config


def resolve_csv_path(config: dict, for_date: datetime) -> Path:
    date_format = config.get("date_format", "%Y-%m-%d")
    if config.get("csv_path_template"):
        path_str = config["csv_path_template"].replace(
            "{date}", for_date.strftime(date_format)
        )
        return Path(path_str)
    return Path(config["csv_path"])


def _find_column(fieldnames, candidates):
    lookup = {name.strip().lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    return None


def read_sales_rows(csv_path: Path):
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header row: {csv_path}")

        columns = {
            key: _find_column(reader.fieldnames, candidates)
            for key, candidates in REQUIRED_COLUMNS_ANY_OF.items()
        }
        if not columns["product"]:
            raise ValueError(
                f"Could not find a 'product' column in {csv_path}. "
                f"Found columns: {reader.fieldnames}"
            )
        if not columns["total"] and not (columns["quantity"] and columns["unit_price"]):
            raise ValueError(
                f"CSV must have either a total/revenue column, or both "
                f"quantity and unit_price columns. Found columns: {reader.fieldnames}"
            )

        rows = []
        for i, raw_row in enumerate(reader, start=2):  # start=2: header is line 1
            try:
                product = raw_row[columns["product"]].strip()
                category = (
                    raw_row[columns["category"]].strip()
                    if columns["category"]
                    else "Uncategorized"
                )
                quantity = (
                    float(raw_row[columns["quantity"]])
                    if columns["quantity"] and raw_row.get(columns["quantity"])
                    else None
                )
                unit_price = (
                    float(raw_row[columns["unit_price"]])
                    if columns["unit_price"] and raw_row.get(columns["unit_price"])
                    else None
                )
                if columns["total"] and raw_row.get(columns["total"]):
                    revenue = float(raw_row[columns["total"]])
                elif quantity is not None and unit_price is not None:
                    revenue = quantity * unit_price
                else:
                    raise ValueError("no usable revenue/quantity+price fields")

                rows.append(
                    {
                        "product": product or "Unknown",
                        "category": category or "Uncategorized",
                        "quantity": quantity if quantity is not None else 1.0,
                        "revenue": revenue,
                        "order_id": raw_row.get(columns["order_id"], "")
                        if columns["order_id"]
                        else "",
                    }
                )
            except (ValueError, KeyError) as e:
                logging.warning("Skipping unparseable row %d in %s: %s", i, csv_path, e)
    return rows


def summarize(rows, top_n=5):
    total_revenue = sum(r["revenue"] for r in rows)
    total_units = sum(r["quantity"] for r in rows)
    order_ids = {r["order_id"] for r in rows if r["order_id"]}
    order_count = len(order_ids) if order_ids else len(rows)

    revenue_by_category = defaultdict(float)
    revenue_by_product = defaultdict(float)
    units_by_product = defaultdict(float)
    for r in rows:
        revenue_by_category[r["category"]] += r["revenue"]
        revenue_by_product[r["product"]] += r["revenue"]
        units_by_product[r["product"]] += r["quantity"]

    top_products = sorted(
        revenue_by_product.items(), key=lambda kv: kv[1], reverse=True
    )[:top_n]
    top_products = [
        (name, revenue, units_by_product[name]) for name, revenue in top_products
    ]

    return {
        "row_count": len(rows),
        "total_revenue": total_revenue,
        "total_units": total_units,
        "order_count": order_count,
        "avg_order_value": (total_revenue / order_count) if order_count else 0.0,
        "revenue_by_category": dict(
            sorted(revenue_by_category.items(), key=lambda kv: kv[1], reverse=True)
        ),
        "top_products": top_products,
    }


def build_email_body(report_date, summary, previous_summary=None):
    def money(v):
        return f"${v:,.2f}"

    delta_line = ""
    if previous_summary and previous_summary["total_revenue"] > 0:
        change = summary["total_revenue"] - previous_summary["total_revenue"]
        pct = change / previous_summary["total_revenue"] * 100
        arrow = "up" if change >= 0 else "down"
        delta_line = f"That's {arrow} {abs(pct):.1f}% vs. the previous day ({money(previous_summary['total_revenue'])}).\n"

    lines = [
        f"Daily Sales Summary - {report_date.strftime('%A, %B %d, %Y')}",
        "=" * 50,
        "",
        f"Total revenue:     {money(summary['total_revenue'])}",
        f"Orders:            {summary['order_count']}",
        f"Units sold:        {int(summary['total_units'])}",
        f"Avg order value:   {money(summary['avg_order_value'])}",
        "",
        delta_line.strip(),
        "",
        "Revenue by category:",
    ]
    for cat, rev in summary["revenue_by_category"].items():
        lines.append(f"  - {cat}: {money(rev)}")

    lines += ["", f"Top {len(summary['top_products'])} products by revenue:"]
    for name, rev, units in summary["top_products"]:
        lines.append(f"  - {name}: {money(rev)} ({int(units)} units)")

    lines += ["", "-- Sent automatically by the daily sales summary agent."]
    text_body = "\n".join(l for l in lines if l is not None)

    def esc(s):
        return (
            str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    category_rows = "".join(
        f"<tr><td>{esc(cat)}</td><td style='text-align:right'>{money(rev)}</td></tr>"
        for cat, rev in summary["revenue_by_category"].items()
    )
    product_rows = "".join(
        f"<tr><td>{esc(name)}</td><td style='text-align:right'>{money(rev)}</td>"
        f"<td style='text-align:right'>{int(units)}</td></tr>"
        for name, rev, units in summary["top_products"]
    )
    html_body = f"""\
<html><body style="font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;">
<h2>Daily Sales Summary &mdash; {esc(report_date.strftime('%A, %B %d, %Y'))}</h2>
<table cellpadding="6">
  <tr><td><b>Total revenue</b></td><td>{money(summary['total_revenue'])}</td></tr>
  <tr><td><b>Orders</b></td><td>{summary['order_count']}</td></tr>
  <tr><td><b>Units sold</b></td><td>{int(summary['total_units'])}</td></tr>
  <tr><td><b>Avg order value</b></td><td>{money(summary['avg_order_value'])}</td></tr>
</table>
{f"<p>{esc(delta_line.strip())}</p>" if delta_line.strip() else ""}
<h3>Revenue by category</h3>
<table cellpadding="6" style="border-collapse:collapse;">
  <tr><th align="left">Category</th><th align="right">Revenue</th></tr>
  {category_rows}
</table>
<h3>Top products by revenue</h3>
<table cellpadding="6" style="border-collapse:collapse;">
  <tr><th align="left">Product</th><th align="right">Revenue</th><th align="right">Units</th></tr>
  {product_rows}
</table>
<p style="color:#888;font-size:12px;">Sent automatically by the daily sales summary agent.</p>
</body></html>
"""
    return text_body, html_body


def send_email(config, subject, text_body, html_body, dry_run=False):
    recipients = config["recipients"]
    sender_name = config.get("sender_name", "Sales Reporting Bot")
    sender_email = config.get("sender_email", config["smtp_user"])

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    if dry_run:
        logging.info("[DRY RUN] Would send email to: %s", recipients)
        print("\n" + "=" * 60)
        print(f"SUBJECT: {subject}")
        print(f"TO: {', '.join(recipients)}")
        print("=" * 60)
        print(text_body)
        return

    password = os.environ.get("SALES_AGENT_SMTP_PASSWORD", config.get("smtp_password", ""))
    if not password:
        raise RuntimeError(
            "No SMTP password found. Set the SALES_AGENT_SMTP_PASSWORD environment "
            "variable (preferred) or 'smtp_password' in config.json."
        )

    host = config["smtp_host"]
    port = int(config["smtp_port"])
    use_tls = config.get("use_tls", True)

    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        if use_tls:
            server.starttls()

    try:
        server.login(config["smtp_user"], password)
        server.sendmail(sender_email, recipients, msg.as_string())
        logging.info("Email sent to %s", recipients)
    finally:
        server.quit()


def send_failure_alert(config, report_date, error_message, dry_run=False):
    if not config.get("alert_recipients_on_failure", True):
        return
    subject = f"[ACTION NEEDED] Daily sales summary failed - {report_date.strftime('%Y-%m-%d')}"
    text = (
        f"The daily sales summary agent could not generate today's report.\n\n"
        f"Date: {report_date.strftime('%Y-%m-%d')}\n"
        f"Error: {error_message}\n\n"
        f"Check the CSV file location and log file at logs/agent.log."
    )
    html = f"<p>{text.replace(chr(10), '<br>')}</p>"
    try:
        send_email(config, subject, text, html, dry_run=dry_run)
    except Exception as e:
        logging.error("Also failed to send failure alert email: %s", e)


def main():
    parser = argparse.ArgumentParser(description="Daily sales summary agent")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to config.json"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Report date as YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the report instead of emailing it",
    )
    args = parser.parse_args()

    setup_logging()
    report_date = (
        datetime.strptime(args.date, "%Y-%m-%d") if args.date else datetime.now()
    )

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logging.error("Config error: %s", e)
        sys.exit(1)

    try:
        csv_path = resolve_csv_path(config, report_date)
        logging.info("Reading sales CSV: %s", csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        rows = read_sales_rows(csv_path)
        if not rows:
            raise ValueError(f"No usable rows found in {csv_path}")

        summary = summarize(rows, top_n=config.get("top_n_products", 5))

        previous_summary = None
        if config.get("compare_previous_day", True):
            try:
                prev_date = report_date - timedelta(days=1)
                prev_csv_path = resolve_csv_path(config, prev_date)
                if prev_csv_path.exists() and prev_csv_path != csv_path:
                    previous_summary = summarize(read_sales_rows(prev_csv_path))
            except Exception as e:
                logging.warning("Could not build previous-day comparison: %s", e)

        text_body, html_body = build_email_body(report_date, summary, previous_summary)
        subject = (
            f"{config.get('subject_prefix', 'Daily Sales Summary')} - "
            f"{report_date.strftime('%Y-%m-%d')}"
        )
        send_email(config, subject, text_body, html_body, dry_run=args.dry_run)
        logging.info("Done.")

    except Exception as e:
        logging.exception("Failed to generate/send daily sales summary")
        send_failure_alert(config, report_date, str(e), dry_run=args.dry_run)
        sys.exit(1)


if __name__ == "__main__":
    main()

````

### `sample_sales.csv`

````csv
date,order_id,product,category,quantity,unit_price
2026-09-14,1001,Wireless Mouse,Electronics,3,19.99
2026-09-14,1001,USB-C Cable,Electronics,2,9.99
2026-09-14,1002,Notebook,Office Supplies,10,2.50
2026-09-14,1003,Standing Desk,Furniture,1,349.00
2026-09-14,1004,Wireless Mouse,Electronics,1,19.99
2026-09-14,1005,Desk Lamp,Furniture,4,24.99
2026-09-14,1006,Notebook,Office Supplies,5,2.50
2026-09-14,1007,Mechanical Keyboard,Electronics,2,79.99
2026-09-14,1008,Stapler,Office Supplies,3,6.49
2026-09-14,1009,Standing Desk,Furniture,2,349.00

````

### `setup_task.ps1`

````ps1
<#
.SYNOPSIS
    Registers a Windows Scheduled Task that runs the daily sales summary
    agent every morning.

.DESCRIPTION
    Run this once (as the user who should own the task) to install the
    schedule. Re-run it any time to update the trigger time.

.PARAMETER Time
    Local time to run each day, in 24h HH:mm format. Default: 07:00.

.PARAMETER TaskName
    Name of the scheduled task. Default: "DailySalesSummaryAgent".

.EXAMPLE
    .\setup_task.ps1
    .\setup_task.ps1 -Time 06:30
#>

param(
    [string]$Time = "07:00",
    [string]$TaskName = "DailySalesSummaryAgent"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentScript = Join-Path $ScriptDir "sales_summary_agent.py"

$PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonPath) {
    Write-Error "python.exe not found on PATH. Install Python 3 and ensure 'python' works in a new terminal, then re-run this script."
    exit 1
}

if (-not (Test-Path $AgentScript)) {
    Write-Error "Could not find sales_summary_agent.py next to this script ($ScriptDir)."
    exit 1
}

$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$AgentScript`"" -WorkingDirectory $ScriptDir
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Reads the daily sales CSV and emails the team a summary." `
    -Force

Write-Host "Scheduled task '$TaskName' registered to run daily at $Time."
Write-Host "It runs: `"$PythonPath`" `"$AgentScript`""
Write-Host ""
Write-Host "NOTE: the SMTP password must be available to the task at run time."
Write-Host "Set it as a persistent machine/user environment variable, e.g.:"
Write-Host "    setx SALES_AGENT_SMTP_PASSWORD `"your-app-password`""
Write-Host "(open a new terminal after running setx, then re-check with a manual test run)."
Write-Host ""
Write-Host "Test it now with:  python `"$AgentScript`" --dry-run"
Write-Host "Run it on demand with: Start-ScheduledTask -TaskName $TaskName"

````
