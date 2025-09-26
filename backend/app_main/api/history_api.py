# 聊天历史管理API模块
"""
聊天历史和对话线程管理相关的API接口
"""

from fastapi import APIRouter, HTTPException, Request
from app_main.auth import _auth_user_from_request

# 创建路由器
history_router = APIRouter(prefix="/api", tags=["history"])

# 需要从main.py注入的依赖
chat_db = None

def init_history_dependencies(database):
    """初始化历史API的依赖"""
    global chat_db
    chat_db = database

@history_router.get("/history")
async def get_history(limit: int = 50, session_id: str = None, conversation_id: int = None, request: Request = None):
    """获取聊天历史：强制按JWT用户过滤，不接受用户名查询参数。"""
    if not chat_db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    
    try:
        user = _auth_user_from_request(request)
        records = await chat_db.get_chat_history_by_user(
            username=user["username"],
            limit=limit,
            conversation_id=conversation_id,
            session_id=session_id,
        )
        
        # 获取统计信息
        stats = await chat_db.get_stats()
        
        return {
            "success": True,
            "data": records,
            "total": stats.get("total_records", 0),
            "returned": len(records),
            "session_id": session_id,
            "conversation_id": conversation_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取历史记录失败: {str(e)}")

@history_router.get("/threads")
async def get_threads(limit: int = 100, request: Request = None):
    """获取当前登录用户的对话线程列表（基于JWT，禁止明文用户名参数）。"""
    if not chat_db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    try:
        user = _auth_user_from_request(request)
        threads = await chat_db.get_threads_by_username(username=user["username"], limit=limit)
        return {"success": True, "data": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取线程列表失败: {str(e)}")

@history_router.delete("/history")
async def clear_history(session_id: str = None):
    """清空聊天历史"""
    if not chat_db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    
    try:
        # 如果没有提供session_id，则清空所有历史（保持向后兼容）
        if session_id:
            success = await chat_db.clear_history(session_id=session_id)
            message = f"会话 {session_id} 的聊天历史已清空"
        else:
            success = await chat_db.clear_history()
            message = "所有聊天历史已清空"
        
        if success:
            return {"success": True, "message": message}
        else:
            raise HTTPException(status_code=500, detail="清空历史记录失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空历史记录失败: {str(e)}")

@history_router.delete("/threads")
async def delete_thread(session_id: str, conversation_id: int):
    """删除某个对话线程"""
    if not chat_db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    try:
        ok = await chat_db.delete_conversation(session_id=session_id, conversation_id=conversation_id)
        if ok:
            return {"success": True}
        raise HTTPException(status_code=500, detail="删除对话线程失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除对话线程失败: {str(e)}")
