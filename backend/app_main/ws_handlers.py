import json
from typing import Dict


async def handle_ping(websocket, manager):
    await manager.send_personal_message({
        "type": "pong",
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }, websocket)


async def handle_pause(websocket, manager, active_stream_tasks: Dict[str, object]):
    try:
        current_session_id = manager.get_session_id(websocket)
        task = active_stream_tasks.pop(current_session_id, None)
        if task and not task.done():
            task.cancel()
    except Exception:
        pass
    await manager.send_personal_message({"type": "ai_response_end", "content": ""}, websocket)


async def handle_resume_conversation(message, websocket, manager, mcp_agent):
    try:
        target_session = str(message.get("session_id") or "").strip()
        target_conv = message.get("conversation_id")
        if not target_session or target_conv is None:
            await manager.send_personal_message({
                "type": "resume_error",
                "content": "Missing session_id or conversation_id"
            }, websocket)
            return
        current_session_id = manager.get_session_id(websocket)
        if not hasattr(mcp_agent, 'session_contexts'):
            mcp_agent.session_contexts = {}
        session_ctx = mcp_agent.session_contexts.get(current_session_id, {})
        session_ctx["effective_session_id"] = target_session
        session_ctx["effective_conversation_id"] = int(target_conv)
        mcp_agent.session_contexts[current_session_id] = session_ctx
        await manager.send_personal_message({
            "type": "resume_ok",
            "session_id": target_session,
            "conversation_id": int(target_conv)
        }, websocket)
    except Exception as _e:
        await manager.send_personal_message({
            "type": "resume_error",
            "content": f"Resume failed: {_e}"
        }, websocket)


