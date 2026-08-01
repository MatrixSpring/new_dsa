# -*- coding: utf-8 -*-
"""人格化投资 Agent 决策层 (P1-①, 借鉴 ai-hedge-fund)。

多角色 Agent 并行研判 + PM(组合经理) 汇总决策：
  - valuation    估值 Agent
  - fundamental   基本面 Agent
  - technical     技术面 Agent
  - sentiment     情绪/舆情 Agent
  - risk_control  风控 Agent
  - PM            加权共识 + 最终建议 + 风险等级

LLM 增强（可选）：若 src.llm.llm_client 可用(token+网络)，调用 LLM 生成观点；
否则（默认离线）使用基于公司数据(估值/财务/一致预期/ESG/因子)的规则启发式，
保证决策层离线可用、联网即增强。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from src.multi_agent import AgentReport, ConsensusReport, MultiAgentOrchestrator

logger = logging.getLogger(__name__)

PERSONAS = {
    "valuation": {
        "role": "估值", "weight": 0.25,
        "prompt": "你是估值分析师，基于 PE/PB/PS/市值判断标的估值吸引力。",
    },
    "fundamental": {
        "role": "基本面", "weight": 0.25,
        "prompt": "你是基本面分析师，基于营收/净利润/毛利/分红判断盈利质量与成长性。",
    },
    "technical": {
        "role": "技术面", "weight": 0.15,
        "prompt": "你是技术分析师，基于动量/因子多空收益判断价格趋势。",
    },
    "sentiment": {
        "role": "情绪舆情", "weight": 0.15,
        "prompt": "你是情绪分析师，基于舆情/新闻热度判断市场情绪。",
    },
    "risk_control": {
        "role": "风控", "weight": 0.20,
        "prompt": "你是风控官，排查商誉/股权质押/限售解禁/ESG 风险。",
    },
}


def _call_llm(system: str, user: str) -> Optional[str]:
    """延迟调用 LLM（可选增强）。失败/无 token 返回 None 走规则降级。"""
    try:
        from src.llm import llm_client  # 延迟导入，避免无 token 时模块加载失败
        fn = getattr(llm_client, "chat", None) or getattr(llm_client, "complete", None)
        if not callable(fn):
            return None
        out = fn([{"role": "system", "content": system}, {"role": "user", "content": user}])
        if isinstance(out, dict):
            return out.get("content") or out.get("text")
        return str(out)
    except Exception as e:  # noqa: BLE001
        logger.debug("llm call failed (fallback to rule): %s", e)
        return None


def _rule_report(name: str, ctx: Dict[str, Any]) -> AgentReport:
    """基于公司数据字段的规则启发式观点。"""
    if name == "valuation":
        pe, pb, ps = ctx.get("pe"), ctx.get("pb"), ctx.get("ps")
        signals, flags = [], []
        score, concl = 50.0, "neutral"
        if pe is not None:
            if pe < 15 and (pb or 99) < 3:
                score, concl = 72.0, "bullish"; signals.append(f"PE={pe:.1f} 低估")
            elif pe > 45 or (pb or 0) > 6:
                score, concl = 33.0, "bearish"; signals.append(f"PE={pe:.1f} 偏高")
            else:
                signals.append(f"PE={pe:.1f} 中性")
        if ps is not None and ps > 10:
            score -= 6; flags.append(f"PS={ps:.1f} 偏贵")
        return AgentReport(agent_name=name, conclusion=concl, confidence=0.6,
                           score=score, key_signals=signals, risk_flags=flags,
                           reasoning="估值规则：低 PE/PB 看多，高估值看空。")

    if name == "fundamental":
        npf, rev, gp, dy = (ctx.get("net_profit"), ctx.get("revenue"),
                            ctx.get("gross_profit"), ctx.get("dividend_yield"))
        signals, flags = [], []
        score, concl = 50.0, "neutral"
        if npf is not None and npf > 0:
            score += 8; signals.append("净利润为正")
        if dy is not None and dy > 2:
            score += 10; concl = "bullish"; signals.append(f"股息率{dy:.1f}%")
        if gp is not None and npf is not None and npf > 0:
            signals.append("有毛利/净利数据")
        if npf is None and rev is None:
            flags.append("缺财务数据")
        score = min(85.0, max(20.0, score))
        return AgentReport(agent_name=name, conclusion=concl, confidence=0.55,
                           score=score, key_signals=signals, risk_flags=flags,
                           reasoning="基本面规则：盈利为正/高股息看多，缺财务数据谨慎。")

    if name == "technical":
        lsr = ctx.get("factor_lsr")
        signals, flags = [], []
        score, concl = 50.0, "neutral"
        if lsr is not None:
            if lsr > 0:
                score = min(80.0, 50 + lsr / 10); concl = "bullish"
                signals.append(f"因子多空收益{lsr:.1f}%")
            else:
                score = max(20.0, 50 + lsr / 10); concl = "bearish"
                signals.append(f"因子多空收益{lsr:.1f}%")
        else:
            signals.append("无动量/因子信号")
        return AgentReport(agent_name=name, conclusion=concl, confidence=0.5,
                           score=score, key_signals=signals, risk_flags=flags,
                           reasoning="技术规则：因子多空收益为正看多，为负看空。")

    if name == "sentiment":
        signals = ["无实时舆情数据，中性"]
        return AgentReport(agent_name=name, conclusion="neutral", confidence=0.4,
                           score=50.0, key_signals=signals,
                           reasoning="情绪规则：缺舆情源，默认中性。")

    if name == "risk_control":
        flags = []
        gw = ctx.get("big_goodwill"); pl = ctx.get("equity_pledges")
        ru = ctx.get("restricted_unlock"); esg = ctx.get("esg_rating")
        if gw:
            flags.append("存在大额商誉")
        if pl:
            flags.append("存在股权质押")
        if ru:
            flags.append("近期限售解禁")
        if esg and isinstance(esg, str) and esg.strip() and esg.strip()[0] in ("C", "D", "B"):
            flags.append(f"ESG评级偏低({esg})")
        score = 50.0 - 8 * len(flags)
        concl = "bearish" if len(flags) >= 2 else ("neutral" if flags else "bullish")
        return AgentReport(agent_name=name, conclusion=concl, confidence=0.7,
                           score=max(15.0, score), risk_flags=flags,
                           reasoning="风控规则：商誉/质押/解禁/低ESG 累计风险。")
    return AgentReport(agent_name=name, conclusion="neutral", score=50.0)


class PersonaAgent:
    """单个人格化 Agent：优先 LLM 增强，失败降级规则。"""

    def __init__(self, key: str):
        self.key = key
        self.meta = PERSONAS[key]

    def run(self, code: str, ctx: Dict[str, Any]) -> AgentReport:
        llm_txt = _call_llm(self.meta["prompt"], f"股票 {code} 数据: {ctx}")
        if llm_txt:
            return AgentReport(
                agent_name=self.key, conclusion="neutral", confidence=0.6,
                score=50.0, reasoning=llm_txt[:800],
            )
        return _rule_report(self.key, ctx)


def _pm_decide(reports: Dict[str, AgentReport], code: str, duration_ms: float = 0.0) -> ConsensusReport:
    """PM 汇总：加权共识 + 最终建议 + 风险等级。"""
    keys = list(reports.keys())
    total_w = sum(PERSONAS[k]["weight"] for k in keys) or 1.0
    wscore = sum(PERSONAS[k]["weight"] * reports[k].score for k in keys) / total_w
    bulls = sum(1 for r in reports.values() if r.conclusion == "bullish")
    bears = sum(1 for r in reports.values() if r.conclusion == "bearish")
    n = len(reports)
    if bulls > bears and wscore >= 55:
        consensus = "bullish"
    elif bears > bulls and wscore <= 45:
        consensus = "bearish"
    elif abs(bulls - bears) <= 1:
        consensus = "neutral"
    else:
        consensus = "divergent"
    risk_flags = [f for r in reports.values() for f in r.risk_flags]
    risk_level = "high" if len(risk_flags) >= 3 else ("medium" if risk_flags else "low")
    rec = (f"综合 {n} 位 Agent（估值/基本面/技术/情绪/风控），加权得分 {wscore:.1f}，"
           f"看多{bulls}/看空{bears}，结论【{consensus}】，风险等级【{risk_level}】。")
    return ConsensusReport(
        stock_code=code, agents=reports, consensus=consensus,
        consensus_score=round(wscore, 2), agreement_ratio=round(max(bulls, bears) / n, 2),
        key_contradictions=[], final_recommendation=rec, risk_level=risk_level,
        total_duration_ms=round(duration_ms, 1),
    )


def analyze_personas(code: str, ctx: Dict[str, Any]) -> ConsensusReport:
    """人格化 Agent 决策层入口：注册 5 角色 → 并行研判 → PM 按人格权重汇总。

    MultiAgentOrchestrator.analyze() 返回已含各角色 AgentReport 的 ConsensusReport，
    但其内置共识为等权；本层提取 agents 后由 _pm_decide 按人格权重重算加权共识。
    """
    orch = MultiAgentOrchestrator()
    for key in PERSONAS:
        orch.register(key, PersonaAgent(key).run)
    start = time.time()
    consensus_report = orch.analyze(code, ctx)
    elapsed = (time.time() - start) * 1000
    return _pm_decide(consensus_report.agents, code, duration_ms=elapsed)
