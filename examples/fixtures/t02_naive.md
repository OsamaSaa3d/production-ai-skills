```python
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o")
agent = create_openai_tools_agent(llm, [lookup_order, issue_refund], prompt)
executor = AgentExecutor(agent=agent, tools=[lookup_order, issue_refund], verbose=True)

def handle(message: str):
    return executor.invoke({"input": message})
```
