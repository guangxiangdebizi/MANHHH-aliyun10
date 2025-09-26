"""
多模态处理模块
"""

import os
import base64
import mimetypes
from pathlib import Path
from typing import List, Dict, Any, Optional


class MultimodalProcessor:
    """多模态消息处理器"""
    
    def __init__(self, public_base_url: str = "", history_image_max_file_bytes: int = 2 * 1024 * 1024):
        self.public_base_url = public_base_url.strip().rstrip("/")
        self.history_image_max_file_bytes = history_image_max_file_bytes
    
    def attachment_is_image(self, name_or_url: str) -> bool:
        """基于扩展名的简单判断（不读取文件）。"""
        try:
            suffix = (Path(name_or_url).suffix or "").lower()
            if not suffix:
                return False
            image_exts = {
                ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"
            }
            return suffix in image_exts
        except Exception:
            return False

    def build_image_url_from_relative(self, rel_url: str) -> Optional[str]:
        """将数据库里 '/uploads/...' 的相对路径转为模型可用URL。
        优先使用 PUBLIC_BASE_URL 直接拼接；否则读取本地文件并转为 dataURL（受大小限制）。
        """
        try:
            if not isinstance(rel_url, str) or not rel_url.strip():
                return None
            rel = rel_url.strip()
            if not rel.startswith("/"):
                rel = "/" + rel

            # 1) 公网URL模式
            if self.public_base_url:
                return f"{self.public_base_url}{rel}"

            # 2) dataURL模式（读取本地 uploads 文件）
            # 绝对路径：backend 目录为基准
            abs_path = Path(__file__).parent.parent / rel.lstrip("/")
            if not abs_path.exists() or not abs_path.is_file():
                return None
            file_size = abs_path.stat().st_size
            if file_size > max(0, int(self.history_image_max_file_bytes or 0)):
                return None

            mime, _ = mimetypes.guess_type(str(abs_path))
            if not mime or not mime.startswith("image/"):
                # 基于扩展名的兜底
                ext = (abs_path.suffix or '').lower().lstrip('.')
                if ext:
                    mime = f"image/{ext}"
                else:
                    mime = "image/jpeg"

            data = abs_path.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception as _e:
            try:
                print(f"⚠️ 构建历史图片URL失败: {_e}")
            except Exception:
                pass
            return None

    def convert_multimodal_to_text(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将多模态消息转换为纯文本消息"""
        converted_messages = []
        for msg in messages:
            if msg.get("role") != "user":
                converted_messages.append(msg)
                continue
            
            content = msg.get("content")
            if isinstance(content, list):
                # 提取文本部分和图片信息
                text_parts = []
                image_count = 0
                image_names = []
                
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif part.get("type") == "image_url":
                            image_count += 1
                            # 尝试从URL推断文件名
                            url = part.get("image_url", {}).get("url", "")
                            if "/uploads/" in url:
                                try:
                                    filename = url.split("/")[-1]
                                    image_names.append(filename)
                                except:
                                    image_names.append(f"image_{image_count}")
                            else:
                                image_names.append(f"image_{image_count}")
                
                # 构建纯文本内容
                final_text = " ".join(text_parts).strip()
                if image_count > 0:
                    image_info = f"\n\n[注意: 上传了 {image_count} 张图片: {', '.join(image_names)}，但当前模型不支持图片识别，已忽略图片内容]"
                    final_text = (final_text + image_info).strip()
                
                converted_messages.append({"role": "user", "content": final_text})
            else:
                converted_messages.append(msg)
        
        return converted_messages

    @staticmethod
    def is_multimodal_error(error_str: str) -> bool:
        """判断是否为多模态格式不支持的错误"""
        if not isinstance(error_str, str):
            return False
        error_lower = error_str.lower()
        indicators = [
            "failed to deserialize",
            "chatcompletionrequestcontent",
            "data did not match any variant",
            "untagged enum",
            "invalid content format",
            "unsupported message format"
        ]
        return any(indicator in error_lower for indicator in indicators)
