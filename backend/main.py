# main.py
"""
FastAPI 后端主文件
提供WebSocket聊天接口和REST API
"""

import json
import asyncio
import uuid
from typing import List, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi import UploadFile, File
from fastapi import Body
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import os
from dotenv import load_dotenv, find_dotenv
import uvicorn
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app_main.quant_intent import (
    is_quant_by_oversee,
)

from mcp_agent import WebMCPAgent
from database import ChatDatabase
from app_main.connection import ConnectionManager
from app_main.ws_handlers import handle_ping, handle_pause, handle_resume_conversation
from app_main.auth import auth_router, _auth_user_from_request, get_chat_db, JWT_SECRET, JWT_ALG
from app_main.mcp_api import mcp_router, get_mcp_agent
import jwt as pyjwt

# 全局变量
mcp_agent = None
chat_db = None  # SQLite数据库实例
active_connections: List[WebSocket] = []
# 当前会话的流式任务，支持暂停/取消
active_stream_tasks: Dict[str, asyncio.Task] = {}

# 每次对话扣减的积分数量（可通过环境变量 CREDITS_COST_PER_MESSAGE 配置）
try:
    CREDITS_COST_PER_MESSAGE = int(os.getenv("CREDITS_COST_PER_MESSAGE", "1"))
except Exception:
    CREDITS_COST_PER_MESSAGE = 1

# 自动路由量化档位的环境开关与目标档位
def _is_truthy(val: str) -> bool:
    try:
        return str(val).strip().lower() in {"1", "true", "yes", "on", "y"}
    except Exception:
        return False

AUTO_ROUTE_QUANT = _is_truthy(os.getenv("AUTO_ROUTE_QUANT", "true"))
AUTO_ROUTE_QUANT_PROFILE_ID = os.getenv("AUTO_ROUTE_QUANT_PROFILE_ID", "quant").strip() or "quant"

def _detect_quant_intent(raw_text: str) -> bool:
    # 关键词回退已移除，保持兼容接口但不再使用
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global mcp_agent, chat_db
    
    # 启动时初始化
    print("🚀 启动 MCP Web 智能助手...")
    
    # 初始化数据库
    chat_db = ChatDatabase()
    db_success = await chat_db.initialize()
    if not db_success:
        print("❌ 数据库初始化失败")
        raise Exception("数据库初始化失败")
    
    # 设置认证模块的数据库依赖注入
    get_chat_db.instance = chat_db
    # 确保用户自定义模型表存在（幂等）
    try:
        import aiosqlite
        async with aiosqlite.connect(chat_db.db_path) as _db:
            await _db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    profile_id TEXT,
                    label TEXT NOT NULL,
                    api_key TEXT NOT NULL,
                    base_url TEXT,
                    model TEXT NOT NULL,
                    temperature REAL DEFAULT 0.2,
                    timeout INTEGER DEFAULT 60,
                    system_prompt TEXT,
                    enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await _db.execute("CREATE INDEX IF NOT EXISTS idx_user_models_user ON user_models(user_id)")
            await _db.execute("CREATE INDEX IF NOT EXISTS idx_user_models_profile ON user_models(user_id, profile_id)")
            await _db.commit()
    except Exception as _e:
        print(f"⚠️ 初始化用户模型表失败: {_e}")
    
    # 初始化MCP智能体
    mcp_agent = WebMCPAgent()
    mcp_success = await mcp_agent.initialize()
    
    if not mcp_success:
        print("❌ MCP智能体初始化失败")
        raise Exception("MCP智能体初始化失败")
    
    # 设置MCP模块的智能体依赖注入
    get_mcp_agent.instance = mcp_agent
    
    # 初始化API模块的依赖
    init_status_dependencies(mcp_agent, chat_db, manager)
    init_history_dependencies(chat_db)
    init_share_dependencies(chat_db)
    
    print("✅ MCP Web 智能助手启动成功")
    
    yield
    
    # 关闭时清理资源
    if mcp_agent:
        await mcp_agent.close()
    if chat_db:
        await chat_db.close()
    print("👋 MCP Web 智能助手已关闭")

# 创建FastAPI应用
# 预加载 .env（不覆盖系统变量）
try:
    load_dotenv(find_dotenv(), override=False)
except Exception:
    pass

