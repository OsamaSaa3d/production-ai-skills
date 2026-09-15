Wrote the tool to `C:\tmp\skills-eval\arm-a\t01-r1\orders_qa.py` (plus `requirements.txt`). It syntax-checks cleanly; not run against a live DB/API since neither is configured here.

## How it works

1. **`ask(question)`** sends the English question to Claude (`claude-opus-5`) with a system prompt describing the exact `orders` schema and a single tool, `run_sql_query`.
2. Claude replies with a `SELECT`/`WITH` query via that tool. The **Tool Runner** (`client.beta.messages.tool_runner`) drives the call → execute → feed-results-back loop for you — no manual `while` loop.
3. Before touching Postgres, `_validate_sql` rejects anything that isn't a single, `orders`-only read query (regex-blocks `INSERT/DROP/GRANT/pg_sleep/...`, blocks multi-statement injection via `;`, checks referenced tables against an allowlist).
4. The query is wrapped as a subquery with a hard outer `LIMIT 201` regardless of what Claude wrote, run with `statement_timeout=5s` on a `readonly=True` connection, so even a bug or a jailbroken query can't run long, mutate anything, or flood the context.
5. Rows come back as JSON; Claude reads them and writes a plain-English answer. If the query errors or the model's phrasing is off, Claude sees the error and can self-correct on the next loop turn.

## Safety notes (important — please act on these before production use)

- **The real security boundary is the DB role**, not this code: create a Postgres user with `GRANT SELECT ON orders` only (see the docstring at the top of the file for the exact SQL). Everything else here is defense-in-depth on top of that grant, not a replacement for it.
- I assumed a **single-table, reporting-only** use case. If you need writes or multi-table joins later, both the allowlist and system prompt need deliberate updates — don't just widen the regex.
- `customer_email` is a raw column the model can select; if this tool is exposed to end users (not just internal staff), you likely want to either strip/mask emails from tool results or restrict who can invoke this.
- Run it: `pip install -r requirements.txt`, set `DATABASE_URL` (read-only DSN) and `ANTHROPIC_API_KEY` (or `ant auth login`), then `python orders_qa.py "How much revenue came from shipped orders last week?"`.

---

## Files written by the session

### `orders_qa.py`

````py
"""
Plain-English Q&A over a Postgres `orders` table, powered by Claude.

Flow: user asks a question in English -> Claude writes a read-only SQL query
via a tool call -> we validate + sandbox-execute it against Postgres -> the
rows go back to Claude -> Claude answers in plain English.

Schema assumed:
    orders(id INTEGER PK, customer_email TEXT, status TEXT,
           total_usd NUMERIC, placed_at TIMESTAMP)

Setup
-----
    pip install anthropic psycopg2-binary sqlparse

    # Recommended: a DB role that can only read the orders table, so a bug
    # or a jailbroken query can't do anything Postgres itself doesn't allow:
    #
    #   CREATE ROLE orders_qa_readonly LOGIN PASSWORD '...';
    #   GRANT CONNECT ON DATABASE yourdb TO orders_qa_readonly;
    #   GRANT USAGE ON SCHEMA public TO orders_qa_readonly;
    #   GRANT SELECT ON public.orders TO orders_qa_readonly;
    #
    # This is the real security boundary. Everything else in this file
    # (statement validation, LIMIT wrapping, statement_timeout) is
    # defense-in-depth on top of it, not a substitute for it.

    export DATABASE_URL="postgresql://orders_qa_readonly:...@localhost:5432/yourdb"
    export ANTHROPIC_API_KEY="sk-ant-..."   # or `ant auth login`

    python orders_qa.py "How much revenue came from shipped orders last week?"
"""

from __future__ import annotations

import os
import re
import sys
import json
import decimal
import datetime

import psycopg2
import psycopg2.extras
import sqlparse

import anthropic
from anthropic import beta_tool

MODEL = "claude-opus-5"

# Only these tables may appear in a generated query. Add more here (and to
# the system prompt / DB grants) if the tool ever needs to join other tables.
ALLOWED_TABLES = {"orders"}

# Keywords that have no business in a read-only reporting query. Checked as
# whole words so this doesn't false-positive on things like a column named
# "created_at".
FORBIDDEN_KEYWORDS = re.compile(
    r"\b("
    r"insert|update|delete|merge|upsert|"
    r"drop|alter|truncate|create|comment|"
    r"grant|revoke|"
    r"copy|call|do|vacuum|reindex|cluster|"
    r"listen|notify|execute|prepare|deallocate|"
    r"pg_sleep|pg_read_file|pg_ls_dir|dblink"
    r")\b",
    re.IGNORECASE,
)

MAX_ROWS = 200
STATEMENT_TIMEOUT_MS = 5_000

