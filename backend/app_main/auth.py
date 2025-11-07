# auth.py
"""
认证模块 - 处理用户登录、注册、密码修改等认证相关业务
"""

import os
import smtplib
from typing import Dict, Any
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formataddr

from fastapi import APIRouter, HTTPException, Request, Body
import jwt as pyjwt
from passlib.context import CryptContext

# 认证配置
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-key-change-me")
JWT_ALG = "HS256"
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# 邮件配置（从环境变量读取）
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_SECURE = os.getenv("SMTP_SECURE", "true").lower() == "true"
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "MCP Assistant")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5050")

# 创建认证路由器
auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])

def _auth_user_from_request(request: Request) -> Dict[str, Any]:
    """从请求中验证用户身份并返回用户信息"""
    auth = request.headers.get("Authorization", "").strip()
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少认证信息")
    token = auth[7:].strip()
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = payload.get("uid")
        username = payload.get("usr")
        if not uid or not username:
            raise ValueError("invalid token")
        return {"id": uid, "username": username}
    except Exception:
        raise HTTPException(status_code=401, detail="认证失败，请重新登录")

def _send_email(to_email: str, subject: str, html: str) -> None:
    """发送邮件的辅助函数"""
    msg = MIMEText(html, 'html', 'utf-8')
    msg['From'] = formataddr((SMTP_FROM_NAME, SMTP_USER))
    msg['To'] = to_email
    msg['Subject'] = subject
    
    if SMTP_SECURE:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        try:
            server.ehlo()
        except Exception:
            pass
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        try:
            server.ehlo()
            server.starttls()
            server.ehlo()
        except Exception:
            pass
    
    try:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [to_email], msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass

# 依赖注入函数
def get_chat_db():
    """获取 chat_db 实例的依赖注入函数，需要在主模块中设置"""
    from fastapi import HTTPException
    # 这里需要从全局变量或依赖注入获取 chat_db
    # 将在 main.py 中通过闭包或其他方式设置
    if not hasattr(get_chat_db, 'instance'):
        raise HTTPException(status_code=503, detail="数据库未初始化")
    return get_chat_db.instance

# 认证路由处理函数
@auth_router.post("/register")
async def register(payload: Dict[str, Any]):
    """用户注册接口"""
    chat_db = get_chat_db()
        
    username = (payload or {}).get("username", "").strip()
    email = (payload or {}).get("email", "").strip().lower()
    password = (payload or {}).get("password", "").strip()
    confirm_password = (payload or {}).get("confirm_password", "").strip()
    
    if not username or not email or not password or not confirm_password:
        raise HTTPException(status_code=400, detail="用户名、邮箱与密码不能为空")
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    
    # 基础格式校验
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="密码长度至少8位")
    
    # 唯一性校验
    existing_u = await chat_db.get_user_by_username(username)
    if existing_u:
        raise HTTPException(status_code=400, detail="用户名已存在")
    existing_e = await chat_db.get_user_by_email(email)
    if existing_e:
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    
    # 邮箱验证码（必须）
    code = (payload or {}).get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="请填写邮箱验证码")
    ok = await chat_db.verify_code(email=email, code=code, purpose="register")
    if not ok:
        raise HTTPException(status_code=400, detail="邮箱验证码无效或已过期")
    
    # 哈希密码
    password_hash = pwd_context.hash(password)
    ok = await chat_db.create_user(username, email, password_hash)
    if not ok:
        raise HTTPException(status_code=500, detail="注册失败")
    return {"success": True}

