# 分享功能API模块
"""
聊天记录分享相关的API接口
"""

from typing import Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Body
from app_main.auth import _auth_user_from_request

# 创建路由器
share_router = APIRouter(prefix="/api", tags=["share"])

# 需要从main.py注入的依赖
chat_db = None

def init_share_dependencies(database):
    """初始化分享API的依赖"""
    global chat_db
    chat_db = database

@share_router.get("/share/{session_id}")
async def get_shared_chat(session_id: str, limit: int = 100):
    """获取分享的聊天记录（只读）"""
    if not chat_db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    
    try:
        # 获取指定会话的聊天历史
        records = await chat_db.get_chat_history(
            session_id=session_id, 
            limit=limit
        )
        
        if not records:
            raise HTTPException(status_code=404, detail="未找到该会话的聊天记录")
        
        # 获取会话统计信息
        stats = await chat_db.get_stats()
        
        return {
            "success": True,
            "data": records,
            "session_id": session_id,
            "total_records": len(records),
            "shared_at": datetime.now().isoformat(),
            "readonly": True
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分享聊天记录失败: {str(e)}")

@share_router.post("/share/create")
async def create_share_snapshot(request: Request, payload: Dict[str, Any] = Body(default={})):
    """创建只读分享快照，返回 share_id。
    支持字段：session_id（可选，默认当前连接最近使用）/ conversation_id（可选）/ limit（默认100）
    备注：为提升安全性，仅允许已登录用户创建快照，并将快照与创建者关联。
    """
    if not chat_db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    try:
        user = _auth_user_from_request(request)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="未认证")

    try:
        session_id = str((payload or {}).get("session_id") or "default").strip() or "default"
        limit = int((payload or {}).get("limit") or 100)
        conversation_id = (payload or {}).get("conversation_id")
        # 仅导出当前用户的记录
        records = await chat_db.get_chat_history_by_user(
            username=user["username"],
            limit=limit,
            conversation_id=conversation_id,
            session_id=session_id,
        )
        if not records:
            raise HTTPException(status_code=404, detail="没有可分享的记录")
        share_id = await chat_db.create_shared_snapshot(records, created_by_user_id=user["id"], created_by_username=user["username"])
        if not share_id:
            raise HTTPException(status_code=500, detail="创建分享失败")
        return {"success": True, "share_id": share_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建分享失败: {str(e)}")

@share_router.get("/share/s/{share_id}")
async def get_share_snapshot(share_id: str):
    """读取只读分享快照。"""
    if not chat_db:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    try:
        records = await chat_db.get_shared_snapshot(share_id)
        if not records:
            raise HTTPException(status_code=404, detail="分享不存在或已删除")
        return {"success": True, "data": records, "share_id": share_id, "readonly": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取分享失败: {str(e)}")
