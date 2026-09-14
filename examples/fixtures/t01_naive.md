Here's a natural-language query interface using LangChain's SQL agent:

```python
from langchain_openai import ChatOpenAI
from langchain.agents import create_sql_agent
from langchain_community.utilities import SQLDatabase

db = SQLDatabase.from_uri("postgresql://localhost/shop")
llm = ChatOpenAI(model="gpt-4o")
agent = create_sql_agent(llm=llm, db=db, verbose=True)

def ask(question: str) -> str:
    return agent.run(question)
```

This lets users ask anything and the agent figures out the SQL.