SYSTEM_PROMPT = """\
You are a data analyst answering plain-English questions about a company's
orders using a Postgres database.

The only table available is:

    orders(
        id             integer primary key,
        customer_email text,
        status         text,       -- e.g. 'pending', 'shipped', 'cancelled', 'refunded'
        total_usd       numeric,   -- order total in US dollars
        placed_at       timestamp  -- when the order was placed
    )

To answer a question, call the `run_sql_query` tool with a single read-only
PostgreSQL query (SELECT, or WITH ... SELECT). Rules:

- Only ever query the `orders` table. Never write INSERT/UPDATE/DELETE/DDL -
  you only have read access anyway, so anything else will simply fail.
- Prefer aggregates (COUNT, SUM, AVG, date_trunc, ...) over pulling raw rows
  when the question asks for a total, average, or trend.
- Use explicit date ranges (e.g. placed_at >= now() - interval '7 days')
  rather than vague language.
- If a query fails or returns something unexpected, look at the error and
  try a corrected query rather than giving up after one attempt.
- When you have enough information, answer the user's question directly in
  plain English. Mention the concrete numbers you found. Do not dump raw
  SQL or a raw result table at the user unless they asked for it.
- If the question can't be answered from this table (e.g. it asks about
  products, inventory, or anything outside orders), say so plainly instead
  of guessing.
"""


class QueryRejected(Exception):
    """Raised when a generated query fails safety validation before it ever
    reaches the database."""


def _get_connection():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("Set DATABASE_URL to a read-only Postgres connection string.")
    conn = psycopg2.connect(dsn)
    # Belt-and-suspenders: even if the DB role somehow has write access,
    # refuse to let this process commit any change.
    conn.set_session(readonly=True, autocommit=False)
    return conn


def _validate_sql(sql: str) -> str:
    """Validate that `sql` is a single, read-only SELECT touching only
    ALLOWED_TABLES. Returns the cleaned statement or raises QueryRejected."""
    cleaned = sqlparse.format(sql, strip_comments=True).strip().rstrip(";").strip()
    if not cleaned:
        raise QueryRejected("Empty query.")

    statements = [s for s in sqlparse.split(cleaned) if s.strip()]
    if len(statements) != 1:
        raise QueryRejected("Only a single SQL statement is allowed.")

    parsed = sqlparse.parse(cleaned)[0]
    stmt_type = parsed.get_type()
    if stmt_type not in ("SELECT", "UNKNOWN"):  # WITH ... SELECT parses as UNKNOWN in sqlparse
        raise QueryRejected(f"Only SELECT queries are allowed, got: {stmt_type}")
    if not re.match(r"^\s*(select|with)\b", cleaned, re.IGNORECASE):
        raise QueryRejected("Query must start with SELECT or WITH.")

    if FORBIDDEN_KEYWORDS.search(cleaned):
        raise QueryRejected("Query contains a disallowed keyword.")

    referenced = set(
        m.lower() for m in re.findall(r"\b(?:from|join)\s+([a-zA-Z_][\w]*)", cleaned, re.IGNORECASE)
    )
    if not referenced:
        raise QueryRejected("Could not determine which table(s) the query reads from.")
    if not referenced.issubset(ALLOWED_TABLES):
        raise QueryRejected(
            f"Query references disallowed table(s): {sorted(referenced - ALLOWED_TABLES)}"
        )

    return cleaned


def _json_safe(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def _run_query(sql: str) -> str:
    """Validate, sandbox, and execute `sql`; return a JSON string result for
    the model, or raise QueryRejected / psycopg2.Error on failure."""
    cleaned = _validate_sql(sql)

    # Enforce a hard row cap no matter what the model wrote, by treating its
    # query as a subquery and applying our own outer LIMIT.
    wrapped = f"SELECT * FROM ({cleaned}) AS _q LIMIT {MAX_ROWS + 1}"

    conn = _get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = %s", (STATEMENT_TIMEOUT_MS,))
                cur.execute(wrapped)
                rows = cur.fetchall()
    finally:
        conn.close()

    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    payload = {
        "row_count": len(rows),
        "truncated": truncated,  # tell the model there's more it isn't seeing
        "rows": [{k: _json_safe(v) for k, v in row.items()} for row in rows],
    }
    return json.dumps(payload, default=str)


@beta_tool
def run_sql_query(query: str) -> str:
    """Run a single read-only SQL SELECT query against the `orders` table
    and return the matching rows as JSON.

    Args:
        query: A single PostgreSQL SELECT (or WITH ... SELECT) statement
            that reads only from the `orders` table.
    """
    try:
        return _run_query(query)
    except QueryRejected as e:
        return json.dumps({"error": f"Query rejected: {e}"})
    except psycopg2.Error as e:
        # psycopg2 error messages are safe to surface - they're driver/DB
        # errors (syntax, missing column, etc.), not user data.
        return json.dumps({"error": f"Database error: {e.pgerror or str(e)}".strip()})


def ask(question: str, client: anthropic.Anthropic | None = None) -> str:
    """Ask a plain-English question about the orders table and return
    Claude's answer."""
    client = client or anthropic.Anthropic()

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        output_config={"effort": "low"},  # single-table Q&A doesn't need deep reasoning
        tools=[run_sql_query],
        messages=[{"role": "user", "content": question}],
    )

    last = None
    for message in runner:
        last = message

    if last is None:
        return "Something went wrong - no response from the model."
    if last.stop_reason == "refusal":
        return "I couldn't answer that question."
    return next((b.text for b in last.content if b.type == "text"), "").strip()


def main():
    if len(sys.argv) < 2:
        print('Usage: python orders_qa.py "your question here"')
        sys.exit(1)
    question = " ".join(sys.argv[1:])
    try:
        answer = ask(question)
    except anthropic.APIStatusError as e:
        print(f"Claude API error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)
    print(answer)


if __name__ == "__main__":
    main()

````

### `requirements.txt`

````txt
anthropic>=0.75
psycopg2-binary>=2.9
sqlparse>=0.5

````
