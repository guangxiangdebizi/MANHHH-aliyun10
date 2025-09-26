"""
消息处理和历史构建模块
"""

from typing import List, Dict, Any, Optional
from .multimodal import MultimodalProcessor


class MessageProcessor:
    """消息处理器"""
    
    def __init__(self, multimodal_processor: MultimodalProcessor, 
                 history_images_max_total: int = 6, 
                 history_images_max_per_record: int = 3):
        self.multimodal = multimodal_processor
        self.history_images_max_total = history_images_max_total
        self.history_images_max_per_record = history_images_max_per_record

    def build_shared_history(self, history: List[Dict[str, Any]], 
                           user_input, force_text_only: bool = False,
                           concise: bool = False,
                           max_tool_summary_len: int = 120) -> List[Dict[str, Any]]:
        """构建共享消息历史
        Args:
            history: 数据库读取的历史记录数组
            user_input: 当前用户输入（文本或多模态 content parts）
            force_text_only: 是否强制将多模态降级为文本
            concise: 精简模式，只保留用户问、AI答，工具结果以简短摘要注记（不限制数量）
            max_tool_summary_len: 单个工具结果摘要的最大字符数
        """
        shared_history: List[Dict[str, Any]] = []
        injected_images_total = 0
        

        if history:
            for record in history:
                # 历史用户消息
                try:
                    attachments = record.get('attachments') or []
                except Exception:
                    attachments = []
                user_text = record.get('user_input') or ""

                # 尝试将历史图片作为多模态注入
                content_parts: List[Any] = []
                if isinstance(user_text, str) and user_text.strip():
                    content_parts.append({"type": "text", "text": user_text})

                if not force_text_only and attachments and injected_images_total < self.history_images_max_total:
                    try:
                        # 逐条记录内限制
                        per_record = 0
                        for att in attachments:
                            if injected_images_total >= self.history_images_max_total:
                                break
                            if per_record >= self.history_images_max_per_record:
                                break
                            url = str(att.get('url') or '').strip()
                            filename = str(att.get('filename') or '')
                            if not url:
                                continue
                            if not self.multimodal.attachment_is_image(filename or url):
                                continue
                            # 构造图片可用URL（公网或dataURL）
                            image_url = self.multimodal.build_image_url_from_relative(url)
                            if not image_url:
                                continue
                            content_parts.append({"type": "image_url", "image_url": {"url": image_url}})
                            per_record += 1
                            injected_images_total += 1
                    except Exception as _e:
                        try:
                            print(f"⚠️ 注入历史图片失败，已跳过: {_e}")
                        except Exception:
                            pass

                # 若存在图片或文本，则以 parts 形式注入；否则退回到空串（避免传空对象）
                if content_parts:
                    shared_history.append({"role": "user", "content": content_parts})
                else:
                    # 保持向后兼容：无图片时，附上附件说明文本
                    fallback_text = user_text
                    if attachments:
                        try:
                            names = ", ".join([str(a.get('filename') or '') for a in attachments if a])
                            urls = "; ".join([str(a.get('url') or '') for a in attachments if a])
                            note = f"\n\n[Attachments]\nfilenames: {names}\nurls: {urls}\nIf needed, use tool 'preview_uploaded_file' with the url string to preview content."
                            fallback_text = (fallback_text or '') + note
                        except Exception:
                            pass
                    shared_history.append({"role": "user", "content": fallback_text})

                # 回放历史中的工具结果
                # - 正常模式：以摘要文本列出每条工具调用与结果
                # - 精简模式：为每次工具调用注入简短结果摘要（不限制数量）
                try:
                    mcp_results = record.get('mcp_results') or []
                except Exception:
                    mcp_results = []
                if mcp_results:
                    if concise:
                        try:
                            items: List[str] = []
                            for r in mcp_results:
                                nm = str((r or {}).get('tool_name') or (r or {}).get('name') or '').strip() or 'tool'
                                raw = str((r or {}).get('result') or (r or {}).get('error') or '').strip()
                                # 生成简短摘要
                                summary = " ".join(raw.split())  # 压缩空白
                                if len(summary) > max_tool_summary_len:
                                    summary = summary[:max_tool_summary_len] + "..."
                                ok = (r or {}).get('success', True)
                                items.append(f"{nm} ({'OK' if ok else 'ERR'}): {summary}" if summary else f"{nm} ({'OK' if ok else 'ERR'})")
                            if items:
                                note = "[Tool results] " + "; ".join(items)
                                shared_history.append({"role": "assistant", "content": note})
                        except Exception:
                            pass
                    else:
                        try:
                            snippets = []
                            for r in mcp_results:
                                tool_name = str((r or {}).get('tool_name') or (r or {}).get('name') or 'tool')
                                ok = (r or {}).get('success', True)
                                res_text = str((r or {}).get('result') or (r or {}).get('error') or '')
                                snippets.append(f"- {tool_name} => {'OK' if ok else 'ERROR'}: {res_text}")
                            if snippets:
                                summary_text = "[Previous tool results]\n" + "\n".join(snippets)
                                shared_history.append({"role": "assistant", "content": summary_text})
                        except Exception:
                            pass

                # 历史助手消息
                if record.get('ai_response'):
                    shared_history.append({"role": "assistant", "content": record['ai_response']})
        
        # 允许 user_input 为多模态列表（OpenAI风格 content parts）
        if isinstance(user_input, list):
            shared_history.append({"role": "user", "content": user_input})
        else:
            shared_history.append({"role": "user", "content": user_input})

        return shared_history
