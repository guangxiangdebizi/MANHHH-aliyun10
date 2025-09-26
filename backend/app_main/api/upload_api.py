# 文件上传API模块
"""
文件上传相关的API接口
"""

import os
import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException

# 创建路由器
upload_router = APIRouter(prefix="/api", tags=["upload"])

# 上传目录配置
UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

@upload_router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文件，返回可访问的URL路径。"""
    try:
        # 基础校验与限制（可按需调整）
        original_name = file.filename or "file"
        ext = os.path.splitext(original_name)[1]
        # 生成唯一文件名，避免重复
        unique_name = f"{uuid.uuid4().hex}{ext}"

        # 使用日期子目录，便于管理
        date_dir = datetime.now().strftime("%Y%m%d")
        target_dir = os.path.join(UPLOADS_DIR, date_dir)
        os.makedirs(target_dir, exist_ok=True)

        target_path = os.path.join(target_dir, unique_name)
        content = await file.read()
        # 简单大小限制：20MB
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 20MB)")
        with open(target_path, "wb") as f:
            f.write(content)

        # 返回静态访问路径（相对API根路径）
        url_path = f"/uploads/{date_dir}/{unique_name}"
        return {"success": True, "data": {"filename": original_name, "stored_as": unique_name, "url": url_path}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")
