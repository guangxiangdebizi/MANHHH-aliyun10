from contextlib import asynccontextmanager
from typing import AsyncGenerator


@asynccontextmanager
async def lifespan_factory(init_db, init_agent, close_db, close_agent) -> AsyncGenerator:
    """通用的应用生命周期工厂：将 main.py 的生命周期代码参数化以便复用/测试。

    - init_db(): -> ChatDatabase 实例
    - init_agent(): -> WebMCPAgent 实例
    - close_db(db)
    - close_agent(agent)
    """
    chat_db = await init_db()
    mcp_agent = await init_agent()
    try:
        yield (chat_db, mcp_agent)
    finally:
        try:
            if close_agent:
                await close_agent(mcp_agent)
        finally:
            if close_db:
                await close_db(chat_db)


