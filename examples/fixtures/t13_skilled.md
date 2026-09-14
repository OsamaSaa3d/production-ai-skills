This doesn't need an agent. The steps are fixed and known, so they belong in your code — a scheduled script with a single LLM call in the middle.

```python
import pandas as pd

def daily_summary(csv_path: str) -> str:
    df = pd.read_csv(csv_path)
    facts = {
        "total_usd": float(df.total.sum()),
        "orders": int(len(df)),
        "top_sku": df.groupby("sku").total.sum().idxmax(),
    }
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": "Write a three-sentence sales summary for a team email."},
                  {"role": "user", "content": json.dumps(facts)}])
    return resp.choices[0].message.content

# cron: 0 8 * * *  -> daily_summary("/data/sales.csv") -> send_email(...)
```

An agent here would rediscover the same three steps every morning, at higher cost and lower reliability, with nothing gained.
