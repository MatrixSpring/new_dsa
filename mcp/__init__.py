# -*- coding: utf-8 -*-
"""MCP 开放接口包（P0-③）。

将本系统的股票分析能力暴露为标准 Model Context Protocol (MCP) server，
对标 2026 年 Wind / 同花顺的 Agent 开放生态，使外部 Agent（Claude Desktop、
Cursor、自研 Agent）可直接调用本系统的公司/产业链/因子挖掘/回测/分析能力。

实现：标准 MCP over stdio（JSON-RPC 2.0），零外部依赖；内部通过本系统
REST API（http://127.0.0.1:8000/api/v1）桥接，复用全部已验证逻辑。
"""
