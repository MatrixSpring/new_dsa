# -*- coding: utf-8 -*-
"""
==================================================
长文本深度解析服务 — core/llm_parse_service.py
==================================================

设计文档: docs/llm-deep-parse-integration.md (DSA-OPT-LLM-001)
          docs/crawler-llm-parse-integration.md (DSA-CRAWL-LLM-MERGE-V1.0)

职责（5 大核心能力）:
  1. 长篇文本分层拆解 (short/mid/long 对齐 DSA 四周期)
  2. 多文档交叉对比 (共识 / 分歧 / 乐观 / 悲观)
  3. 隐藏约束挖掘 (门槛 / 对赌 / 质押 / 配额 / 退出机制 / 苛刻前提)
  4. 长期规划提取 (产能 / 技术路线 / 产业政策周期)
  5. 隐性风险深度挖掘 (业绩拐点 / 远期利空)

核心原则:
  - LLM 只做信息提炼与逻辑梳理，涨跌区间 / 概率等量化数值一律由 DSA 数学模型输出。
  - 无 API key / 调用失败时，自动降级为确定性启发式抽取，保证流水线不中断。
  - 所有输出强制绑定原文片段（source_origin），无原文支撑内容标记 reliability 低。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DOC_TYPES = frozenset({
    "policy",          # 政策
    "broker_report",   # 券商研报
    "prospectus",      # 招股书
    "meeting_minutes", # 会议纪要
    "industry_white_paper",  # 行业白皮书
    "other",
})
VALID_MODES = frozenset({"fast", "deep"})

# ---- 关键词词典（启发式降级用） ----
_SHORT_KW = ["短期", "本周", "半月", "立即", "即时", "马上", "落地", "当天", "近月", "短期内"]
_MID_KW = ["中期", "一个月", "月度", "1个月", "阶段", "补贴周期", "准入", "门槛变化", "供需"]
_LONG_KW = ["半年", "长期", "产能", "规划", "技术路线", "三年", "五年", "产业长期", "转型", "淘汰"]
_CONSTRAINT_KW = [
    "补贴", "门槛", "对赌", "质押", "商誉", "配额", "退出", "限制", "约束", "前置条件",
    "附加", "苛刻", "前提", "红线", "不达标", "违约金",
]
_RISK_KW = [
    "利空", "下行", "风险", "下滑", "亏损", "不及预期", "拐点", "不确定", "承压",
    "订单不确定", "瓶颈", "弱化", "减值",
]


def _split_sentences(text: str) -> List[str]:
    """按中英文句末/换行切分句子，过滤空串。"""
    parts = re.split(r"[。！？\n;；]+", text or "")
    out = [p.strip() for p in parts if p and p.strip()]
    return out


def _classify_cycle(sentence: str) -> Optional[str]:
    """根据关键词判定句子归属周期层。"""
    for kw in _LONG_KW:
        if kw in sentence:
            return "long_term_halfyear"
    for kw in _MID_KW:
        if kw in sentence:
            return "mid_term_1m"
    for kw in _SHORT_KW:
        if kw in sentence:
            return "short_term_1w"
    return None


def _extract_scope(sentence: str) -> str:
    """粗略抽取关联行业/个股描述。"""
    m = re.search(r"([\u4e00-\u9fa5]{2,8}(?:行业|板块|产业|公司|个股|企业))", sentence)
    return m.group(1) if m else ""


def _heuristic_parse(text: str, doc_type: str) -> Dict[str, Any]:
    """离线确定性抽取，作为 LLM 不可用时的降级实现。"""
    sentences = _split_sentences(text)
    short_effects: List[str] = []
    mid_changes: List[str] = []
    long_plans: List[str] = []
    constraints: List[Dict[str, Any]] = []
    risks: List[str] = []

    for sent in sentences:
        cyc = _classify_cycle(sent)
        if cyc == "short_term_1w":
            short_effects.append(sent)
        elif cyc == "mid_term_1m":
            mid_changes.append(sent)
        elif cyc == "long_term_halfyear":
            long_plans.append(sent)

        for kw in _CONSTRAINT_KW:
            if kw in sent:
                risk_level = "高" if kw in ("对赌", "质押", "商誉", "红线", "违约金") else "中"
                constraints.append({
                    "content": sent,
                    "risk_level": risk_level,
                    "cycle": "生效周期待核实",
                    "source_origin": sent[:60],
                })
                break

        for kw in _RISK_KW:
            if kw in sent and sent not in risks:
                risks.append(sent)
                break

    return {
        "short_term_1w": {
            "effect": "；".join(short_effects[:5]) or "（启发式未识别短期条款）",
            "scope": _extract_scope(" ".join(short_effects)) or "待补充",
            "trigger_time": "待补充",
        },
        "mid_term_1m": {
            "industry_change": "；".join(mid_changes[:5]) or "（启发式未识别中期变化）",
            "profit_impact": "待补充",
        },
        "long_term_halfyear": {
            "industry_plan": "；".join(long_plans[:5]) or "（启发式未识别长期规划）",
            "macro_orientation": "待补充",
        },
        "hidden_constraint": constraints[:8],
        "potential_risk": risks[:8],
        "reliability": 0.4,
        "source": "heuristic",
    }


# ---- Prompt 模板（来自设计文档附录，按金融结构化要求） ----
_PROMPT_LAYER = (
    "你是专业A股投研分析师，对给定文本做严格三段分层整理，仅返回 JSON，"
    "禁止编造内容，每条内容标注 source_origin 原文片段。\n"
    "结构：\n"
    "short_term_1w: {effect, scope, trigger_time}\n"
    "mid_term_1m: {industry_change, profit_impact}\n"
    "long_term_halfyear: {industry_plan, macro_orientation}\n"
    "hidden_constraint: [{content, risk_level(高/中/低), cycle, source_origin}]\n"
    "potential_risk: [字符串]\n"
    "reliability: 0~1 浮点"
)

_PROMPT_COMPARE = (
    "对比多篇文档，整理结构化 JSON：\n"
    "consensus: 统一观点\n"
    "conflict: 分歧点\n"
    "optimistic_view: 最乐观预判\n"
    "pessimistic_view: 最悲观隐患\n"
    "每条结论标注 source_doc（文档标题）与 source_origin（原文片段）。禁止脱离原文主观臆断。"
)

_PROMPT_CONSTRAINT = (
    "通读全文，挖掘所有隐藏限制、附加门槛、业绩对赌、配额约束、远期利空、"
    "乐观假设前置苛刻条件，返回 JSON 数组：\n"
    "[{content, risk_level(高/中/低), cycle, source_origin}]"
)

_PROMPT_LONGTERM = (
    "提取文本中未来半年及以上行业产能投放、技术路线、产业政策周期、"
    "行业淘汰/扶持时间表，返回 JSON：\n"
    "{industry_plan, macro_orientation, source_origin}"
)


class LlmParseService:
    """长文本深度解析服务（5 子模块）。"""

    def __init__(self, gateway=None):
        self._gateway = gateway

    def _gw(self):
        if self._gateway is None:
            from llm.gateway import get_gateway
            self._gateway = get_gateway()
        return self._gateway

    def _doc_id(self, text: str, salt: str = "") -> str:
        h = hashlib.sha256((text + salt + str(time.time())).encode("utf-8")).hexdigest()
        return h[:16]

    def parse_document(
        self,
        text: str,
        doc_type: str = "other",
        mode: str = "deep",
        doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """能力 1+3+4+5：单文档分层拆解 + 约束挖掘 + 长期规划 + 隐性风险。"""
        if not text or not text.strip():
            return {"code": 400, "msg": "文本为空", "data": None}
        doc_type = doc_type if doc_type in DOC_TYPES else "other"
        mode = mode if mode in VALID_MODES else "deep"

        base = {
            "doc_id": doc_id or self._doc_id(text, doc_type),
            "doc_type": doc_type,
            "mode": mode,
        }

        gw = self._gw()
        system_prompt = _PROMPT_LAYER
        user_prompt = f"文档类型: {doc_type}\n待解析原文：\n{text}"
        try:
            result = gw.parse_structured(system_prompt, user_prompt, task="llm_parse")
        except Exception as exc:  # noqa: BLE001 - 解析服务不可因 LLM 异常中断
            logger.warning("[LlmParseService] LLM 调用异常，降级启发式: %s", exc)
            result = None

        if result is not None and getattr(result, "success", False) and result.data:
            data = dict(result.data)
            data.update(base)
            data["reliability"] = float(data.get("reliability", 0.8))
            data["source"] = "llm"
            return {"code": 0, "msg": "ok", "data": data}

        # 降级：确定性启发式
        heuristic = _heuristic_parse(text, doc_type)
        heuristic.update(base)
        return {"code": 0, "msg": "ok(heuristic)", "data": heuristic}

    def compare_documents(self, documents: List[Dict[str, str]]) -> Dict[str, Any]:
        """能力 2：多文档交叉对比（2~10 份）。"""
        if not documents or len(documents) < 1:
            return {"code": 400, "msg": "文档列表为空", "data": None}
        documents = documents[:10]
        titles = [d.get("title", f"doc{i}") for i, d in enumerate(documents)]
        corpus = "\n\n=== 文档分隔 ===\n\n".join(
            f"【{d.get('title', '未命名')}】\n{d.get('text', '')}" for d in documents
        )

        gw = self._gw()
        user_prompt = f"以下为 {len(documents)} 份文档：\n{corpus}"
        try:
            result = gw.parse_structured(_PROMPT_COMPARE, user_prompt, task="llm_parse")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LlmParseService] 对比 LLM 异常，降级: %s", exc)
            result = None

        if result is not None and getattr(result, "success", False) and result.data:
            data = dict(result.data)
            data["doc_count"] = len(documents)
            data["doc_titles"] = titles
            data["source"] = "llm"
            return {"code": 0, "msg": "ok", "data": data}

        # 降级：逐文档启发式抽取后合并共识/分歧
        return {
            "code": 0,
            "msg": "ok(heuristic)",
            "data": {
                "doc_count": len(documents),
                "doc_titles": titles,
                "consensus": "；".join(
                    _heuristic_parse(d.get("text", ""), "other")["short_term_1w"]["effect"]
                    for d in documents
                )[:200] or "（启发式未识别共识）",
                "conflict": "待 LLM 深度对比",
                "optimistic_view": "待补充",
                "pessimistic_view": "待补充",
                "source": "heuristic",
            },
        }

    def mine_constraints(self, text: str) -> Dict[str, Any]:
        """能力 3：隐藏约束挖掘。"""
        if not text or not text.strip():
            return {"code": 400, "msg": "文本为空", "data": None}
        gw = self._gw()
        try:
            result = gw.parse_structured(_PROMPT_CONSTRAINT, text, task="llm_parse")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LlmParseService] 约束 LLM 异常，降级: %s", exc)
            result = None
        if result is not None and getattr(result, "success", False) and result.data:
            constraints = result.data.get("constraints") or result.data.get("hidden_constraint") or []
            return {"code": 0, "msg": "ok", "data": {"hidden_constraint": constraints, "source": "llm"}}
        heuristic = _heuristic_parse(text, "other")
        return {"code": 0, "msg": "ok(heuristic)", "data": {"hidden_constraint": heuristic["hidden_constraint"], "source": "heuristic"}}

    def extract_long_term_plan(self, text: str) -> Dict[str, Any]:
        """能力 4：长期规划提取。"""
        if not text or not text.strip():
            return {"code": 400, "msg": "文本为空", "data": None}
        gw = self._gw()
        try:
            result = gw.parse_structured(_PROMPT_LONGTERM, text, task="llm_parse")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LlmParseService] 长期规划 LLM 异常，降级: %s", exc)
            result = None
        if result is not None and getattr(result, "success", False) and result.data:
            data = dict(result.data)
            data["source"] = "llm"
            return {"code": 0, "msg": "ok", "data": data}
        heuristic = _heuristic_parse(text, "other")
        return {
            "code": 0,
            "msg": "ok(heuristic)",
            "data": {
                "industry_plan": heuristic["long_term_halfyear"]["industry_plan"],
                "macro_orientation": "待补充",
                "source": "heuristic",
            },
        }


# 全局单例
_service_instance: Optional[LlmParseService] = None


def get_llm_parse_service() -> LlmParseService:
    global _service_instance
    if _service_instance is None:
        _service_instance = LlmParseService()
    return _service_instance


__all__ = ["LlmParseService", "get_llm_parse_service", "DOC_TYPES", "VALID_MODES"]
