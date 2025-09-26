"""
AgentOrchestrator: 最小可用版多智能体编排器
实现固定三角色：Planner -> Researcher -> Writer
每个步骤支持工具函数调用（非流式，迭代至无tool_calls或达到上限）。

注意：首版尽量复用现有工具机制，事件协议沿用 tool_* 与 ai_response_*。
"""

from typing import Any, Dict, List, AsyncGenerator, Optional
import asyncio

try:
    import yaml  # type: ignore
except Exception:  # 允许未安装时由上层提示
    yaml = None


class AgentOrchestrator:
    def __init__(
        self,
        tools_manager: Any,
        message_processor: Any,
        model_manager: Any,
        get_llm_bundle_fn,
        current_session_id_ctx,
    ) -> None:
        self.tools_manager = tools_manager
        self.message_processor = message_processor
        self.model_manager = model_manager
        self._get_llm_bundle = get_llm_bundle_fn
        self._current_session_id_ctx = current_session_id_ctx

    def _load_spec(self, agent_file: str) -> Dict[str, Any]:
        if not agent_file:
            return self._default_spec()
        try:
            if yaml is None:
                return self._default_spec()
            with open(agent_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data
        except Exception:
            return self._default_spec()

    def _default_spec(self) -> Dict[str, Any]:
        return {
            "roles": [
                {"id": "planner", "system_prompt": "你是任务规划师，负责拆解用户问题，给出明确的子任务步骤与所需数据。"},
                {"id": "researcher", "system_prompt": "你是研究员，负责检索并调用可用工具完成事实性数据收集与要点总结。"},
                {"id": "writer", "system_prompt": "你是撰写者，整合规划与证据，给出结构化、清晰、可执行的最终回答。"},
            ],
            "max_rounds": 1,
            "tools_allowlist": [],
        }

    async def chat_stream(
        self,
        user_input: Any,
        history: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        agent_cfg: Optional[Dict[str, Any]] = None,
        session_contexts: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            # 选择底层模型档位
            backing_profile = ""
            agent_file = ""
            if agent_cfg:
                backing_profile = (agent_cfg.get("backing_profile") or "").strip()
                agent_file = (agent_cfg.get("agent_file") or "").strip()

            spec = self._load_spec(agent_file)
            roles = spec.get("roles") or []
            max_rounds = int(spec.get("max_rounds", 1) or 1)
            tools_allowlist = spec.get("tools_allowlist") or []

            # 构建共享历史（精简工具结果，保留问答主干）
            shared_history = self.message_processor.build_shared_history(
                history, user_input, False, concise=True
            )

            # 选择默认 LLM 实例（可被角色级覆盖）
            default_llm_bundle = self._get_llm_bundle(backing_profile)
            default_llm_tools = default_llm_bundle.get("llm_tools")

            # 开始总回复（改为逐字流：各角色在生成时直接输出片段）
            yield {"type": "ai_response_start", "content": "AI正在回复..."}

            # 顺序执行角色
            role_outputs: Dict[str, str] = {}
            any_streamed = False
            for role in roles:
                role_id = role.get("id") or "role"
                sys_prompt = role.get("system_prompt") or ""

                # 选择该角色使用的模型档位（可覆盖默认）
                role_profile = (role.get("model_profile") or "").strip()
                role_llm_tools = default_llm_tools
                if role_profile:
                    try:
                        role_bundle = self._get_llm_bundle(role_profile)
                        role_llm_tools = role_bundle.get("llm_tools") or default_llm_tools
                    except Exception:
                        role_llm_tools = default_llm_tools

                # 为当前角色构建消息（系统提示 + 共享历史）
                messages: List[Dict[str, Any]] = (
                    [{"role": "system", "content": sys_prompt}] + shared_history
                )

                # 迭代执行：流式判定 + 工具调用 + 写回
                tool_iterations = 0
                max_tool_iterations = 6
                role_last_content = ""
                role_prefix_sent = False
                while tool_iterations < max_tool_iterations:
                    tool_iterations += 1

                    # 流式调用当前角色
                    tool_calls = None
                    content_preview = ""
                    try:
                        import logging
                        mcp_logger = logging.getLogger('mcp')
                        original_level = mcp_logger.level
                        mcp_logger.setLevel(logging.CRITICAL)
                        try:
                            buffered_chunks: List[str] = []
                            async for event in role_llm_tools.astream_events(messages, version="v1"):
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
                                        if not role_prefix_sent:
                                            yield {"type": "ai_response_chunk", "content": f"[{role_id}] " + content_piece}
                                            role_prefix_sent = True
                                        else:
                                            yield {"type": "ai_response_chunk", "content": content_piece}
                                        any_streamed = True
                                        buffered_chunks.append(content_piece)
                                elif ev == "on_chat_model_end":
                                    data = event.get("data", {})
                                    output = data.get("output")
                                    try:
                                        tool_calls = getattr(output, 'tool_calls', None)
                                    except Exception:
                                        tool_calls = None
                                    try:
                                        content_preview = getattr(output, 'content', None) or "".join(buffered_chunks)
                                    except Exception:
                                        content_preview = "".join(buffered_chunks)
                        finally:
                            mcp_logger.setLevel(original_level)
                    except Exception as e:
                        yield {"type": "ai_response_chunk", "content": f"\n⚠️ {role_id} 执行失败: {e}\n"}
                        break

                    # 无工具：写回并结束该角色
                    if not tool_calls:
                        role_last_content = content_preview
                        messages.append({"role": "assistant", "content": content_preview})
                        shared_history.append({"role": "assistant", "content": f"[{role_id}] {content_preview}"})
                        # 角色结束时追加换行，便于前端可读性
                        if role_prefix_sent:
                            try:
                                yield {"type": "ai_response_chunk", "content": "\n"}
                            except Exception:
                                pass
                        break

                    # 有工具：宣布计划并逐个执行
                    yield {"type": "tool_plan", "content": f"{role_id} 将调用 {len(tool_calls)} 个工具", "tool_count": len(tool_calls)}

                    for i, tool_call in enumerate(tool_calls, 1):
                        # 解析工具
                        if isinstance(tool_call, dict):
                            tool_id = tool_call.get("id") or f"call_{i}"
                            fn = tool_call.get("function") or {}
                            tool_name = fn.get("name") or tool_call.get("name") or ""
                            tool_args_raw = fn.get("arguments") or tool_call.get("args") or {}
                        else:
                            tool_id = getattr(tool_call, "id", None) or f"call_{i}"
                            tool_name = getattr(tool_call, "name", "") or ""
                            tool_args_raw = getattr(tool_call, "args", {}) or {}

                        # 白名单过滤
                        if tools_allowlist and tool_name and tool_name not in tools_allowlist:
                            yield {"type": "tool_error", "tool_id": tool_id, "error": f"工具 '{tool_name}' 不在允许列表中", "by_role": role_id}
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_id,
                                "name": tool_name,
                                "content": f"错误: 工具 '{tool_name}' 未被允许",
                            })
                            continue

                        # 解析参数
                        if isinstance(tool_args_raw, str):
                            import json
                            try:
                                parsed_args = json.loads(tool_args_raw) if tool_args_raw else {}
                            except Exception:
                                parsed_args = {"$raw": tool_args_raw}
                        elif isinstance(tool_args_raw, dict):
                            parsed_args = tool_args_raw
                        else:
                            parsed_args = {"$raw": str(tool_args_raw)}

                        yield {"type": "tool_start", "tool_id": tool_id, "tool_name": tool_name, "tool_args": parsed_args, "by_role": role_id}

                        # 匹配工具并执行
                        target_tool = None
                        for tool in self.tools_manager.tools:
                            if tool.name == tool_name:
                                target_tool = tool
                                break
                        if target_tool is None:
                            error_msg = f"工具 '{tool_name}' 未找到"
                            yield {"type": "tool_error", "tool_id": tool_id, "error": error_msg, "by_role": role_id}
                            tool_result = f"错误: {error_msg}"
                        else:
                            try:
                                tool_result = await target_tool.ainvoke(parsed_args)
                                yield {"type": "tool_end", "tool_id": tool_id, "tool_name": tool_name, "result": str(tool_result), "by_role": role_id}
                            except Exception as e:
                                error_msg = f"工具执行出错: {e}"
                                yield {"type": "tool_error", "tool_id": tool_id, "error": error_msg, "by_role": role_id}
                                tool_result = f"错误: {error_msg}"

                        # 写回 tool 消息
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "name": tool_name,
                            "content": str(tool_result),
                        })

                # 记录最后内容（便于兜底）
                role_outputs[role_id] = role_last_content

            # 若全程未产生流式片段，则兜底输出最终文本；否则避免重复
            final_text = role_outputs.get("writer") or (list(role_outputs.values())[-1] if role_outputs else "")
            if not any_streamed and final_text:
                yield {"type": "ai_response_chunk", "content": final_text}
            yield {"type": "ai_response_end", "content": ""}
            return

        except Exception as e:
            yield {"type": "error", "content": f"Agent 执行出错: {e}"}