@auth_router.post("/send_code")
async def send_code(payload: Dict[str, Any]):
    """发送邮箱验证码：purpose=register/reset_password"""
    chat_db = get_chat_db()
        
    email = (payload or {}).get("email", "").strip().lower()
    purpose = (payload or {}).get("purpose", "register").strip()
    
    if not email:
        raise HTTPException(status_code=400, detail="邮箱不能为空")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    
    # 基础SMTP配置校验
    if not SMTP_USER or not SMTP_PASS:
        raise HTTPException(status_code=500, detail="邮件服务未配置(SMTP_USER/SMTP_PASS)，请先在 .env 设置并重启后端")
    
    # 频率限制
    can = await chat_db.can_send_code(email, purpose, min_interval_seconds=60)
    if not can:
        raise HTTPException(status_code=429, detail="发送过于频繁，请稍后再试")
    
    # 生成6位验证码
    import random
    code = "".join([str(random.randint(0,9)) for _ in range(6)])
    ok = await chat_db.create_verification_code(email, code, purpose, ttl_minutes=10)
    if not ok:
        raise HTTPException(status_code=500, detail="创建验证码失败")
    
    # 发送邮件
    try:
        html = f"""
        <div style='font-family:Arial,Helvetica,sans-serif;'>
          <p>您的验证码为：<strong style='font-size:18px'>{code}</strong></p>
          <p>10分钟内有效。用于 {purpose}。</p>
          <p style='color:#718096'>如果不是您本人操作，请忽略此邮件。</p>
        </div>
        """
        _send_email(email, "您的验证码", html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送邮件失败: {e}")
    return {"success": True}

@auth_router.post("/reset_password")
async def reset_password(payload: Dict[str, Any]):
    """找回密码：通过邮箱验证码重置新密码。

    请求体：{ email: str, code: str, new_password: str, confirm_password?: str }
    流程：
      1) 校验参数与格式
      2) 校验用户是否存在（通过邮箱）
      3) 校验验证码（purpose=reset_password）
      4) 通过后更新密码
    """
    chat_db = get_chat_db()

    email = (payload or {}).get("email", "").strip().lower()
    code = (payload or {}).get("code", "").strip()
    new_password = (payload or {}).get("new_password", "").strip()
    confirm_password = (payload or {}).get("confirm_password", "").strip()

    if not email or not code or not new_password:
        raise HTTPException(status_code=400, detail="缺少必要参数")
    if "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if confirm_password and new_password != confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="密码长度至少8位")

    user = await chat_db.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    ok_code = await chat_db.verify_code(email=email, code=code, purpose="reset_password")
    if not ok_code:
        raise HTTPException(status_code=400, detail="邮箱验证码无效或已过期")

    try:
        async with __import__('aiosqlite').connect(chat_db.db_path) as db:
            await db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (pwd_context.hash(new_password), user["id"]) 
            )
            await db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重置密码失败: {e}")
    return {"success": True}

@auth_router.post("/login")
async def login(payload: Dict[str, Any]):
    """用户登录接口 - 支持用户名或邮箱+密码登录"""
    chat_db = get_chat_db()
        
    username = (payload or {}).get("username", "").strip()
    password = (payload or {}).get("password", "").strip()
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名/邮箱与密码不能为空")
    
    # 判断输入的是邮箱还是用户名
    if "@" in username:
        # 当作邮箱处理
        user = await chat_db.get_user_by_email(username.lower())
    else:
        # 当作用户名处理
        user = await chat_db.get_user_by_username(username)
    
    if not user:
        raise HTTPException(status_code=401, detail="用户名/邮箱或密码错误")
    
    if not pwd_context.verify(password, user.get("password_hash") or ""):
        raise HTTPException(status_code=401, detail="用户名/邮箱或密码错误")
    
    token = pyjwt.encode(
        {"uid": user["id"], "usr": user["username"], "iat": int(datetime.now().timestamp())}, 
        JWT_SECRET, 
        algorithm=JWT_ALG
    )
    return {
        "success": True, 
        "token": token, 
        "user": {"id": user["id"], "username": user["username"], "credits": user.get("credits")}
    }

@auth_router.post("/login_with_code")
async def login_with_code(payload: Dict[str, Any]):
    """邮箱验证码登录接口 - 无需密码"""
    chat_db = get_chat_db()
        
    email = (payload or {}).get("email", "").strip().lower()
    code = (payload or {}).get("code", "").strip()
    
    if not email or not code:
        raise HTTPException(status_code=400, detail="邮箱和验证码不能为空")
    
    if "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    
    # 验证邮箱验证码
    ok = await chat_db.verify_code(email=email, code=code, purpose="login")
    if not ok:
        raise HTTPException(status_code=400, detail="验证码无效或已过期")
    
    # 通过邮箱查找用户
    user = await chat_db.get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="该邮箱未注册")
    
    # 生成登录token
    token = pyjwt.encode(
        {"uid": user["id"], "usr": user["username"], "iat": int(datetime.now().timestamp())}, 
        JWT_SECRET, 
        algorithm=JWT_ALG
    )
    return {
        "success": True, 
        "token": token, 
        "user": {"id": user["id"], "username": user["username"], "credits": user.get("credits")}
    }

