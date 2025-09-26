"""
MCP工具获取和管理模块
负责从MCP服务器获取工具、注入本地工具、工具名规范化等功能
"""

import os
import re
import asyncio
import logging
from typing import Dict, List, Any, Optional, Set
import aiohttp
import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient

from basictool import create_basic_tools


class MCPToolsManager:
    """MCP工具管理器"""
    
    def __init__(self):
        self.tools: List[Any] = []
        self.tools_by_server: Dict[str, List[Any]] = {}
        self.server_configs: Dict[str, Dict[str, Any]] = {}
        self.mcp_client: Optional[MultiServerMCPClient] = None
        self._used_tool_names: Set[str] = set()
        
    async def initialize_mcp_tools(self, server_configs: Dict[str, Dict[str, Any]], 
                                 db_config: Dict[str, Any], 
                                 session_contexts: Dict[str, Dict[str, Any]],
                                 current_session_id_ctx,
                                 llm_nontool) -> bool:
        """初始化MCP工具
        
        Args:
            server_configs: MCP服务器配置
            db_config: 数据库配置 (包含 host, user, password, name, port)
            session_contexts: 会话上下文
            current_session_id_ctx: 当前会话ID上下文变量
            llm_nontool: 无工具的LLM实例
            
        Returns:
            bool: 初始化是否成功
        """
        try:
            self.server_configs = server_configs
            # 保存会话上下文与上下文变量，供HTTP请求时动态注入用户头
            self._session_contexts = session_contexts or {}
            self._current_session_id_ctx = current_session_id_ctx
            
            # 允许没有外部MCP服务器，仅使用本地工具
            if not self.server_configs:
                print("⚠️ 没有配置外部MCP服务器，仅使用本地医疗数据工具")
                self.server_configs = {}

            print("🔗 正在连接MCP服务器...")
            
            # 先测试服务器连接
            await self._test_server_connections()
            
            # 创建MCP客户端
            if self.server_configs:
                self.mcp_client = await self._create_mcp_client()
                
                # 获取外部工具
                await self._fetch_external_tools()
            
            # 注入本地工具已移除 (medicaltool已删除)
            
            # 注入基础工具
            await self._inject_basic_tools()
            
            print(f"✅ 成功连接，获取到 {len(self.tools)} 个工具")
            print(f"📊 服务器分组情况: {dict((name, len(tools)) for name, tools in self.tools_by_server.items())}")
            
            return True
            
        except Exception as e:
            import traceback
            print(f"❌ MCP工具初始化失败: {e}")
            print(f"📋 详细错误信息:")
            traceback.print_exc()
            
            # 尝试清理可能的连接
            if hasattr(self, 'mcp_client') and self.mcp_client:
                try:
                    await self.mcp_client.close()
                except:
                    pass
            return False
    
    async def _test_server_connections(self):
        """测试服务器连接"""
        for server_name, server_config in self.server_configs.items():
            try:
                url = server_config.get('url')
                if not url:
                    print(f"⚠️ 服务器 {server_name} 缺少 url 配置，跳过连接测试")
                    continue
                print(f"🧪 测试连接到 {server_name}: {url}")
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        print(f"✅ {server_name} 连接测试成功 (状态: {response.status})")
            except Exception as test_e:
                print(f"⚠️ {server_name} 连接测试失败: {test_e}")
    
    async def _create_mcp_client(self) -> MultiServerMCPClient:
        """创建MCP客户端"""
        # 创建MCP客户端 - 强制清除缓存并禁用HTTP/2
        async def _on_request(request: httpx.Request):
            try:
                ctx = getattr(self, "_session_contexts", {}) or {}
                ctx_var = getattr(self, "_current_session_id_ctx", None)
                current_sid = None
                try:
                    if ctx_var is not None:
                        current_sid = ctx_var.get(None)
                except Exception:
                    current_sid = None
                token = None
                if current_sid and ctx.get(current_sid):
                    token = (ctx[current_sid].get("tushare_token") or "").strip()
                if token:
                    # 仅当存在用户自定义token时覆盖请求头
                    request.headers["X-Tushare-Token"] = token
            except Exception:
                # 注入失败不应阻断请求
                pass

        def http_client_factory(headers=None, timeout=None, auth=None):
            return httpx.AsyncClient(
                http2=False,  # 禁用HTTP/2
                headers=headers,
                timeout=timeout,
                auth=auth,
                event_hooks={"request": [_on_request]}
            )

        # 更新服务器配置以使用自定义的httpx客户端工厂
        for server_name in self.server_configs:
            # 避免污染原配置对象，复制后添加工厂
            server_cfg = dict(self.server_configs[server_name])
            server_cfg['httpx_client_factory'] = http_client_factory
            self.server_configs[server_name] = server_cfg

        return MultiServerMCPClient(self.server_configs)
    
    async def _fetch_external_tools(self):
        """从外部MCP服务器获取工具"""
        # 改为串行获取工具，避免并发问题
        print("🔧 正在逐个获取服务器工具...")
        for server_name in self.server_configs.keys():
            try:
                print(f"─── 正在从服务器 '{server_name}' 获取工具 ───")
                # 抑制MCP客户端的SSE解析错误日志（这些错误不影响功能）
                mcp_logger = logging.getLogger('mcp')
                original_level = mcp_logger.level
                mcp_logger.setLevel(logging.CRITICAL)
                
                try:
                    server_tools = await self.mcp_client.get_tools(server_name=server_name)
                finally:
                    mcp_logger.setLevel(original_level)
                    
                # 对工具名做合法化与去重
                sanitized_tools = []
                for tool in server_tools:
                    try:
                        original_name = getattr(tool, 'name', '') or ''
                        sanitized = self._sanitize_and_uniq_tool_name(original_name)
                        if sanitized != original_name:
                            print(f"🧹 规范化工具名: '{original_name}' -> '{sanitized}'")
                            try:
                                tool.name = sanitized  # 覆盖名称，供后续绑定与匹配
                            except Exception:
                                pass
                        sanitized_tools.append(tool)
                    except Exception as _e:
                        print(f"⚠️ 工具名规范化失败，跳过: {getattr(tool,'name','<unknown>')} - {_e}")
                        sanitized_tools.append(tool)
                        
                self.tools.extend(sanitized_tools)
                self.tools_by_server[server_name] = sanitized_tools
                print(f"✅ 从 {server_name} 获取到 {len(server_tools)} 个工具")
            except Exception as e:
                print(f"❌ 从服务器 '{server_name}' 获取工具失败: {e}")
                self.tools_by_server[server_name] = []
    

    
    async def _inject_basic_tools(self):
        """注入基础工具"""
        try:
            basic_tools = create_basic_tools()
            for tool in basic_tools:
                self.tools.append(tool)
                self.tools_by_server.setdefault("__basic__", []).append(tool)
            print(f"🧰 已注入 {len(basic_tools)} 个基础工具")
        except Exception as e:
            print(f"⚠️ 注入基础工具失败: {e}")
    
    def _sanitize_and_uniq_tool_name(self, name: str) -> str:
        """将工具名规范为 ^[a-zA-Z0-9_-]+$，并避免重名冲突。"""
        if not isinstance(name, str):
            name = str(name or "")
        # 仅保留字母数字下划线和连字符，其余替换为下划线
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        if not sanitized:
            sanitized = "tool"
        base = sanitized
        # 确保唯一
        index = 1
        while sanitized in self._used_tool_names:
            index += 1
            sanitized = f"{base}_{index}"
        self._used_tool_names.add(sanitized)
        return sanitized
    
    def get_tools_info(self) -> Dict[str, Any]:
        """获取工具信息列表，按MCP服务器分组"""
        if not self.tools_by_server:
            return {"servers": {}, "total_tools": 0, "server_count": 0}
        
        servers_info = {}
        total_tools = 0
        
        # 按服务器分组构建工具信息
        for server_name, server_tools in self.tools_by_server.items():
            tools_info = []
            
            for tool in server_tools:
                tool_info = {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {},
                    "required": []
                }
                
                # 获取参数信息 - 优化版本
                try:
                    schema = None
                    
                    # 方法1: 尝试使用args_schema (LangChain工具常用)
                    if hasattr(tool, 'args_schema') and tool.args_schema:
                        if isinstance(tool.args_schema, dict):
                            schema = tool.args_schema
                        elif hasattr(tool.args_schema, 'model_json_schema'):
                            schema = tool.args_schema.model_json_schema()
                    
                    # 方法2: 如果没有args_schema，尝试tool_call_schema
                    if not schema and hasattr(tool, 'tool_call_schema') and tool.tool_call_schema:
                        schema = tool.tool_call_schema
                    
                    # 方法3: 最后尝试input_schema
                    if not schema and hasattr(tool, 'input_schema') and tool.input_schema:
                        if isinstance(tool.input_schema, dict):
                            schema = tool.input_schema
                        elif hasattr(tool.input_schema, 'model_json_schema'):
                            try:
                                schema = tool.input_schema.model_json_schema()
                            except:
                                pass
                    
                    # 解析schema
                    if schema and isinstance(schema, dict):
                        if 'properties' in schema:
                            tool_info["parameters"] = schema['properties']
                            tool_info["required"] = schema.get('required', [])
                        elif 'type' in schema and schema.get('type') == 'object' and 'properties' in schema:
                            tool_info["parameters"] = schema['properties']
                            tool_info["required"] = schema.get('required', [])
                
                except Exception as e:
                    # 如果出错，至少保留工具的基本信息
                    print(f"⚠️ 获取工具 '{tool.name}' 参数信息失败: {e}")
                
                tools_info.append(tool_info)
            
            # 添加服务器信息
            servers_info[server_name] = {
                "name": server_name,
                "tools": tools_info,
                "tool_count": len(tools_info)
            }
            
            total_tools += len(tools_info)
        
        return {
            "servers": servers_info,
            "total_tools": total_tools,
            "server_count": len(servers_info)
        }
    
    async def close(self):
        """关闭连接"""
        try:
            if self.mcp_client and hasattr(self.mcp_client, 'close'):
                await self.mcp_client.close()
        except:
            pass