app = FastAPI(
    title="MCP Web智能助手",
    description="基于MCP的智能助手Web版",
    version="1.0.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载认证路由
app.include_router(auth_router)

# 挂载MCP路由
app.include_router(mcp_router)

# 挂载API路由
from app_main.api.upload_api import upload_router
from app_main.api.status_api import status_router, init_status_dependencies
from app_main.api.user_models_api import user_models_router, init_user_models_dependencies
from app_main.api.history_api import history_router, init_history_dependencies
from app_main.api.share_api import share_router, init_share_dependencies
app.include_router(upload_router)
app.include_router(status_router)
app.include_router(history_router)
app.include_router(share_router)
app.include_router(user_models_router)



# ─────────── WebSocket 接口 ───────────

manager = ConnectionManager()

# 挂载上传文件静态目录
try:
    UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
except Exception as _e:
    print(f"⚠️ 挂载上传目录失败: {_e}")

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket聊天接口"""
    # 为每个连接生成唯一会话ID并建立连接
    session_id = str(uuid.uuid4())
    await manager.connect(websocket, session_id)
    print(f"📱 新连接建立，会话ID: {session_id}，当前连接数: {len(manager.active_connections)}")
    # 向前端发送会话ID
    await manager.send_personal_message({"type": "session_info", "session_id": session_id}, websocket)
    # 认证：从查询参数 token 校验，未带或非法则拒绝交互
    try:
        token = websocket.query_params.get("token")
        if not token:
            await manager.send_personal_message({"type": "error", "content": "需要登录后才能对话"}, websocket)
            await websocket.close()
            return
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
            user_id = payload.get("uid")
            username = payload.get("usr")
            if not user_id:
                raise ValueError("Invalid token")
        except Exception:
            await manager.send_personal_message({"type": "error", "content": "登录已失效，请重新登录"}, websocket)
            await websocket.close()
            return
        # 将用户信息放入会话上下文（合并而不是覆盖）
        if not hasattr(mcp_agent, 'session_contexts'):
            mcp_agent.session_contexts = {}
        existing_ctx = mcp_agent.session_contexts.get(session_id, {}) or {}
        existing_ctx.update({"user_id": user_id, "username": username})
        # 载入用户的 Tushare Token 到会话上下文（用于下游动态注入到 MCP 请求头）
        # 仅当用户已启用时才加载
        try:
            if chat_db and user_id:
                token_data = await chat_db.get_user_tushare_token_by_id(int(user_id))
                if token_data and token_data.get("enabled") and token_data.get("token"):
                    existing_ctx["tushare_token"] = str(token_data["token"]).strip()
                    print(f"✓ 用户 {username} 已启用自定义 Tushare Token")
                else:
                    # 确保清除旧的 token（如果用户禁用了）
                    existing_ctx.pop("tushare_token", None)
        except Exception as _e:
            print(f"⚠️ 读取用户 Tushare Token 失败: {_e}")
        mcp_agent.session_contexts[session_id] = existing_ctx
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
        return

    # 从连接查询参数中读取 model 并保存到会话上下文（后端隐藏使用，不回传给前端）
    try:
        print(f"🔍 WebSocket 查询参数: {dict(websocket.query_params)}")
        model_param = websocket.query_params.get("model")
        print(f"🔍 提取的 model 参数: {model_param}")
        if not hasattr(mcp_agent, 'session_contexts'):
            mcp_agent.session_contexts = {}
        mcp_agent.session_contexts[session_id] = mcp_agent.session_contexts.get(session_id, {}) or {}

        # 记录模型档位（如果提供）
        try:
            if model_param is not None and model_param != "":
                if not hasattr(mcp_agent, 'session_contexts'):
                    mcp_agent.session_contexts = {}
                session_ctx = mcp_agent.session_contexts.get(session_id, {}) or {}
                # 若是用户自定义模型，预取配置缓存
                if str(model_param).startswith("user-"):
                    try:
                        user_id = (session_ctx or {}).get("user_id")
                        if user_id:
                            import aiosqlite
                            async with aiosqlite.connect(chat_db.db_path) as db:
                                cur = await db.execute(
                                    "SELECT id, label, api_key, base_url, model, temperature, timeout, system_prompt, enabled FROM user_models WHERE id = ? AND user_id = ?",
                                    (int(str(model_param).split("-",1)[1]), int(user_id))
                                )
                                row = await cur.fetchone()
                                if row and int(row[8]) == 1:
                                    cfg = {
                                        "id": f"user-{int(row[0])}",
                                        "label": row[1],
                                        "api_key": row[2],
                                        "base_url": row[3],
                                        "model": row[4],
                                        "temperature": float(row[5] or 0.2),
                                        "timeout": int(row[6] or 60),
                                        "system_prompt": row[7] or "",
                                    }
                                    mapping = session_ctx.get("user_models") or {}
                                    mapping[cfg["id"]] = cfg
                                    session_ctx["user_models"] = mapping
                    except Exception as __e:
                        print(f"⚠️ 预取用户模型失败: {__e}")
                session_ctx["model"] = str(model_param)
                mcp_agent.session_contexts[session_id] = session_ctx
                print(f"🔐 已为会话 {session_id} 记录 model={model_param}")
        except Exception as e:
            print(f"⚠️ 记录 model 失败: {e}")
    except Exception as _e:
        print(f"❌ 处理查询参数异常: {_e}")
        if not hasattr(mcp_agent, 'session_contexts'):
            mcp_agent.session_contexts = {}
        mcp_agent.session_contexts[session_id] = {}
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                if message.get("type") == "user_msg":
                    # 支持两种输入：
                    # 1) content: 纯文本字符串
                    # 2) content_parts: 多模态内容数组（[{type:'text',...}, {type:'image_url',...}]）
                    raw_content = message.get("content", None)
                    content_parts = message.get("content_parts") or []
                    attachments = message.get("attachments") or []

                    user_has_text = isinstance(raw_content, str) and raw_content.strip() != ""
                    user_has_images = isinstance(content_parts, list) and any(
                        isinstance(p, dict) and str(p.get("type") or "").lower() == "image_url" for p in content_parts
                    )
                    # 允许纯图片消息
                    if not user_has_text and not user_has_images and not attachments:
                        await manager.send_personal_message({
                            "type": "error",
                            "content": "User input cannot be empty"
                        }, websocket)
                        continue
                    # 在生成前：如开启了自动路由，优先用 Oversee 判别LLM，仅以本次用户文本判定；失败则回退关键词
                    try:
                        if AUTO_ROUTE_QUANT:
                            current_session_id = manager.get_session_id(websocket)
                            if not hasattr(mcp_agent, 'session_contexts'):
                                mcp_agent.session_contexts = {}
                            session_ctx = mcp_agent.session_contexts.get(current_session_id, {}) or {}
                            curr_model = session_ctx.get("model") or session_ctx.get("llm_profile")
                            # 仅在用户文本明显为量化需求且当前并非量化档位时切换
                            user_preview_text = (raw_content or "") if isinstance(raw_content, str) else ""
                            want_quant = None
                            try:
                                want_quant = await is_quant_by_oversee(user_preview_text)
                                try:
                                    if os.getenv("OVERSEE_LLM_DEBUG", "false").strip().lower() in {"1","true","yes","on","y"}:
                                        print(f"🔎 判别LLM结果: want_quant={want_quant}")
                                except Exception:
                                    pass
                            except Exception as _e:
                                print(f"⚠️ Oversee 判别调用异常: {_e}")
                                want_quant = None
                            # 若判别LLM未能给出明确结论，则不进行自动切换
                            if want_quant and curr_model != AUTO_ROUTE_QUANT_PROFILE_ID:
                                try:
                                    if os.getenv("OVERSEE_LLM_DEBUG", "false").strip().lower() in {"1","true","yes","on","y"}:
                                        short = (user_preview_text or "")[:60]
                                        print(f"✅ 触发自动路由: from={curr_model} -> to={AUTO_ROUTE_QUANT_PROFILE_ID}, text='{short}'")
                                except Exception:
                                    pass
                                session_ctx["model"] = AUTO_ROUTE_QUANT_PROFILE_ID
                                mcp_agent.session_contexts[current_session_id] = session_ctx
                                try:
                                    await manager.send_personal_message({
                                        "type": "model_switched",
                                        "model": AUTO_ROUTE_QUANT_PROFILE_ID,
                                        "reason": "auto_route_quant"
                                    }, websocket)
                                except Exception:
                                    pass
                    except Exception as _e:
                        print(f"⚠️ 自动路由量化档位失败: {_e}")

                    # 在生成前检查并扣减积分
                    try:
                        current_session_id = manager.get_session_id(websocket)
                        if not hasattr(mcp_agent, 'session_contexts'):
                            mcp_agent.session_contexts = {}
                        session_ctx = mcp_agent.session_contexts.get(current_session_id, {}) or {}
                        target_user_id = session_ctx.get("user_id")
                        if not target_user_id:
                            await manager.send_personal_message({
                                "type": "error",
                                "content": "未获取到用户信息，请重新登录"
                            }, websocket)
                            continue
                        ok_deduct = await chat_db.try_deduct_credits(int(target_user_id), int(CREDITS_COST_PER_MESSAGE))
                        if not ok_deduct:
                            # 查询剩余以友好提示
                            remaining = await chat_db.get_user_credits_by_id(int(target_user_id))
                            await manager.send_personal_message({
                                "type": "error",
                                "content": "积分不足，请充值后再使用。",
                                "code": "insufficient_credits",
                                "remaining": remaining,
                                "required": int(CREDITS_COST_PER_MESSAGE)
                            }, websocket)
                            continue
                        try:
                            remaining = await chat_db.get_user_credits_by_id(int(target_user_id))
                        except Exception:
                            remaining = None
                        # 通知前端最新积分
                        try:
                            await manager.send_personal_message({
                                "type": "credits_update",
                                "remaining": remaining
                            }, websocket)
                        except Exception:
                            pass
                    except Exception as _e:
                        print(f"⚠️ 扣减积分失败: {_e}")
                    
                    # 打印安全预览（文本前50字符或 [images] 提示）
                    try:
                        if isinstance(raw_content, str) and raw_content.strip():
                            _preview = raw_content[:50]
                        elif isinstance(content_parts, list) and any((isinstance(p, dict) and str(p.get('type') or '').lower() == 'image_url') for p in content_parts):
                            _preview = "[images]"
                        else:
                            _preview = ""
                    except Exception:
                        _preview = ""
                    print(f"📨 收到用户消息: {_preview}...")
                    
                    # 确认收到用户消息
                    await manager.send_personal_message({
                        "type": "user_msg_received",
                        "content": (raw_content if isinstance(raw_content, str) else "")
                    }, websocket)
                    
                    # 收集对话数据
                    conversation_data = {
                        "user_input": raw_content if raw_content is not None else "",
                        "mcp_tools_called": [],
                        "mcp_results": [],
                        "ai_response_parts": []
                    }
                    
                    # 获取当前连接与会话上下文
                    current_session_id = manager.get_session_id(websocket)
                    # 支持续聊：若存在生效的会话与线程，则复用；否则在生效会话上新建
                    try:
                        if not hasattr(mcp_agent, 'session_contexts'):
                            mcp_agent.session_contexts = {}
                        session_ctx = mcp_agent.session_contexts.get(current_session_id, {})
                        # 用户自定义模型：预载入配置到会话上下文
                        if new_model.startswith("user-"):
                            try:
                                user_id = (session_ctx or {}).get("user_id")
                                if not user_id:
                                    raise ValueError("missing user id")
                                import aiosqlite
                                async with aiosqlite.connect(chat_db.db_path) as db:
                                    cur = await db.execute(
                                        "SELECT id, label, api_key, base_url, model, temperature, timeout, system_prompt, enabled FROM user_models WHERE id = ? AND user_id = ?",
                                        (int(new_model.split("-",1)[1]), int(user_id))
                                    )
                                    row = await cur.fetchone()
                                    if not row or int(row[8]) != 1:
                                        raise ValueError("user model not found or disabled")
                                    cfg = {
                                        "id": f"user-{int(row[0])}",
                                        "label": row[1],
                                        "api_key": row[2],
                                        "base_url": row[3],
                                        "model": row[4],
                                        "temperature": float(row[5] or 0.2),
                                        "timeout": int(row[6] or 60),
                                        "system_prompt": row[7] or "",
                                    }
                                    mapping = session_ctx.get("user_models") or {}
                                    mapping[cfg["id"]] = cfg
                                    session_ctx["user_models"] = mapping
                            except Exception as __e:
                                await manager.send_personal_message({
                                    "type": "model_switch_error",
                                    "content": f"Invalid user model: {__e}"
                                }, websocket)
                                continue
                        # Use effective session/thread when available to avoid cross-thread writes
                        effective_session_id = session_ctx.get("effective_session_id") or current_session_id
                        conversation_id = session_ctx.get("effective_conversation_id") or session_ctx.get("conversation_id")
                        if conversation_id is None:
                            conversation_id = await chat_db.start_conversation(session_id=effective_session_id)
                            # 记录为当前连接的默认对话线程（未显式续聊时也复用该线程）
                            session_ctx["conversation_id"] = conversation_id
                            # 若此前已设置了 effective_session_id，则也将其与该对话绑定为生效线程
                            session_ctx["effective_session_id"] = effective_session_id
                            session_ctx["effective_conversation_id"] = conversation_id
                            mcp_agent.session_contexts[current_session_id] = session_ctx
                            print(f"🧵 新建对话线程 conversation_id={conversation_id} 用于会话 {effective_session_id}（连接 {current_session_id}）")
                    except Exception as _e:
                        print(f"⚠️ 初始化 conversation_id 失败: {_e}")
                        conversation_id = None

                    # Load history strictly by effective session/thread to avoid mismatch
                    effective_session_id_for_history = session_ctx.get("effective_session_id") or current_session_id
                    conversation_id_for_history = session_ctx.get("effective_conversation_id") or conversation_id
                    history = await chat_db.get_chat_history(
                        session_id=effective_session_id_for_history,
                        limit=10,
                        conversation_id=conversation_id_for_history
                    ) # 限制最近10条

                    # 启动后台任务消费流，允许外部 pause 取消
                    async def stream_and_persist():
                        try:
                            response_started = False
                            # 准备用户输入：
                            # - 如为多模态（content_parts），直接传入，不拼接附件提示
                            # - 否则为纯文本，可按需注入附件说明
                            user_payload = None
                            if isinstance(content_parts, list) and content_parts:
                                # 如果包含图片，但当前选择的模型不支持视觉，提前报错
                                try:
                                    selected_pid = session_ctx.get("model")
                                    cfg = None
                                    if selected_pid and selected_pid in mcp_agent.llm_profiles:
                                        cfg = mcp_agent.llm_profiles.get(selected_pid)
                                    else:
                                        cfg = mcp_agent.llm_profiles.get(mcp_agent.default_profile_id)
                                    model_name = (cfg or {}).get("model", "")
                                    base_url = (cfg or {}).get("base_url", "")
                                    if user_has_images and not mcp_agent._supports_vision(model_name, base_url):
                                        await manager.send_personal_message({
                                            "type": "error",
                                            "content": "当前所选模型不支持图像解析，请切换支持视觉的模型或移除图片。",
                                            "code": "vision_not_supported"
                                        }, websocket)
                                        return
                                except Exception:
                                    pass
                                user_payload = content_parts
                            else:
                                enriched_user_input = (raw_content or "").strip()
                                if attachments:
                                    try:
                                        names = ", ".join([str(a.get('filename') or '') for a in attachments if a])
                                        urls = "; ".join([str(a.get('url') or '') for a in attachments if a])
                                        note = f"\n\n[Attachments]\nfilenames: {names}\nurls: {urls}\nIf needed, use tool 'preview_uploaded_file' with the url string to preview content."
                                        enriched_user_input = (enriched_user_input or '') + note
                                    except Exception:
                                        pass
                                user_payload = enriched_user_input

                            async for response_chunk in mcp_agent.chat_stream(user_payload, history=history, session_id=current_session_id):
                                await manager.send_personal_message(response_chunk, websocket)
                                chunk_type = response_chunk.get("type")
                                if chunk_type == "ai_response_start":
                                    response_started = True
                                elif chunk_type == "tool_start":
                                    conversation_data["mcp_tools_called"].append({
                                        "tool_id": response_chunk.get("tool_id"),
                                        "tool_name": response_chunk.get("tool_name"),
                                        "tool_args": response_chunk.get("tool_args"),
                                        "progress": response_chunk.get("progress")
                                    })
                                elif chunk_type == "tool_end":
                                    conversation_data["mcp_results"].append({
                                        "tool_id": response_chunk.get("tool_id"),
                                        "tool_name": response_chunk.get("tool_name"),
                                        "result": response_chunk.get("result"),
                                        "success": True
                                    })
                                elif chunk_type == "tool_error":
                                    conversation_data["mcp_results"].append({
                                        "tool_id": response_chunk.get("tool_id"),
                                        "error": response_chunk.get("error"),
                                        "success": False
                                    })
                                elif chunk_type in ("ai_response_chunk", "ai_thinking_chunk"):
                                    conversation_data["ai_response_parts"].append(response_chunk.get("content", ""))
                                elif chunk_type == "token_usage":
                                    conversation_data["usage"] = {
                                        "input_tokens": response_chunk.get("input_tokens"),
                                        "output_tokens": response_chunk.get("output_tokens"),
                                        "total_tokens": response_chunk.get("total_tokens")
                                    }
                                elif chunk_type == "error":
                                    print(f"❌ MCP处理错误: {response_chunk.get('content')}")
                                    break
                        except asyncio.CancelledError:
                            # 被暂停：结束消息但不丢已生成内容
                            if response_started:
                                try:
                                    await manager.send_personal_message({"type": "ai_response_end", "content": ""}, websocket)
                                except Exception:
                                    pass
                            raise
                        except Exception as e:
                            print(f"❌ MCP流式处理异常: {e}")
                        finally:
                            ai_response_final = "".join(conversation_data["ai_response_parts"]) or ""
                            if not ai_response_final and conversation_data["mcp_results"]:
                                error_results = [r for r in conversation_data["mcp_results"] if not r.get("success", True)]
                                if error_results:
                                    ai_response_final = "处理过程中遇到错误：\n" + "\n".join([r.get("error", "未知错误") for r in error_results])
                            try:
                                if chat_db:
                                    # 续聊：保存到生效会话+线程
                                    effective_session_id_for_save = session_ctx.get("effective_session_id") or current_session_id
                                    effective_conversation_id_for_save = session_ctx.get("effective_conversation_id") or conversation_id
                                    inserted_id = await chat_db.save_conversation(
                                        user_input=conversation_data["user_input"],
                                        mcp_tools_called=conversation_data["mcp_tools_called"],
                                        mcp_results=conversation_data["mcp_results"],
                                        ai_response=ai_response_final,
                                        session_id=effective_session_id_for_save,
                                        conversation_id=effective_conversation_id_for_save,
                                        username=(session_ctx or {}).get("username"),
                                        user_id=(session_ctx or {}).get("user_id"),
                                        attachments=attachments,
                                        usage=conversation_data.get("usage")
                                    )
                                    # 将新记录ID回传给前端，便于即时挂载操作按钮
                                    try:
                                        await manager.send_personal_message({
                                            "type": "record_saved",
                                            "record_id": inserted_id,
                                            "session_id": effective_session_id_for_save,
                                            "conversation_id": effective_conversation_id_for_save
                                        }, websocket)
                                    except Exception:
                                        pass
                            except Exception as e:
                                print(f"❌ 保存对话记录异常: {e}")
                            finally:
                                active_stream_tasks.pop(current_session_id, None)

                    task = asyncio.create_task(stream_and_persist())
                    active_stream_tasks[current_session_id] = task
                    continue
                
                elif message.get("type") == "pause":
                    await handle_pause(websocket, manager, active_stream_tasks)
                    continue

                elif message.get("type") == "ping":
                    await handle_ping(websocket, manager)
                elif message.get("type") == "resume_conversation":
                    await handle_resume_conversation(message, websocket, manager, mcp_agent)
                elif message.get("type") == "switch_model":
                    # 切换当前连接的模型档位（不重连，不新开会话）
                    try:
                        payload = message or {}
                        new_model = str(payload.get("model") or "").strip()
                        if not new_model:
                            await manager.send_personal_message({
                                "type": "model_switch_error",
                                "content": "Missing model id"
                            }, websocket)
                            continue
                        current_session_id = manager.get_session_id(websocket)
                        if not hasattr(mcp_agent, 'session_contexts'):
                            mcp_agent.session_contexts = {}
                        session_ctx = mcp_agent.session_contexts.get(current_session_id, {})
                        session_ctx["model"] = new_model
                        mcp_agent.session_contexts[current_session_id] = session_ctx
                        await manager.send_personal_message({
                            "type": "model_switched",
                            "model": new_model
                        }, websocket)
                    except Exception as _e:
                        await manager.send_personal_message({
                            "type": "model_switch_error",
                            "content": f"Switch failed: {_e}"
                        }, websocket)
                elif message.get("type") == "replay_edit":
                    # 回溯编辑：删除某线程从指定记录ID起的历史，并以新内容作为本轮用户输入重新生成
                    try:
                        payload = message or {}
                        target_session = str(payload.get("session_id") or "").strip()
                        target_conv = payload.get("conversation_id")
                        from_record_id = payload.get("from_record_id")
                        new_user_input = str(payload.get("new_user_input") or "").strip()
                        if not target_session or target_conv is None or from_record_id is None or not new_user_input:
                            await manager.send_personal_message({
                                "type": "edit_error",
                                "content": "Missing required fields"
                            }, websocket)
                            continue
                        # 先删除后续记录
                        try:
                            ok = await chat_db.delete_records_after(target_session, int(target_conv), int(from_record_id))
                            if not ok:
                                await manager.send_personal_message({
                                    "type": "edit_error",
                                    "content": "Failed to truncate history"
                                }, websocket)
                                continue
                        except Exception as _e:
                            await manager.send_personal_message({
                                "type": "edit_error",
                                "content": f"Truncate failed: {_e}"
                            }, websocket)
                            continue

                        # 绑定生效会话/线程到当前连接，随后按普通 user_msg 流程处理
                        current_session_id = manager.get_session_id(websocket)
                        if not hasattr(mcp_agent, 'session_contexts'):
                            mcp_agent.session_contexts = {}
                        session_ctx = mcp_agent.session_contexts.get(current_session_id, {})
                        session_ctx["effective_session_id"] = target_session
                        session_ctx["effective_conversation_id"] = int(target_conv)
                        mcp_agent.session_contexts[current_session_id] = session_ctx
                        await manager.send_personal_message({
                            "type": "edit_ok",
                            "session_id": target_session,
                            "conversation_id": int(target_conv)
                        }, websocket)

                        # 生成前扣减积分
                        try:
                            target_user_id = (mcp_agent.session_contexts.get(current_session_id, {}) or {}).get("user_id") if hasattr(mcp_agent, 'session_contexts') else None
                            if not target_user_id:
                                await manager.send_personal_message({
                                    "type": "edit_error",
                                    "content": "未获取到用户信息，请重新登录"
                                }, websocket)
                                continue
                            ok_deduct = await chat_db.try_deduct_credits(int(target_user_id), int(CREDITS_COST_PER_MESSAGE))
                            if not ok_deduct:
                                remaining = await chat_db.get_user_credits_by_id(int(target_user_id))
                                await manager.send_personal_message({
                                    "type": "edit_error",
                                    "content": "积分不足，请充值后再使用。",
                                    "code": "insufficient_credits",
                                    "remaining": remaining,
                                    "required": int(CREDITS_COST_PER_MESSAGE)
                                }, websocket)
                                continue
                            try:
                                remaining = await chat_db.get_user_credits_by_id(int(target_user_id))
                            except Exception:
                                remaining = None
                            try:
                                await manager.send_personal_message({
                                    "type": "credits_update",
                                    "remaining": remaining
                                }, websocket)
                            except Exception:
                                pass
                        except Exception as _e:
                            print(f"⚠️ 回溯编辑扣减积分失败: {_e}")

                        # 直接按 user_msg 流程继续生成
                        user_input = new_user_input
                        # 收集对话数据
                        conversation_data = {
                            "user_input": user_input,
                            "mcp_tools_called": [],
                            "mcp_results": [],
                            "ai_response_parts": []
                        }
                        # 在目标线程上取历史
                        history = await chat_db.get_chat_history(
                            session_id=target_session,
                            limit=10,
                            conversation_id=int(target_conv)
                        )
                        async def stream_and_persist_edit():
                            try:
                                response_started = False
                                async for response_chunk in mcp_agent.chat_stream(user_input, history=history, session_id=current_session_id):
                                    await manager.send_personal_message(response_chunk, websocket)
                                    chunk_type = response_chunk.get("type")
                                    if chunk_type == "ai_response_start":
                                        response_started = True
                                    elif chunk_type == "tool_start":
                                        conversation_data["mcp_tools_called"].append({
                                            "tool_id": response_chunk.get("tool_id"),
                                            "tool_name": response_chunk.get("tool_name"),
                                            "tool_args": response_chunk.get("tool_args"),
                                            "progress": response_chunk.get("progress")
                                        })
                                    elif chunk_type == "tool_end":
                                        conversation_data["mcp_results"].append({
                                            "tool_id": response_chunk.get("tool_id"),
                                            "tool_name": response_chunk.get("tool_name"),
                                            "result": response_chunk.get("result"),
                                            "success": True
                                        })
                                    elif chunk_type == "tool_error":
                                        conversation_data["mcp_results"].append({
                                            "tool_id": response_chunk.get("tool_id"),
                                            "error": response_chunk.get("error"),
                                            "success": False
                                        })
                                    elif chunk_type in ("ai_response_chunk", "ai_thinking_chunk"):
                                        conversation_data["ai_response_parts"].append(response_chunk.get("content", ""))
                                    elif chunk_type == "token_usage":
                                        conversation_data["usage"] = {
                                            "input_tokens": response_chunk.get("input_tokens"),
                                            "output_tokens": response_chunk.get("output_tokens"),
                                            "total_tokens": response_chunk.get("total_tokens")
                                        }
                                    elif chunk_type == "error":
                                        print(f"❌ MCP处理错误: {response_chunk.get('content')}")
                                        break
                            except asyncio.CancelledError:
                                if response_started:
                                    try:
                                        await manager.send_personal_message({"type": "ai_response_end", "content": ""}, websocket)
                                    except Exception:
                                        pass
                                raise
                            except Exception as e:
                                print(f"❌ MCP流式处理异常: {e}")
                            finally:
                                ai_response_final = "".join(conversation_data["ai_response_parts"]) or ""
                                if not ai_response_final and conversation_data["mcp_results"]:
                                    error_results = [r for r in conversation_data["mcp_results"] if not r.get("success", True)]
                                    if error_results:
                                        ai_response_final = "处理过程中遇到错误：\n" + "\n".join([r.get("error", "未知错误") for r in error_results])
                                try:
                                    if chat_db:
                                        inserted_id = await chat_db.save_conversation(
                                            user_input=conversation_data["user_input"],
                                            mcp_tools_called=conversation_data["mcp_tools_called"],
                                            mcp_results=conversation_data["mcp_results"],
                                            ai_response=ai_response_final,
                                            session_id=target_session,
                                            conversation_id=int(target_conv),
                                            username=(mcp_agent.session_contexts.get(current_session_id, {}) or {}).get("username") if hasattr(mcp_agent, 'session_contexts') else None,
                                            user_id=(mcp_agent.session_contexts.get(current_session_id, {}) or {}).get("user_id") if hasattr(mcp_agent, 'session_contexts') else None,
                                            attachments=[{"filename": "(edited)"}],  # 保留字段结构，后续可扩展
                                            usage=conversation_data.get("usage")
                                        )
                                        try:
                                            await manager.send_personal_message({
                                                "type": "record_saved",
                                                "record_id": inserted_id,
                                                "session_id": target_session,
                                                "conversation_id": int(target_conv)
                                            }, websocket)
                                        except Exception:
                                            pass
                                except Exception as e:
                                    print(f"❌ 保存对话记录异常: {e}")
                                finally:
                                    active_stream_tasks.pop(current_session_id, None)

                        task = asyncio.create_task(stream_and_persist_edit())
                        active_stream_tasks[current_session_id] = task
                        continue
                    except Exception as _e:
                        await manager.send_personal_message({
                            "type": "edit_error",
                            "content": f"Edit failed: {_e}"
                        }, websocket)
                        continue
                
                else:
                    await manager.send_personal_message({
                        "type": "error",
                        "content": f"未知消息类型: {message.get('type')}"
                    }, websocket)
                    
            except json.JSONDecodeError:
                await manager.send_personal_message({
                    "type": "error",
                    "content": "Invalid message format. Please send valid JSON."
                }, websocket)
            except Exception as e:
                print(f"❌ WebSocket消息处理异常: {e}")
                import traceback
                traceback.print_exc()
                await manager.send_personal_message({
                    "type": "error",
                    "content": f"处理消息时出错: {str(e)}"
                }, websocket)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"❌ WebSocket错误: {e}")
        manager.disconnect(websocket)

# ─────────── REST API 接口 ───────────

@app.get("/")
async def root():
    """根路径重定向到前端"""
    return {"message": "MCP Web智能助手API", "version": "1.0.0"}

# ─────────── 静态文件服务（可选） ───────────

# 如果要让FastAPI直接服务前端文件，取消下面的注释
# app.mount("/static", StaticFiles(directory="../frontend"), name="static")

if __name__ == "__main__":
    # 开发环境启动
    # 端口可通过环境变量 BACKEND_PORT 覆盖，默认 8003，与前端配置一致
    try:
        port = int(os.getenv("BACKEND_PORT", "8003"))
    except Exception:
        port = 8003
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
