from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import os
import pandas as pd

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool


def _parse_date(s: str) -> datetime:
    s = (s or "").strip()
    # 支持 2024-01-31 或 20240131
    if not s:
        raise ValueError("date is empty")
    if "-" in s:
        return datetime.strptime(s, "%Y-%m-%d")
    return datetime.strptime(s, "%Y%m%d")


def _fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _ensure_ts_token() -> None:
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 TUSHARE_TOKEN 环境变量")
    import tushare as ts
    ts.set_token(token)


def _safe_min_max(series: pd.Series) -> Tuple[Optional[float], Optional[float]]:
    if series is None or series.empty:
        return None, None
    return float(series.min()), float(series.max())


def _first(series: pd.Series) -> Optional[float]:
    if series is None or series.empty:
        return None
    return float(series.iloc[0])


def _last(series: pd.Series) -> Optional[float]:
    if series is None or series.empty:
        return None
    return float(series.iloc[-1])


def _normalize_index_code(code: str) -> str:
    """标准化指数代码为 6位数字.大写交易所，如 399959.SZ / 000001.SH。
    支持输入形式："399959.SZ"、"399959.sz"、"sz399959"、"SZ399959"。
    其他格式则原样返回。
    """
    s = (code or "").strip()
    if not s:
        return s
    # 形如 399959.SZ / 399959.sz
    if "." in s and len(s.split(".")) == 2:
        left, right = s.split(".")
        return f"{left}.{right.upper()}"
    # 形如 sz399959 / SZ399959
    low = s.lower()
    if low.startswith("sz") or low.startswith("sh"):
        market = s[:2].upper()
        digits = s[2:]
        return f"{digits}.{market}"
    return s


class IndexConstituentsResult(BaseModel):
    ts_code: str
    weight: float


class FetchIndexAndConstituentsArgs(BaseModel):
    index_code: str = Field(..., description="指数代码，如 000001.SH")
    start_date: str = Field(..., description="开始日期，YYYYMMDD 或 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期，YYYYMMDD 或 YYYY-MM-DD")


def _get_index_daily(index_code: str, start: str, end: str) -> pd.DataFrame:
    """获取指数区间日线。使用 pro_bar asset='I' 以便统一行情字段。
    文档参考: https://tushare.pro/document/2?doc_id=109
    """
    import tushare as ts
    pro = ts.pro_api()
    # pro_bar 对 index 取值: asset='I'
    norm_code = _normalize_index_code(index_code)
    df = ts.pro_bar(ts_code=norm_code, asset='I', start_date=start, end_date=end)
    if df is None or df.empty:
        return pd.DataFrame()
    # 按交易日期升序
    return df.sort_values("trade_date").reset_index(drop=True)


def _get_index_weights(index_code: str, trade_date: str) -> List[IndexConstituentsResult]:
    """获取指数权重（以 end_date 为基准；若当天无数据则逐日向前回退直至找到为止）。
    文档参考: https://tushare.pro/document/2?doc_id=96
    """
    import tushare as ts
    pro = ts.pro_api()
    norm_code = _normalize_index_code(index_code)

    def _fetch(date_str: str) -> pd.DataFrame:
        try:
            return pro.index_weight(index_code=norm_code, trade_date=date_str)
        except Exception:
            return pd.DataFrame()

    # 逐日向前回退，最多回退 120 天（可按需调整）
    try:
        dt = datetime.strptime(trade_date, "%Y%m%d")
    except Exception:
        dt = pd.Timestamp(trade_date).to_pydatetime()

    df = pd.DataFrame()
    for _ in range(0, 120):
        d = dt.strftime("%Y%m%d")
        df = _fetch(d)
        if df is not None and not df.empty:
            break
        dt = dt - pd.Timedelta(days=1)

    if df is None or df.empty:
        return []

    # 仅保留必要字段
    out: List[IndexConstituentsResult] = []
    for _, row in df.iterrows():
        try:
            code = str(row.get("con_code") or row.get("ts_code") or "").strip()
            weight = float(row.get("weight") or 0.0)
            if code:
                out.append(IndexConstituentsResult(ts_code=code, weight=weight))
        except Exception:
            continue
    return out


def _get_stock_daily(ts_code: str, start: str, end: str) -> pd.DataFrame:
    import tushare as ts
    # 个股需确保代码为标准大写交易所后缀
    norm_code = _normalize_index_code(ts_code)
    df = ts.pro_bar(ts_code=norm_code, start_date=start, end_date=end, adj=None)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.sort_values("trade_date").reset_index(drop=True)


def _calc_return(open_price: Optional[float], close_price: Optional[float]) -> Optional[float]:
    if open_price is None or close_price is None or open_price == 0:
        return None
    return float((close_price - open_price) / open_price)


