"""
量化意图检测模块：
- 提供基于关键词的快速判断 _detect_quant_intent
- 提供基于 Oversee 判别LLM（GLM-4.5-flash）的严格判断 is_quant_by_oversee

注意：判别LLM仅接收“本次用户文本”，不携带上下文
"""

import os
from typing import Optional

from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage


def _is_truthy(val: str) -> bool:
    try:
        return str(val).strip().lower() in {"1", "true", "yes", "on", "y"}
    except Exception:
        return False


def detect_quant_intent_by_keywords(raw_text: str) -> bool:
    """已弃用：保留空实现以兼容旧引用，不再使用关键词回退。"""
    return False


def _get_oversee_config() -> dict:
    try:
        # 尝试加载 .env（不覆盖系统变量）
        try:
            load_dotenv(find_dotenv(), override=False)
        except Exception:
            pass
        enabled = _is_truthy(os.getenv("OVERSEE_LLM_ENABLED", "true"))
        api_key = os.getenv("Oversee_LLM_APIKEY") or os.getenv("OVERSEE_LLM_APIKEY") or os.getenv("OVERSEE_LLM_API_KEY")
        base_url = os.getenv("OVERSEE_LLM_BASE_URL", "").strip()
        model = os.getenv("OVERSEE_LLM_MODEL", "glm-4.5-flash").strip()
        temperature = float(os.getenv("OVERSEE_LLM_TEMPERATURE", "0.1"))
        timeout = int(os.getenv("OVERSEE_LLM_TIMEOUT", "10"))
        cfg = {
            "enabled": enabled,
            "api_key": (api_key or "").strip(),
            "base_url": base_url,
            "model": model,
            "temperature": temperature,
            "timeout": timeout,
        }
        # DEBUG: 打印配置概览（不泄露完整Key）
        try:
            if _is_truthy(os.getenv("OVERSEE_LLM_DEBUG", "false")):
                masked = "" if not cfg["api_key"] else ("***" + cfg["api_key"][-4:])
                print(
                    f"🧭 Oversee配置: enabled={cfg['enabled']}, model={cfg['model']}, base_url={'set' if cfg['base_url'] else 'default'}, "
                    f"temperature={cfg['temperature']}, timeout={cfg['timeout']}s, api_key={masked}"
                )
        except Exception:
            pass
        return cfg
    except Exception:
        return {
            "enabled": False,
            "api_key": "",
            "base_url": "",
            "model": "",
            "temperature": 0.1,
            "timeout": 10,
        }


async def is_quant_by_oversee(raw_text: str) -> Optional[bool]:
    """使用判别LLM判断是否量化需求。
    返回 True/False；若不可用或失败，返回 None（未知）。
    """
    try:
        if not isinstance(raw_text, str) or not raw_text.strip():
            return None
        cfg = _get_oversee_config()
        if not cfg.get("enabled") or not cfg.get("api_key") or not cfg.get("model"):
            return None

        prev_key = os.getenv("OPENAI_API_KEY")
        prev_base = os.getenv("OPENAI_BASE_URL")
        try:
            os.environ["OPENAI_API_KEY"] = cfg["api_key"]
            if cfg.get("base_url"):
                os.environ["OPENAI_BASE_URL"] = cfg["base_url"]

            clf = ChatOpenAI(
                model=cfg["model"],
                temperature=cfg["temperature"],
                timeout=cfg["timeout"],
                max_retries=1,
            )
            system_prompt = os.getenv("OVERSEE_LLM_SYSTEM_PROMPT", "").strip() or (
                "你是一个严格的路由判别器，只能回答‘是’或‘否’。\n"
                "判定目标：用户是否在请求‘量化交易/回测/因子/策略代码’（尤其恒生 PTrader/HS PTrader 平台）。\n"
                "满足任一条件即回答‘是’：\n"
                "- 明确提及量化/回测/因子/择时/自动交易/交易机器人/买入/卖出/止损/止盈/仓位/信号\n"
                "- 明确提及恒生/Ptrader/HS PTrader 或其API/生命周期函数（initialize/handle_data/run_daily/run_interval/on_order_response/on_trade_response/after_trading_end/set_universe/set_benchmark/set_commission/order/order_target）\n"
                "- 模糊提及‘赚钱的代码/会赚钱的代码’且语境是股票/交易相关\n"
                "以下情况回答‘否’：仅是一般性财经/行业/公司分析，没有要求生成量化策略代码或回测脚本。\n"
            )
            msgs = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=raw_text.strip()),
            ]
            resp = await clf.ainvoke(msgs)
            content = (getattr(resp, "content", None) or "").strip()
            normalized = content.lower()
            decision: Optional[bool] = None
            if normalized:
                if normalized.startswith("是") or normalized in {"yes", "y", "true", "是"}:
                    decision = True
                elif normalized.startswith("否") or normalized in {"no", "n", "false", "否"}:
                    decision = False
            # 调试日志
            try:
                if _is_truthy(os.getenv("OVERSEE_LLM_DEBUG", "false")):
                    print(f"🧪 Oversee判别LLM: raw='{content}' => decision={decision}")
            except Exception:
                pass
            return decision
        finally:
            if prev_key is not None:
                os.environ["OPENAI_API_KEY"] = prev_key
            if prev_base is not None:
                os.environ["OPENAI_BASE_URL"] = prev_base
    except Exception:
        return None


