from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Body

from app_main.auth import _auth_user_from_request, get_chat_db

user_models_router = APIRouter(prefix="/api/user", tags=["user_models"])


def init_user_models_dependencies(chat_db):
    # 与其他模块保持一致风格；这里依赖 get_chat_db() 提供实例
    get_chat_db.instance = chat_db


@user_models_router.get("/models")
async def list_user_models(request: Request):
    chat_db = get_chat_db()
    user = _auth_user_from_request(request)
    try:
        # 确保表存在（幂等）
        try:
            await __import__('aiosqlite').connect  # noqa
        except Exception:
            pass
        # 直接用数据库实例的路径
        import aiosqlite
        async with aiosqlite.connect(chat_db.db_path) as db:
            cur = await db.execute(
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
            await db.execute("CREATE INDEX IF NOT EXISTS idx_user_models_user ON user_models(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_user_models_profile ON user_models(user_id, profile_id)")
            await db.commit()

        # 查询
        import aiosqlite
        async with aiosqlite.connect(chat_db.db_path) as db:
            cur = await db.execute(
                """
                SELECT id, profile_id, label, base_url, model, temperature, timeout, system_prompt, enabled
                FROM user_models WHERE user_id = ? ORDER BY id DESC
                """,
                (int(user["id"]),)
            )
            rows = await cur.fetchall()
            data = []
            for r in rows:
                data.append({
                    "id": int(r[0]),
                    "profile_id": r[1],
                    "label": r[2],
                    "base_url": r[3],
                    "model": r[4],
                    "temperature": r[5],
                    "timeout": r[6],
                    "system_prompt": r[7],
                    "enabled": bool(r[8]),
                })
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户自定义模型失败: {e}")


@user_models_router.get("/tushare_token")
async def get_tushare_token_status(request: Request):
    """查询当前用户是否已设置 Tushare Token 和启用状态（不返回明文）。"""
    chat_db = get_chat_db()
    user = _auth_user_from_request(request)
    try:
        import aiosqlite
        async with aiosqlite.connect(chat_db.db_path) as db:
            cur = await db.execute("SELECT tushare_token, tushare_token_enabled FROM users WHERE id = ?", (int(user["id"]),))
            row = await cur.fetchone()
            token = row[0] if row else None
            enabled = bool(row[1]) if (row and len(row) > 1) else False
            return {
                "success": True, 
                "is_set": bool((token or '').strip()),
                "enabled": enabled
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@user_models_router.post("/tushare_token")
async def set_tushare_token(request: Request, payload: dict = Body(default={})):  # { token?: string, clear?: boolean, enabled?: boolean }
    """设置或清空当前用户的 Tushare Token，并可设置启用状态。"""
    chat_db = get_chat_db()
    user = _auth_user_from_request(request)
    token = (payload or {}).get("token")
    clear = str((payload or {}).get("clear", "")).strip().lower() in {"1", "true", "yes", "on"}
    enabled = payload.get("enabled")  # 可选：启用/禁用
    
    if clear:
        token = None
        enabled = False  # 清除时自动禁用
    
    # 仅当既没有 token、也没有 enabled、也不是 clear 时才报错
    if not clear and not (str(token or '').strip()) and enabled is None:
        raise HTTPException(status_code=400, detail="token 不能为空，或使用 clear=true 清除")
    
    # 如果只是切换启用状态（没有提供 token），则只更新 enabled 字段
    if enabled is not None and not token and not clear:
        # 仅更新启用状态
        try:
            ok = await chat_db.set_user_tushare_token(
                int(user["id"]), 
                None,  # 不修改 token
                enabled,
                only_update_enabled=True  # 关键：只更新启用状态
            )
            if not ok:
                raise HTTPException(status_code=500, detail="保存失败")
            return {"success": True}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"保存失败: {e}")
    
    # 保存或清除 token
    try:
        ok = await chat_db.set_user_tushare_token(
            int(user["id"]), 
            (str(token).strip() if token else None),
            enabled if enabled is not None else None
        )
        if not ok:
            raise HTTPException(status_code=500, detail="保存失败")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")


@user_models_router.post("/models")
async def create_user_model(request: Request, payload: Dict[str, Any]):
    chat_db = get_chat_db()
    user = _auth_user_from_request(request)
    label = (payload or {}).get("label", "").strip()
    api_key = (payload or {}).get("api_key", "").strip()
    model = (payload or {}).get("model", "").strip()
    if not label or not api_key or not model:
        raise HTTPException(status_code=400, detail="label、api_key、model 为必填")
    profile_id = (payload or {}).get("profile_id", "").strip() or None
    base_url = (payload or {}).get("base_url", "").strip()
    temperature = float((payload or {}).get("temperature", 0.2))
    timeout = int((payload or {}).get("timeout", 60))
    system_prompt = (payload or {}).get("system_prompt", "").strip()
    enabled = 1 if str((payload or {}).get("enabled", 1)).strip().lower() not in {"0","false","no","off"} else 0
    try:
        import aiosqlite
        async with aiosqlite.connect(chat_db.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_models (user_id, profile_id, label, api_key, base_url, model, temperature, timeout, system_prompt, enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (int(user["id"]), profile_id, label, api_key, base_url, model, temperature, timeout, system_prompt, enabled)
            )
            cur = await db.execute("SELECT last_insert_rowid()")
            row = await cur.fetchone()
            await db.commit()
            new_id = int(row[0]) if row else None
        return {"success": True, "id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {e}")


@user_models_router.put("/models/{model_id}")
async def update_user_model(model_id: int, request: Request, payload: Dict[str, Any]):
    chat_db = get_chat_db()
    user = _auth_user_from_request(request)
    allowed = {"profile_id","label","api_key","base_url","model","temperature","timeout","system_prompt","enabled"}
    fields = []
    params = []
    for k, v in (payload or {}).items():
        if k in allowed:
            fields.append(f"{k} = ?")
            if k == "temperature":
                params.append(float(v))
            elif k == "timeout":
                params.append(int(v))
            elif k == "enabled":
                params.append(0 if str(v).strip().lower() in {"0","false","no","off"} else 1)
            else:
                params.append((str(v) if v is not None else "").strip())
    if not fields:
        return {"success": True}
    params.extend([int(user["id"]), int(model_id)])
    try:
        import aiosqlite
        async with aiosqlite.connect(chat_db.db_path) as db:
            await db.execute(
                f"UPDATE user_models SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND id = ?",
                tuple(params)
            )
            await db.commit()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {e}")


@user_models_router.delete("/models/{model_id}")
async def delete_user_model(model_id: int, request: Request):
    chat_db = get_chat_db()
    user = _auth_user_from_request(request)
    try:
        import aiosqlite
        async with aiosqlite.connect(chat_db.db_path) as db:
            await db.execute(
                "DELETE FROM user_models WHERE user_id = ? AND id = ?",
                (int(user["id"]), int(model_id))
            )
            await db.commit()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")