@auth_router.post("/change_password")
async def change_password(request: Request, payload: Dict[str, Any]):
    """用户修改密码：必须登录（Bearer），并提供旧密码与新密码。"""
    chat_db = get_chat_db()

    # 从 Bearer Token 获取当前用户
    authed_user = _auth_user_from_request(request)

    old_password = (payload or {}).get("old_password", "").strip()
    new_password = (payload or {}).get("new_password", "").strip()

    if not old_password or not new_password:
        raise HTTPException(status_code=400, detail="缺少必要参数")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="密码长度至少8位")

    # 查询并校验旧密码
    user = await chat_db.get_user_by_username(authed_user["username"])
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if not pwd_context.verify(old_password, user.get("password_hash") or ""):
        raise HTTPException(status_code=401, detail="旧密码不正确")

    # 更新为新密码
    try:
        async with __import__('aiosqlite').connect(chat_db.db_path) as db:
            await db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (pwd_context.hash(new_password), user["id"]) 
            )
            await db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新密码失败: {e}")
    return {"success": True}

@auth_router.post("/update_profile")
async def update_profile(payload: Dict[str, Any]):
    """更新用户名。若新用户名已存在则报错。"""
    chat_db = get_chat_db()
        
    username = (payload or {}).get("username", "").strip()
    new_username = (payload or {}).get("new_username", "").strip()
    
    if not username or not new_username:
        raise HTTPException(status_code=400, detail="缺少必要参数")
    
    # 新用户名占用校验
    existing = await chat_db.get_user_by_username(new_username)
    if existing:
        raise HTTPException(status_code=400, detail="新用户名已被占用")
    
    user = await chat_db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    try:
        async with __import__('aiosqlite').connect(chat_db.db_path) as db:
            await db.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (new_username, user["id"]) 
            )
            await db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新用户名失败: {e}")
    return {"success": True}

@auth_router.post("/update_email")
async def update_email(request: Request, payload: Dict[str, Any]):
    """修改邮箱：需登录 + 邮箱验证码验证。

    请求体：{ new_email: str, code: str }
    流程：
      1) 校验参数与格式
      2) 校验邮箱未被占用
      3) 校验验证码（purpose=update_email）
      4) 通过后更新邮箱
    """
    chat_db = get_chat_db()
        
    user = _auth_user_from_request(request)
    new_email = (payload or {}).get("new_email", "").strip().lower()
    code = (payload or {}).get("code", "").strip()
    
    if not new_email or not code:
        raise HTTPException(status_code=400, detail="缺少必要参数")
    if "@" not in new_email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    
    # 邮箱唯一性
    exists = await chat_db.get_user_by_email(new_email)
    if exists and int(exists.get("id")) != int(user["id"]):
        raise HTTPException(status_code=400, detail="邮箱已被占用")
    
    # 校验验证码
    ok_code = await chat_db.verify_code(email=new_email, code=code, purpose="update_email")
    if not ok_code:
        raise HTTPException(status_code=400, detail="邮箱验证码无效或已过期")
    
    try:
        async with __import__('aiosqlite').connect(chat_db.db_path) as db:
            await db.execute(
                "UPDATE users SET email = ? WHERE id = ?",
                (new_email, user["id"])
            )
            await db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新邮箱失败: {e}")
    return {"success": True}

@auth_router.get("/credits")
async def get_credits(request: Request):
    """查询当前登录用户的积分余额（通过Authorization Bearer校验）。"""
    chat_db = get_chat_db()
    user = _auth_user_from_request(request)
    full = await chat_db.get_user_by_username(user["username"]) or {}
    return {"success": True, "credits": full.get("credits", 0)}

# 导出认证相关的辅助函数，供其他模块使用
__all__ = ["auth_router", "_auth_user_from_request", "_send_email"]