def _extract_price_summary(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    if df is None or df.empty:
        return {
            "open_at_start": None,
            "low_min": None,
            "low_min_date": None,
            "high_max": None,
            "high_max_date": None,
            "close_at_end": None,
        }
    open_at_start = _first(df["open"]) if "open" in df.columns else None
    low_min, high_max = None, None
    low_min_date, high_max_date = None, None
    if "low" in df.columns:
        low_min = float(df["low"].min())
        try:
            low_idx = df["low"].idxmin()
            low_min_date = str(df.loc[low_idx, "trade_date"]) if "trade_date" in df.columns else None
        except Exception:
            low_min_date = None
    if "high" in df.columns:
        high_max = float(df["high"].max())
        try:
            high_idx = df["high"].idxmax()
            high_max_date = str(df.loc[high_idx, "trade_date"]) if "trade_date" in df.columns else None
        except Exception:
            high_max_date = None
    close_at_end = _last(df["close"]) if "close" in df.columns else None
    return {
        "open_at_start": open_at_start,
        "low_min": low_min,
        "low_min_date": low_min_date,
        "high_max": high_max,
        "high_max_date": high_max_date,
        "close_at_end": close_at_end,
    }


def _build_tool_result(index_code: str, start: str, end: str,
                       index_df: pd.DataFrame,
                       constituents: List[IndexConstituentsResult],
                       stock_summaries: Dict[str, Dict[str, Optional[float]]]) -> Dict[str, Any]:
    index_summary = _extract_price_summary(index_df)
    index_return = _calc_return(index_summary.get("open_at_start"), index_summary.get("close_at_end"))
    return {
        "index": {
            "code": _normalize_index_code(index_code),
            "start_date": start,
            "end_date": end,
            "prices": index_summary,
            "return_ratio": index_return,
        },
        "constituents": [
            {
                "ts_code": c.ts_code,
                "weight": c.weight,
                "prices": stock_summaries.get(c.ts_code, {
                    "open_at_start": None, "low_min": None, "high_max": None, "close_at_end": None
                }),
                "return_ratio": _calc_return(
                    stock_summaries.get(c.ts_code, {}).get("open_at_start"),
                    stock_summaries.get(c.ts_code, {}).get("close_at_end")
                )
            }
            for c in constituents
        ]
    }


def fetch_index_and_constituents_impl(index_code: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """聚合工具：
    - 输入：指数代码、start_date、end_date
    - 步骤：
      1) 获取指数区间日线
      2) 以 end_date 作为权重日期，获取指数成分权重
      3) 对每个成分股获取区间日线，输出开盘(起点)、区间最低、区间最高、收盘(终点)、以及区间涨跌幅
    - 输出：包含指数与各成分股的价格摘要与涨跌幅
    文档参考：
      - 指数/通用行情 pro_bar: https://tushare.pro/document/2?doc_id=109
      - 指数成分与权重: https://tushare.pro/document/2?doc_id=96
    """
    _ensure_ts_token()
    # 规范日期
    dt_start = _parse_date(start_date)
    dt_end = _parse_date(end_date)
    if dt_start > dt_end:
        raise ValueError("start_date 不能大于 end_date")
    start = _fmt_date(dt_start)
    end = _fmt_date(dt_end)

    # 1) 指数行情
    index_df = _get_index_daily(index_code=index_code, start=start, end=end)

    # 2) 权重(以 end_date 为日期)
    constituents = _get_index_weights(index_code=index_code, trade_date=end)

    # 3) 成分股行情摘要
    stock_summaries: Dict[str, Dict[str, Optional[float]]] = {}
    for c in constituents:
        try:
            sdf = _get_stock_daily(ts_code=c.ts_code, start=start, end=end)
            stock_summaries[c.ts_code] = _extract_price_summary(sdf)
        except Exception:
            stock_summaries[c.ts_code] = {
                "open_at_start": None, "low_min": None, "high_max": None, "close_at_end": None
            }

    return _build_tool_result(index_code=index_code, start=start, end=end,
                               index_df=index_df,
                               constituents=constituents,
                               stock_summaries=stock_summaries)


def create_tushare_tools() -> List[StructuredTool]:
    """导出为 LangChain StructuredTool 列表。"""
    return [
        StructuredTool.from_function(
            func=fetch_index_and_constituents_impl,
            name="tushare_index_constituents_summary",
            description=(
                "聚合 TuShare（仅支持中证指数公司 CSI 指数）：给定指数代码与区间(start_date,end_date)，"
                "获取指数行情与 end_date 对应的成分权重，并对每个成分股输出区间内"
                "起始开盘价、区间最低(含日期)、区间最高(含日期)、结束收盘价与区间涨跌幅。"
                "日期格式支持 YYYYMMDD 或 YYYY-MM-DD。"
                "注意：仅接受中证指数公司（CSI）发布的指数代码，例如 000300.SH、000905.SH 等。"
            ),
            args_schema=FetchIndexAndConstituentsArgs,
        )
    ]


