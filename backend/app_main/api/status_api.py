# 系统状态API模块
"""
系统状态和统计信息相关的API接口
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from app_main.auth import _auth_user_from_request, get_chat_db
from app_main.connection import ConnectionManager

# 创建路由器
status_router = APIRouter(prefix="/api", tags=["status"])

# 需要从main.py注入的依赖
mcp_agent = None
chat_db = None
manager = None

def init_status_dependencies(agent, database, connection_manager):
    """初始化状态API的依赖"""
    global mcp_agent, chat_db, manager
    mcp_agent = agent
    chat_db = database
    manager = connection_manager

@status_router.get("/models")
async def get_models(request: Request):
    """获取可选的大模型档位列表（用于前端下拉选择）。"""
    if not mcp_agent:
        raise HTTPException(status_code=503, detail="MCP智能体未初始化")
    try:
        base = mcp_agent.get_models_info() or {"models": [], "default": "default"}
        # 合并用户自定义模型（需要登录）
        try:
            user = _auth_user_from_request(request)
            chat_db = get_chat_db()
            import aiosqlite
            extra = []
            async with aiosqlite.connect(chat_db.db_path) as db:
                cur = await db.execute(
                    "SELECT id, label, model, enabled FROM user_models WHERE user_id = ? ORDER BY id DESC",
                    (int(user["id"]),)
                )
                rows = await cur.fetchall()
                for r in rows:
                    extra.append({
                        "id": f"user-{int(r[0])}",
                        "label": r[1],
                        "model": r[2],
                        "is_default": False,
                        "type": "model",
                        "is_agent": False,
                    })
            base["models"] = (base.get("models") or []) + extra
        except HTTPException:
            pass
        return {"success": True, "data": base}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")

@status_router.get("/status")
async def get_status():
    """获取系统状态"""
    # 获取数据库统计信息
    db_stats = {}
    if chat_db:
        try:
            db_stats = await chat_db.get_stats()
        except Exception as e:
            print(f"⚠️ 获取数据库统计失败: {e}")
    
    return {
        "success": True,
        "data": {
            "agent_initialized": mcp_agent is not None,
            "database_initialized": chat_db is not None,
            "tools_count": len(mcp_agent.tools) if mcp_agent else 0,
            "active_connections": len(manager.active_connections) if manager else 0,
            "chat_records_count": db_stats.get("total_records", 0),
            "chat_sessions_count": db_stats.get("total_sessions", 0),
            "chat_conversations_count": db_stats.get("total_conversations", 0),
            "latest_record": db_stats.get("latest_record"),
            "database_path": db_stats.get("database_path"),
            "timestamp": datetime.now().isoformat()
        }
    }

@status_router.get("/database/stats")
async def get_database_stats():
    """获取数据库详细统计信息"""
    if not chat_db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    
    try:
        stats = await chat_db.get_stats()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取数据库统计失败: {str(e)}")
