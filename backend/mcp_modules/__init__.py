"""
MCP Agent 模块化结构
"""

from .config import MCPConfig
from .multimodal import MultimodalProcessor
from .model_manager import ModelManager
from .message_processor import MessageProcessor

__all__ = [
    'MCPConfig',
    'MultimodalProcessor', 
    'ModelManager',
    'MessageProcessor'
]
