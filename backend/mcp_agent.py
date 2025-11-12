"""
MCP智能体封装 - 为Web后端使用
基于 test.py 中的 SimpleMCPAgent，优化为适合WebSocket流式推送的版本
"""

import os
import json
import asyncio
from typing import Dict, List, Any, AsyncGenerator, Optional
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv, find_dotenv
import re
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
import contextvars
import pymysql

# 导入模块化组件
from mcp_modules.config import MCPConfig
from mcp_modules.multimodal import MultimodalProcessor
from mcp_modules.model_manager import ModelManager
from mcp_modules.message_processor import MessageProcessor
from get_mcp_tools import MCPToolsManager
from mcp_modules.agent_orchestrator import AgentOrchestrator

# ─────────── 1. MCP配置管理 ───────────
# 已移至 mcp_agent/config.py


# ─────────── 3. Web版MCP智能体 ───────────
class WebMCPAgent:
    """Web版MCP智能体 - 支持流式推送"""

    def __init__(self):
        # 修复：使用backend目录下的配置文件
        config_path = Path(__file__).parent / "mcp.json"
        self.config = MCPConfig(str(config_path))
        self.llm = None
        self.llm_tools = None  # 绑定工具用于判定与工具阶段
        self.llm_nontool = None  # 无工具实例，仅用于工具内部如SQL重写
        
        # 初始化工具管理器
        self.tools_manager = MCPToolsManager()
        # 兼容性属性（指向工具管理器的属性）
        self.tools = self.tools_manager.tools
        self.tools_by_server = self.tools_manager.tools_by_server
        self.server_configs = self.tools_manager.server_configs
        self.mcp_client = self.tools_manager.mcp_client

        # 加载 .env 并设置API环境变量（覆盖已存在的环境变量）
        try:
            load_dotenv(find_dotenv(), override=True)
        except Exception:
            # 忽略 .env 加载错误，继续从系统环境读取
            pass

        # 初始化模块化组件
        self.model_manager = ModelManager()

        # 从模型管理器获取配置（向后兼容）
        self.api_key = self.model_manager.api_key
        self.base_url = self.model_manager.base_url
        self.model_name = self.model_manager.model_name
        self.llm_profiles = self.model_manager.llm_profiles
        self.default_profile_id = self.model_manager.default_profile_id
        self.temperature = self.model_manager.temperature
        self.timeout = self.model_manager.timeout

        # 将关键配置同步到环境（供底层SDK使用），不覆盖外部已设值
        if self.api_key and not os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = self.api_key
        if self.base_url and not os.getenv("OPENAI_BASE_URL"):
            os.environ["OPENAI_BASE_URL"] = self.base_url

        # 会话上下文（存放每个 session 的 msid 等）
        self.session_contexts: Dict[str, Dict[str, Any]] = {}
        
        # 历史图片配置
        try:
            public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip()
            history_image_max_file_bytes = int(os.getenv("HISTORY_IMAGE_MAX_FILE_BYTES", str(2 * 1024 * 1024)))
        except Exception:
            public_base_url = ""
            history_image_max_file_bytes = 2 * 1024 * 1024
            
        self.multimodal_processor = MultimodalProcessor(public_base_url, history_image_max_file_bytes)
        
        try:
            history_images_max_total = int(os.getenv("HISTORY_IMAGES_MAX_TOTAL", "6"))
            history_images_max_per_record = int(os.getenv("HISTORY_IMAGES_MAX_PER_RECORD", "3"))
        except Exception:
            history_images_max_total = 6
            history_images_max_per_record = 3
            
        self.message_processor = MessageProcessor(self.multimodal_processor, history_images_max_total, history_images_max_per_record)
        # 当前会话ID上下文变量（用于工具在运行时识别会话）
        self._current_session_id_ctx: contextvars.ContextVar = contextvars.ContextVar("current_session_id", default=None)
        
        # 记录不支持多模态的模型（避免重复尝试）
        self._non_multimodal_models: set = set()

        # Agent 编排器
        self.agent_orchestrator = AgentOrchestrator(
            tools_manager=self.tools_manager,
            message_processor=self.message_processor,
            model_manager=self.model_manager,
            get_llm_bundle_fn=self._get_or_create_llm_instances,
            current_session_id_ctx=self._current_session_id_ctx,
        )

        # 数据库配置（从环境读取，提供默认值）
        self.db_host = os.getenv("DB_HOST", "18.119.46.208")
        self.db_user = os.getenv("DB_USER", "root")
        self.db_password = os.getenv("DB_PASSWORD", "zkshi0101")
        self.db_name = os.getenv("DB_NAME", "ry_vuebak")
        try:
            self.db_port = int(os.getenv("DB_PORT", "3306"))
        except Exception:
            self.db_port = 3306

        # 上下文变量与非多模态集合已在上方初始化

    # 已移至 mcp_agent/model_manager.py



    # 已移至 mcp_agent/multimodal.py

    def _get_current_model_key(self, session_id: Optional[str] = None) -> str:
        """获取当前会话使用的模型标识（用于记录多模态支持情况）"""
        return self.model_manager.get_current_model_key(self.session_contexts, session_id)

    def _convert_multimodal_to_text(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将多模态消息转换为纯文本消息"""
        return self.multimodal_processor.convert_multimodal_to_text(messages)

    def _is_multimodal_error(self, error_str: str) -> bool:
        """判断是否为多模态格式不支持的错误"""
        return MultimodalProcessor.is_multimodal_error(error_str)


    def get_models_info(self) -> Dict[str, Any]:
        """对外暴露的模型档位信息（用于前端展示）。"""
        profiles = self.llm_profiles or {}
        ids = list(profiles.keys())
        non_default_ids = [pid for pid in ids if pid != "default"]

        # 计算有效默认档位：优先采用 LLM_DEFAULT 指定且存在的ID；
        # 否则若存在非 default 档位，取第一个；否则只能是 default（单模型旧兼容）
        if self.default_profile_id and self.default_profile_id != "default" and self.default_profile_id in profiles:
            effective_default = self.default_profile_id
        elif non_default_ids:
            effective_default = non_default_ids[0]
        else:
            effective_default = "default"

        # 展示策略：
        # - 若存在任意非 default 档位，则完全隐藏 default（它只作为别名/回退，不单独显示）。
        # - 若只有 default 一个档位，则显示它（旧版单模型场景）。
        show_ids = non_default_ids if non_default_ids else (["default"] if "default" in profiles else [])

        # 展示所有在 LLM_PROFILES 中声明的档位（不再按 base_url+model 去重）
        models = []
        for pid in show_ids:
            cfg = profiles.get(pid, {})
            models.append({
                "id": pid,
                "label": cfg.get("label", pid),
                "model": cfg.get("model", ""),
                "is_default": pid == effective_default,
            })

        # 极端兜底：如果最终一个都没有（理论不会发生），返回空列表与默认ID
        return {"models": models, "default": effective_default}

    def _get_or_create_llm_instances(self, profile_id: str) -> Dict[str, Any]:
        """根据档位获取/创建对应的 LLM 实例集合：llm、llm_nontool、llm_tools。"""
        return self.model_manager.get_or_create_llm_instances(profile_id, self.tools)

    async def initialize(self):
        """初始化智能体"""
        try:
            # 选择启动档位：优先 LLM_DEFAULT 指定的档位；否则选择任一含 api_key 的档位；
            # 若均无则回退到环境变量 OPENAI_API_KEY；仍无则报错
            startup_cfg = None
            # 优先默认档位
            if self.default_profile_id in self.llm_profiles:
                cfg = self.llm_profiles[self.default_profile_id]
                if cfg.get("api_key") and cfg.get("model"):
                    startup_cfg = cfg
            # 其次任意有效档位
            if startup_cfg is None:
                for _pid, cfg in self.llm_profiles.items():
                    if _pid == "default":
                        continue
                    if cfg.get("api_key") and cfg.get("model"):
                        startup_cfg = cfg
                        break
            # 最后回退到环境变量
            if startup_cfg is None and os.getenv("OPENAI_API_KEY"):
                startup_cfg = {
                    "api_key": os.getenv("OPENAI_API_KEY").strip(),
                    "base_url": os.getenv("OPENAI_BASE_URL", "").strip(),
                    "model": self.model_name,
                    "temperature": self.temperature,
                    "timeout": self.timeout,
                }
            if startup_cfg is None:
                raise RuntimeError("缺少可用的模型档位或 OPENAI_API_KEY，请在 .env 中配置 LLM_PROFILES 对应的 *_API_KEY 或提供 OPENAI_API_KEY")

            # 临时写入环境供底层 SDK 使用
            if startup_cfg.get("api_key"):
                os.environ["OPENAI_API_KEY"] = startup_cfg["api_key"]
            if startup_cfg.get("base_url"):
                os.environ["OPENAI_BASE_URL"] = startup_cfg["base_url"]

            # ChatOpenAI 支持从环境变量读取 base_url
            base_llm = ChatOpenAI(
                model=startup_cfg.get("model", self.model_name),
                temperature=startup_cfg.get("temperature", self.temperature),
                timeout=startup_cfg.get("timeout", self.timeout),
                max_retries=3,
            )
            # 主引用向后兼容
            self.llm = base_llm
            # 无工具实例：当前与 base_llm 相同（无需绑定工具），供工具内部调用
            self.llm_nontool = ChatOpenAI(
                model=startup_cfg.get("model", self.model_name),
                temperature=startup_cfg.get("temperature", self.temperature),
                timeout=startup_cfg.get("timeout", self.timeout),
                max_retries=3,
            )

            # 加载MCP配置并连接
            mcp_config = self.config.load_config()
            server_configs = mcp_config.get("servers", {})
            
            # 准备数据库配置
            db_config = {
                'host': self.db_host,
                'user': self.db_user,
                'password': self.db_password,
                'name': self.db_name,
                'port': self.db_port
            }
            
            # 使用工具管理器初始化工具
            tools_success = await self.tools_manager.initialize_mcp_tools(
                server_configs=server_configs,
                db_config=db_config,
                session_contexts=self.session_contexts,
                current_session_id_ctx=self._current_session_id_ctx,
                llm_nontool=self.llm_nontool
            )
            
            if not tools_success:
                print("⚠️ 工具初始化失败，但继续启动")
            
            # 更新引用（工具管理器可能已更新这些属性）
            self.mcp_client = self.tools_manager.mcp_client

            # 创建工具判定实例（默认档位），其余档位在第一次使用时按需创建
            self.llm_tools = base_llm.bind_tools(self.tools)

            print("🤖 Web MCP智能助手已启动！")
            return True

        except Exception as e:
            import traceback
            print(f"❌ 初始化失败: {e}")
            print(f"📋 详细错误信息:")
            traceback.print_exc()
            
            # 尝试清理可能的连接
            if hasattr(self, 'mcp_client') and self.mcp_client:
                try:
                    await self.mcp_client.close()
                except:
                    pass
            return False

    async def reload_mcp_servers(self) -> bool:
        """重新加载 backend/mcp.json 并重建 MCP 客户端与工具集合。
        用于在运行时更新服务器 headers（例如 Tushare Token）。
        """
        try:
            # 关闭旧客户端
            try:
                if self.tools_manager and self.tools_manager.mcp_client:
                    await self.tools_manager.close()
            except Exception:
                pass

            # 重新加载配置
            mcp_config = self.config.load_config()
            server_configs = mcp_config.get("servers", {})

            # 重新初始化工具
            tools_success = await self.tools_manager.initialize_mcp_tools(
                server_configs=server_configs,
                db_config={
                    'host': self.db_host,
                    'user': self.db_user,
                    'password': self.db_password,
                    'name': self.db_name,
                    'port': self.db_port
                },
                session_contexts=self.session_contexts,
                current_session_id_ctx=self._current_session_id_ctx,
                llm_nontool=self.llm_nontool
            )
            if not tools_success:
                print("⚠️ 工具重载失败")
                return False

            # 更新引用
            self.mcp_client = self.tools_manager.mcp_client
            self.tools = self.tools_manager.tools
            self.tools_by_server = self.tools_manager.tools_by_server

            # 重新绑定工具到当前 LLM
            if self.llm:
                self.llm_tools = self.llm.bind_tools(self.tools)

            print("✅ MCP服务器配置已重载")
            return True
        except Exception as e:
            import traceback
            print(f"❌ 重载MCP服务器失败: {e}")
            traceback.print_exc()
            return False

    def _get_tools_system_prompt(self) -> str:
        """用于工具判定/执行阶段的系统提示词：从环境变量读取或使用默认提示词。"""
        # 尝试从模型管理器获取当前模型的系统提示词
        try:
            model_manager = ModelManager()
            # 获取当前会话ID，优先使用上下文变量
            current_session_id = self._current_session_id_ctx.get(None)
            # 用户自定义模型优先使用自身提示词
            try:
                pf = None
                if current_session_id and self.session_contexts.get(current_session_id):
                    pf = self.session_contexts[current_session_id].get("model")
                if pf and str(pf).startswith("user-"):
                    user_map = self.session_contexts.get(current_session_id, {}).get("user_models") or {}
                    cfg = user_map.get(pf)
                    if cfg and (cfg.get("system_prompt") or "").strip():
                        custom_prompt = (cfg.get("system_prompt") or "").strip()
                    else:
                        custom_prompt = model_manager.get_system_prompt(self.session_contexts, current_session_id)
                else:
                    custom_prompt = model_manager.get_system_prompt(self.session_contexts, current_session_id)
            except Exception:
                custom_prompt = model_manager.get_system_prompt(self.session_contexts, current_session_id)
            
            if custom_prompt:
                # 如果有自定义提示词，安全地替换占位符（避免与 JSON/mermaid 花括号冲突）
                now = datetime.now()
                current_date = now.strftime("%Y年%m月%d日")
                current_time = now.strftime("%H:%M:%S")
                current_datetime = now.strftime("%Y年%m月%d日 %H:%M:%S")
                current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
                current_hour = now.hour
                current_minute = now.minute
                current_timestamp = int(now.timestamp())

                replacements = {
                    "current_date": current_date,
                    "current_time": current_time,
                    "current_datetime": current_datetime,
                    "current_weekday": current_weekday,
                    "current_hour": current_hour,
                    "current_minute": current_minute,
                    "current_timestamp": current_timestamp,
                    "今天的具体时间": current_datetime,
                    "当前时间": current_datetime,
                    "今天": current_date,
                    "现在几点": current_time,
                    "星期几": current_weekday,
                }

                formatted = custom_prompt
                for key, value in replacements.items():
                    try:
                        formatted = formatted.replace("{" + key + "}", str(value))
                    except Exception:
                        # 单个替换失败不影响整体
                        pass
                return formatted
        except Exception as e:
            print(f"⚠️ 获取自定义系统提示词失败，使用默认提示词: {e}")
        
        # 默认提示词（兜底方案，加入可视化规范）
        now = datetime.now()
        current_date = now.strftime("%Y年%m月%d日")
        current_weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
        return (
            "今天是{date}（{weekday}）。你是专业的金融分析师，请你使用工具解答用户的问题！\n\n"
            "【可视化输出（echart + Mermaid）】\n"
            "- 若需展示数据对比/趋势/占比：输出一个合法的 ```echarts 代码块（标准ECharts JSON）\n"
            "- 若需展示流程/结构/时序：输出 ```mermaid 代码块（flowchart/sequence/state/class/gantt/pie）\n"
            "- 每个图一个代码块，尽量不要夹杂解释性文字。"
            "【重要】统一使用 ```echarts 代码块输出 ECharts 配置（option），不要输出 ```chartjs。\\n"
        ).format(date=current_date, weekday=current_weekday)

    def _get_stream_system_prompt(self) -> str:
        """保持接口以兼容旧调用，但当前不再使用流式回答提示词。"""
        return ""

    # 已移至 get_mcp_tools.py

    async def chat_stream(self, user_input, history: List[Dict[str, Any]] = None, session_id: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """流式探测 + 立即中断：
        - 先直接 astream 开流，短暂缓冲并检测 function_call/tool_call；
        - 若检测到工具调用：立即中断本次流式（不下发缓冲），执行工具（非流式），写回 messages 后进入下一轮；
        - 若未检测到工具：将本次流作为最终回答，开始流式推送到结束。
        """
        try:
            if session_id:
                try:
                    self._current_session_id_ctx.set(session_id)
                except Exception:
                    pass
            try:
                preview = user_input if isinstance(user_input, str) else "[multimodal parts]"
                if isinstance(preview, str):
                    preview = preview[:50]
                print(f"🤖 开始处理用户输入: {preview}...")
            except Exception:
                print("🤖 开始处理用户输入 ...")
            yield {"type": "status", "content": "开始生成..."}

            # 依据会话上下文选择模型档位
            profile_id = None
            try:
                if session_id and self.session_contexts.get(session_id):
                    profile_id = self.session_contexts[session_id].get("model") or self.session_contexts[session_id].get("llm_profile")
            except Exception:
                profile_id = None

            # 若选择的是 agent 档位，则走多智能体编排流程
            if profile_id and self.llm_profiles.get(profile_id, {}).get("kind") == "agent":
                agent_cfg = self.llm_profiles.get(profile_id, {})
                async for ev in self.agent_orchestrator.chat_stream(
                    user_input=user_input,
                    history=history,
                    session_id=session_id,
                    agent_cfg=agent_cfg,
                    session_contexts=self.session_contexts,
                ):
                    yield ev
                return

            # 支持用户自定义模型(user-*)
            current_llm_tools = None
            try:
                if profile_id and str(profile_id).startswith("user-"):
                    user_map = self.session_contexts.get(session_id, {}).get("user_models") or {}
                    cfg = user_map.get(profile_id)
                    if cfg:
                        prev_key = os.getenv("OPENAI_API_KEY")
                        prev_base = os.getenv("OPENAI_BASE_URL")
                        try:
                            if cfg.get("api_key"):
                                os.environ["OPENAI_API_KEY"] = cfg["api_key"]
                            if cfg.get("base_url"):
                                os.environ["OPENAI_BASE_URL"] = cfg["base_url"]
                            _base = ChatOpenAI(
                                model=cfg.get("model", self.model_name),
                                temperature=cfg.get("temperature", self.temperature),
                                timeout=cfg.get("timeout", self.timeout),
                                max_retries=3,
                            )
                            current_llm_tools = _base.bind_tools(self.tools)
                        finally:
                            if prev_key is not None:
                                os.environ["OPENAI_API_KEY"] = prev_key
                            if prev_base is not None:
                                os.environ["OPENAI_BASE_URL"] = prev_base
            except Exception as __e:
                print(f"⚠️ 用户自定义模型绑定工具失败: {__e}")
                current_llm_tools = None
            if current_llm_tools is None:
                llm_bundle = self._get_or_create_llm_instances(profile_id)
                current_llm_tools = llm_bundle.get("llm_tools", self.llm_tools)

            # 1) 构建共享消息历史（不包含系统提示，便于两套系统提示分别注入）
            # 检查当前模型是否已知不支持多模态
            current_model_key = self._get_current_model_key(session_id)
            force_text_only = current_model_key in self._non_multimodal_models
            
            # 精简历史：仅保留“问答”为主，工具结果做简要注记，减少噪音
            shared_history = self.message_processor.build_shared_history(
                history, user_input, force_text_only, concise=True
            )

            max_rounds = 25
            round_index = 0
            # 合并两阶段输出为同一条消息：在整个会话回答期间仅发送一次 start，最后一次性 end
            combined_response_started = False
            # 工具调用失败计数器和兜底机制
            consecutive_tool_failures = 0
            max_consecutive_failures = 3  # 连续失败3次触发兜底
            tool_error_history = []  # 记录错误历史
            while round_index < max_rounds:
                round_index += 1
                print(f"🧠 第 {round_index} 轮推理 (双实例：判定工具 + 纯流式回答)...")

                # 2) 使用带工具实例做"流式判定"：
                tools_messages = [{"role": "system", "content": self._get_tools_system_prompt()}] + shared_history
                tool_calls_check = None
                last_usage: Optional[Dict[str, Any]] = None
                buffered_chunks: List[str] = []
                content_preview = ""
                response_started = False
                multimodal_fallback_attempted = False
                
                try:
                    # 抑制MCP客户端在判定工具时的SSE解析错误日志
                    import logging
                    mcp_logger = logging.getLogger('mcp')
                    original_level = mcp_logger.level
                    mcp_logger.setLevel(logging.CRITICAL)
                    
                    try:
                        async for event in current_llm_tools.astream_events(tools_messages, version="v1"):
                            ev = event.get("event")
                            if ev == "on_chat_model_stream":
                                data = event.get("data", {})
                                chunk = data.get("chunk")
                                if chunk is None:
                                    continue
                                try:
                                    content_piece = getattr(chunk, 'content', None)
                                except Exception:
                                    content_piece = None
                                if content_piece:
                                    # 立即向前端流式下发作为最终回复（合并模式：仅首次发送 start）
                                    if not combined_response_started:
                                        yield {"type": "ai_response_start", "content": "AI正在回复..."}
                                        combined_response_started = True
                                    response_started = True
                                    buffered_chunks.append(content_piece)
                                    try:
                                        print(f"📤 [判定LLM流] {content_piece}")
                                    except Exception:
                                        pass
                                    yield {"type": "ai_response_chunk", "content": content_piece}
                            elif ev == "on_chat_model_end":
                                data = event.get("data", {})
                                output = data.get("output")
                                try:
                                    tool_calls_check = getattr(output, 'tool_calls', None)
                                except Exception:
                                    tool_calls_check = None
                                try:
                                    content_preview = getattr(output, 'content', None) or ""
                                except Exception:
                                    content_preview = ""
                                # 捕获真实token用量（若底层返回）
                                try:
                                    usage = getattr(output, 'usage_metadata', None)
                                    if not usage:
                                        meta = getattr(output, 'response_metadata', None) or {}
                                        # 兼容不同SDK字段
                                        usage = meta.get('token_usage') or {
                                            k: meta.get(k) for k in ("input_tokens", "output_tokens", "total_tokens") if k in meta
                                        }
                                    if usage:
                                        # 规范化为dict
                                        if not isinstance(usage, dict):
                                            try:
                                                usage = dict(usage)
                                            except Exception:
                                                usage = {"raw": str(usage)}
                                        last_usage = {
                                            "input_tokens": usage.get("input_tokens"),
                                            "output_tokens": usage.get("output_tokens"),
                                            "total_tokens": usage.get("total_tokens") or (
                                                (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
                                            )
                                        }
                                except Exception:
                                    last_usage = last_usage
                    finally:
                        mcp_logger.setLevel(original_level)
                except Exception as e:
                    error_msg = str(e)
                    print(f"⚠️ 工具判定(流式)失败：{error_msg}")
                    
                    # 检查是否为多模态格式错误，如果是则尝试降级重试
                    if not multimodal_fallback_attempted and self._is_multimodal_error(error_msg):
                        print(f"🔄 检测到多模态格式错误，尝试降级为纯文本模式...")
                        
                        # 标记该模型不支持多模态
                        self._non_multimodal_models.add(current_model_key)
                        
                        # 发送降级提示
                        if not combined_response_started:
                            yield {"type": "ai_response_start", "content": "AI正在回复..."}
                            combined_response_started = True
                        yield {"type": "ai_response_chunk", "content": "⚠️ 当前模型不支持图片识别，已自动转换为纯文本模式处理。\n\n"}
                        
                        # 转换消息为纯文本格式并重试
                        text_only_messages = self._convert_multimodal_to_text(tools_messages)
                        multimodal_fallback_attempted = True
                        
                        try:
                            # 降级重试时也抑制MCP错误日志
                            mcp_logger.setLevel(logging.CRITICAL)
                            try:
                                async for event in current_llm_tools.astream_events(text_only_messages, version="v1"):
                                    ev = event.get("event")
                                    if ev == "on_chat_model_stream":
                                        data = event.get("data", {})
                                        chunk = data.get("chunk")
                                        if chunk is None:
                                            continue
                                        try:
                                            content_piece = getattr(chunk, 'content', None)
                                        except Exception:
                                            content_piece = None
                                        if content_piece:
                                            response_started = True
                                            buffered_chunks.append(content_piece)
                                            try:
                                                print(f"📤 [降级LLM流] {content_piece}")
                                            except Exception:
                                                pass
                                            yield {"type": "ai_response_chunk", "content": content_piece}
                                    elif ev == "on_chat_model_end":
                                        data = event.get("data", {})
                                        output = data.get("output")
                                        try:
                                            tool_calls_check = getattr(output, 'tool_calls', None)
                                        except Exception:
                                            tool_calls_check = None
                                        try:
                                            content_preview = getattr(output, 'content', None) or ""
                                        except Exception:
                                            content_preview = ""
                            finally:
                                mcp_logger.setLevel(original_level)
                        except Exception as fallback_e:
                            print(f"❌ 降级重试也失败：{fallback_e}")
                            tool_calls_check = None
                            content_preview = ""
                    else:
                        tool_calls_check = None
                        content_preview = ""

                if tool_calls_check:
                    # 合并模式：不结束消息，插入分隔后继续执行工具，最终一并结束
                    if response_started and buffered_chunks:
                        yield {"type": "ai_response_chunk", "content": "\n\n"}
                        buffered_chunks = []

                    tool_calls_to_run = tool_calls_check
                    yield {"type": "tool_plan", "content": f"AI决定调用 {len(tool_calls_to_run)} 个工具", "tool_count": len(tool_calls_to_run)}
                    # 写回assistant带tool_calls
                    try:
                        shared_history.append({
                            "role": "assistant",
                            "content": "",
                            "tool_calls": tool_calls_to_run
                        })
                    except Exception:
                        shared_history.append({"role": "assistant", "content": ""})

                    # 执行工具（非流式）
                    exit_to_stream = False
                    current_round_has_error = False
                    for i, tool_call in enumerate(tool_calls_to_run, 1):
                        if isinstance(tool_call, dict):
                            tool_id = tool_call.get('id') or f"call_{i}"
                            fn = tool_call.get('function') or {}
                            tool_name = fn.get('name') or tool_call.get('name') or ''
                            tool_args_raw = fn.get('arguments') or tool_call.get('args') or {}
                        else:
                            tool_id = getattr(tool_call, 'id', None) or f"call_{i}"
                            tool_name = getattr(tool_call, 'name', '') or ''
                            tool_args_raw = getattr(tool_call, 'args', {}) or {}

                        # 解析参数
                        if isinstance(tool_args_raw, str):
                            try:
                                parsed_args = json.loads(tool_args_raw) if tool_args_raw else {}
                            except Exception:
                                parsed_args = {"$raw": tool_args_raw}
                        elif isinstance(tool_args_raw, dict):
                            parsed_args = tool_args_raw
                        else:
                            parsed_args = {"$raw": str(tool_args_raw)}

                        yield {"type": "tool_start", "tool_id": tool_id, "tool_name": tool_name, "tool_args": parsed_args, "progress": f"{i}/{len(tool_calls_to_run)}"}

                        tool_execution_failed = False
                        try:
                            target_tool = None
                            for tool in self.tools:
                                if tool.name == tool_name:
                                    target_tool = tool
                                    break
                            if target_tool is None:
                                error_msg = f"工具 '{tool_name}' 未找到"
                                print(f"❌ {error_msg}")
                                yield {"type": "tool_error", "tool_id": tool_id, "error": error_msg}
                                tool_result = f"错误: {error_msg}"
                                tool_execution_failed = True
                                current_round_has_error = True
                                tool_error_history.append({"tool": tool_name, "error": error_msg})
                            else:
                                # 抑制MCP客户端在工具调用时的SSE解析错误日志
                                import logging
                                mcp_logger = logging.getLogger('mcp')
                                original_level = mcp_logger.level
                                mcp_logger.setLevel(logging.CRITICAL)
                                
                                try:
                                    tool_result = await target_tool.ainvoke(parsed_args)
                                    yield {"type": "tool_end", "tool_id": tool_id, "tool_name": tool_name, "result": str(tool_result)}
                                    # 工具执行成功，重置失败计数器
                                    consecutive_tool_failures = 0
                                    # 不再支持退出工具模式
                                finally:
                                    mcp_logger.setLevel(original_level)
                        except Exception as e:
                            error_msg = f"工具执行出错: {e}"
                            print(f"❌ {error_msg}")
                            yield {"type": "tool_error", "tool_id": tool_id, "error": error_msg}
                            tool_result = f"错误: {error_msg}"
                            tool_execution_failed = True
                            current_round_has_error = True
                            tool_error_history.append({"tool": tool_name, "error": str(e)})

                        # 始终追加 tool 消息，满足 OpenAI 函数调用协议要求
                        # 对于退出工具模式，内容为简单状态，不影响后续回答质量
                        shared_history.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": tool_name,
                            "content": str(tool_result)
                        })

                        if exit_to_stream:
                            break

                    # 更新连续失败计数器
                    if current_round_has_error:
                        consecutive_tool_failures += 1
                        print(f"⚠️ 工具调用失败计数: {consecutive_tool_failures}/{max_consecutive_failures}")
                        
                        # 达到阈值,触发兜底响应
                        if consecutive_tool_failures >= max_consecutive_failures:
                            print(f"🛟 触发兜底机制: 连续{consecutive_tool_failures}次工具调用失败")
                            
                            # 构建错误摘要
                            error_summary = "\n".join([
                                f"- {err.get('tool', '未知工具')}: {err.get('error', '未知错误')}"
                                for err in tool_error_history[-3:]  # 只显示最近3个错误
                            ])
                            
                            # 生成兜底回复提示词
                            fallback_prompt = f"""工具调用出现异常,请根据当前已有信息给用户一个合理的回复。

错误情况:
{error_summary}

请告知用户:
1. 系统暂时无法获取所需数据
2. 根据对话历史,给出基于已知信息的建议或替代方案
3. 语气友好专业,不要过分道歉"""

                            # 将兜底提示加入历史
                            shared_history.append({
                                "role": "user",
                                "content": fallback_prompt
                            })
                            
                            # 通知前端触发兜底机制
                            yield {
                                "type": "fallback_triggered",
                                "content": f"工具调用异常,正在生成替代回复...",
                                "error_count": consecutive_tool_failures
                            }
                            
                            # 强制进入下一轮,让模型基于兜底提示生成回复
                            # 重置计数器,避免再次触发
                            consecutive_tool_failures = 0
                            tool_error_history = []
                            continue

                    if exit_to_stream:
                        # 不再支持提前强制切流式，按原逻辑继续下一轮
                        pass
                    else:
                        # 工具后继续下一轮
                        continue

                # 3) 无工具：合并模式
                # 若先前已经流式输出过片段，则此处不再把所有片段再发一次，只发送结束标记；
                # 若此前尚未开始（无流式片段），则一次性发送最终文本再结束。
                final_text = "".join(buffered_chunks) if buffered_chunks else (content_preview or "")
                if combined_response_started:
                    # 已经开始过，避免重复内容
                    yield {"type": "ai_response_end", "content": ""}
                else:
                    yield {"type": "ai_response_start", "content": "AI正在回复..."}
                    combined_response_started = True
                    if final_text:
                        try:
                            print(f"📤 [最终回复流] {final_text}")
                        except Exception:
                            pass
                        yield {"type": "ai_response_chunk", "content": final_text}
                    yield {"type": "ai_response_end", "content": ""}
                # 在结束后补发token用量（若可用）
                if last_usage:
                    try:
                        yield {"type": "token_usage", **last_usage}
                    except Exception:
                        pass
                return

            # 轮次耗尽：直接返回提示信息
            print(f"⚠️ 达到最大推理轮数({max_rounds})，直接返回提示信息")
            final_text = "已达到最大推理轮数，请缩小问题范围或稍后重试。"
            yield {"type": "ai_response_start", "content": "AI正在回复..."}
            yield {"type": "ai_response_chunk", "content": final_text}
            yield {"type": "ai_response_end", "content": final_text}
            return
        except Exception as e:
            import traceback
            print(f"❌ chat_stream 异常: {e}")
            print("📋 详细错误信息:")
            traceback.print_exc()
            yield {"type": "error", "content": f"处理请求时出错: {str(e)}"}

    def get_tools_info(self) -> Dict[str, Any]:
        """获取工具信息列表，按MCP服务器分组"""
        return self.tools_manager.get_tools_info()

    async def close(self):
        """关闭连接"""
        try:
            await self.tools_manager.close()
        except:
            pass
