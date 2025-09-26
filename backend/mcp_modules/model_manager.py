"""
模型档位管理模块
"""

import os
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv, find_dotenv


class ModelManager:
    """模型档位管理器"""
    
    def __init__(self):
        # 确保.env文件被正确加载
        try:
            env_path = find_dotenv()
            if env_path:
                load_dotenv(env_path, override=False)
                print(f"✅ ModelManager 成功加载 .env 文件: {env_path}")
            else:
                print("⚠️ ModelManager 未找到 .env 文件")
        except Exception as e:
            print(f"⚠️ ModelManager 加载 .env 文件失败: {e}")
        
        self.llm_profiles = self._load_llm_profiles_from_env()
        self.default_profile_id = os.getenv("LLM_DEFAULT", "default").strip() or "default"
        if self.default_profile_id not in self.llm_profiles:
            self.default_profile_id = "default"
        self._llm_cache: Dict[str, Dict[str, Any]] = {}
        
        # 数值配置，带默认
        try:
            self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
        except Exception:
            self.temperature = 0.2
        try:
            self.timeout = int(os.getenv("OPENAI_TIMEOUT", "60"))
        except Exception:
            self.timeout = 60
        
        # 基础模型配置
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        self.model_name = os.getenv("OPENAI_MODEL", os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")).strip()

    def _load_llm_profiles_from_env(self) -> Dict[str, Dict[str, Any]]:
        """从环境变量解析多模型档位配置。
        约定：
        - LLM_PROFILES=profile1,profile2
        - 每个档位变量：
          LLM_<ID>_LABEL、LLM_<ID>_API_KEY、LLM_<ID>_BASE_URL、LLM_<ID>_MODEL、
          （可选）LLM_<ID>_TEMPERATURE、LLM_<ID>_TIMEOUT、LLM_<ID>_SYSTEM_PROMPT
        - 同时提供一个向后兼容的 default 档位，来自 OPENAI_* 变量
        """
        profiles: Dict[str, Dict[str, Any]] = {}

        # default 档位（向后兼容现有 OPENAI_*）
        profiles["default"] = {
            "id": "default",
            "label": os.getenv("LLM_DEFAULT_LABEL", "Default"),
            "api_key": os.getenv("OPENAI_API_KEY", "").strip(),
            "base_url": os.getenv("OPENAI_BASE_URL", "").strip(),
            "model": os.getenv("OPENAI_MODEL", os.getenv("OPENAI_MODEL_NAME", "deepseek-chat")).strip(),
            "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.2")),
            "timeout": int(os.getenv("OPENAI_TIMEOUT", "60")),
            "system_prompt": os.getenv("LLM_DEFAULT_SYSTEM_PROMPT", "").strip(),
            # 默认档位类型为普通模型
            "kind": os.getenv("LLM_DEFAULT_KIND", "model").strip() or "model",
            # 兼容 agent 扩展字段（默认档位正常为空）
            "agent_file": os.getenv("LLM_DEFAULT_AGENT_FILE", "").strip(),
            "backing_profile": os.getenv("LLM_DEFAULT_BACKING_PROFILE", "").strip(),
        }

        ids_raw = os.getenv("LLM_PROFILES", "").strip()
        if ids_raw:
            for pid in [x.strip() for x in ids_raw.split(",") if x.strip()]:
                pid_upper = pid.upper()
                kind = (os.getenv(f"LLM_{pid_upper}_KIND", "model").strip() or "model").lower()

                api_key = os.getenv(f"LLM_{pid_upper}_API_KEY", "").strip()
                model_name = os.getenv(f"LLM_{pid_upper}_MODEL", "").strip()
                base_url = os.getenv(f"LLM_{pid_upper}_BASE_URL", "").strip()
                label = os.getenv(f"LLM_{pid_upper}_LABEL", pid)
                try:
                    temperature = float(os.getenv(f"LLM_{pid_upper}_TEMPERATURE", os.getenv("OPENAI_TEMPERATURE", "0.2")))
                except Exception:
                    temperature = 0.2
                try:
                    timeout = int(os.getenv(f"LLM_{pid_upper}_TIMEOUT", os.getenv("OPENAI_TIMEOUT", "60")))
                except Exception:
                    timeout = 60
                system_prompt = os.getenv(f"LLM_{pid_upper}_SYSTEM_PROMPT", "").strip()
                agent_file = os.getenv(f"LLM_{pid_upper}_AGENT_FILE", "").strip()
                backing_profile = os.getenv(f"LLM_{pid_upper}_BACKING_PROFILE", "").strip()

                # 非 agent 档位：没有 api_key 或 model 则跳过
                if kind != "agent" and (not api_key or not model_name):
                    continue

                profiles[pid] = {
                    "id": pid,
                    "label": label,
                    "api_key": api_key,
                    "base_url": base_url,
                    "model": model_name,
                    "temperature": temperature,
                    "timeout": timeout,
                    "system_prompt": system_prompt,
                    "kind": kind,
                    "agent_file": agent_file,
                    "backing_profile": backing_profile,
                }

        return profiles

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
            kind = cfg.get("kind", "model")
            model_for_display = cfg.get("model", "")
            if kind == "agent":
                backing_id = cfg.get("backing_profile")
                if backing_id and backing_id in profiles:
                    model_for_display = profiles[backing_id].get("model", model_for_display)
            models.append({
                "id": pid,
                "label": cfg.get("label", pid),
                "model": model_for_display,
                "is_default": pid == effective_default,
                "type": kind,
                "is_agent": (kind == "agent"),
            })

        # 极端兜底：如果最终一个都没有（理论不会发生），返回空列表与默认ID
        return {"models": models, "default": effective_default}

    def get_current_model_key(self, session_contexts: Dict[str, Dict[str, Any]], session_id: Optional[str] = None) -> str:
        """获取当前会话使用的模型标识（用于记录多模态支持情况）"""
        try:
            profile_id = None
            if session_id and session_contexts.get(session_id):
                profile_id = session_contexts[session_id].get("model") or session_contexts[session_id].get("llm_profile")
            if not profile_id:
                profile_id = self.default_profile_id
            cfg = self.llm_profiles.get(profile_id, {})
            model_name = cfg.get("model", "")
            base_url = cfg.get("base_url", "")
            return f"{model_name}@{base_url}"
        except Exception:
            return "unknown"

    def get_system_prompt(self, session_contexts: Dict[str, Dict[str, Any]], session_id: Optional[str] = None) -> str:
        """获取当前会话使用的模型的系统提示词"""
        try:
            profile_id = None
            if session_id and session_contexts.get(session_id):
                profile_id = session_contexts[session_id].get("model") or session_contexts[session_id].get("llm_profile")
            if not profile_id:
                profile_id = self.default_profile_id
            
            print(f"🔍 获取系统提示词: session_id={session_id}, profile_id={profile_id}")
            
            cfg = self.llm_profiles.get(profile_id, {})
            print(f"🔍 找到配置: {bool(cfg)}")
            
            # 优先从环境变量读取系统提示词
            system_prompt = cfg.get("system_prompt", "")
            print(f"🔍 环境变量提示词长度: {len(system_prompt)}")
            
            # 如果环境变量中没有，尝试从对应的文件中读取
            if not system_prompt:
                system_prompt = self._load_prompt_from_file(profile_id)
                print(f"🔍 文件提示词长度: {len(system_prompt)}")
            
            # 如果当前模型没有配置系统提示词，返回空字符串，由调用方使用默认逻辑
            return system_prompt
        except Exception as e:
            print(f"❌ 获取系统提示词异常: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _load_prompt_from_file(self, profile_id: str) -> str:
        """从文件中加载系统提示词"""
        try:
            import importlib.util
            import os
            
            # 构建文件路径
            prompt_file_path = os.path.join(
                os.path.dirname(__file__), 
                "..", 
                "prompts", 
                f"LLM_{profile_id}_SYSTEM_PROMPT.py"
            )
            
            if not os.path.exists(prompt_file_path):
                return ""
            
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(
                f"prompt_{profile_id}", prompt_file_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 获取 SYSTEM_PROMPT 变量
            return getattr(module, "SYSTEM_PROMPT", "")
        
        except Exception as e:
            print(f"⚠️ 从文件加载提示词失败 ({profile_id}): {e}")
            return ""

    def get_or_create_llm_instances(self, profile_id: str, tools: list) -> Dict[str, Any]:
        """根据档位获取/创建对应的 LLM 实例集合：llm、llm_nontool、llm_tools。"""
        pid = profile_id or self.default_profile_id
        if pid not in self.llm_profiles:
            pid = self.default_profile_id

        if pid in self._llm_cache:
            return self._llm_cache[pid]

        cfg = self.llm_profiles[pid]

        # 临时切换环境变量，构造实例
        prev_key = os.getenv("OPENAI_API_KEY")
        prev_base = os.getenv("OPENAI_BASE_URL")
        try:
            if cfg.get("api_key"):
                os.environ["OPENAI_API_KEY"] = cfg["api_key"]
            if cfg.get("base_url"):
                os.environ["OPENAI_BASE_URL"] = cfg["base_url"]

            base_llm = ChatOpenAI(
                model=cfg.get("model", self.model_name),
                temperature=cfg.get("temperature", self.temperature),
                timeout=cfg.get("timeout", self.timeout),
                max_retries=3,
            )
            llm_nontool = ChatOpenAI(
                model=cfg.get("model", self.model_name),
                temperature=cfg.get("temperature", self.temperature),
                timeout=cfg.get("timeout", self.timeout),
                max_retries=3,
            )
            llm_tools = base_llm.bind_tools(tools)
        finally:
            # 还原环境，避免影响其他逻辑
            if prev_key is not None:
                os.environ["OPENAI_API_KEY"] = prev_key
            if prev_base is not None:
                os.environ["OPENAI_BASE_URL"] = prev_base

        bundle = {"llm": base_llm, "llm_nontool": llm_nontool, "llm_tools": llm_tools}
        self._llm_cache[pid] = bundle
        return bundle
