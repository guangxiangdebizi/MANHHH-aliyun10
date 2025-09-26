# mcp_api.py
"""
MCP 相关 API 模块 - 处理 MCP 工具、服务器配置等相关接口
"""

from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any

# 创建 MCP 路由器
mcp_router = APIRouter(prefix="/api", tags=["mcp"])

def get_mcp_agent():
    """获取 mcp_agent 实例的依赖注入函数，需要在主模块中设置"""
    if not hasattr(get_mcp_agent, 'instance'):
        raise HTTPException(status_code=503, detail="MCP智能体未初始化")
    return get_mcp_agent.instance

@mcp_router.get("/tools")
async def get_tools():
    """获取可用工具列表"""
    mcp_agent = get_mcp_agent()
    
    try:
        tools_info = mcp_agent.get_tools_info()
        return {
            "success": True,
            "data": tools_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取工具列表失败: {str(e)}")

@mcp_router.get("/mcp/servers")
async def get_mcp_servers():
    """读取并返回当前 MCP 服务器配置（隐藏敏感头值）。"""
    try:
        mcp_agent = get_mcp_agent()
        cfg = mcp_agent.config.load_config() or {}
        servers = cfg.get("servers", {})
        # 隐去 headers 的值，仅暴露 key
        redacted = {}
        for name, sc in servers.items():
            sc_copy = dict(sc)
            headers = dict(sc_copy.get("headers", {}) or {})
            if headers:
                sc_copy["headers"] = {k: "***" for k in headers.keys()}
            redacted[name] = sc_copy
        return {"success": True, "data": redacted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取MCP配置失败: {str(e)}")

@mcp_router.post("/mcp/token")
async def set_tushare_token(token: str = Body(..., embed=True)):
    """设置 finance-mcp 的 X-Tushare-Token 并热重载。"""
    mcp_agent = get_mcp_agent()
    try:
        token = (token or "").strip()
        if not token:
            raise HTTPException(status_code=400, detail="Token不能为空")

        cfg = mcp_agent.config.load_config() or {}
        servers = cfg.setdefault("servers", {})
        finance = servers.setdefault("finance-mcp", {})
        headers = finance.setdefault("headers", {})
        headers["X-Tushare-Token"] = token

        # 保存
        mcp_agent.config.save_config(cfg)

        # 热重载
        ok = await mcp_agent.reload_mcp_servers()
        if not ok:
            raise HTTPException(status_code=500, detail="热重载失败")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"设置Token失败: {str(e)}")

# 导出路由器
__all__ = ["mcp_router", "get_mcp_agent"]
