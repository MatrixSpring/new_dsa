# -*- coding: utf-8 -*-
"""
===================================
配置包桥接层 (Bridge)
===================================

历史原因：仓库中同时存在
- ``src/config.py``  （历史主配置模块，定义 ``get_config`` / ``setup_env`` /
  ``Config`` 等大量公开 API，被 40+ 个模块以
  ``from src.config import get_config`` 方式引用）
- ``src/config/``    （较新增的配置子包，含 ``settings`` / ``constants`` /
  ``security`` / ``prod_settings`` 子模块，被少量模块以
  ``from src.config.settings import settings`` 等方式引用）

Python 导入 ``src.config`` 时优先解析为**包**（目录），导致 ``src/config.py``
这一同名模块被遮蔽，``from src.config import get_config`` 会抛出
``ImportError: cannot import name 'get_config'``，整个后端无法启动。

本桥接层在包初始化时按文件路径加载历史模块 ``src/config.py``，并将其公开 API
重新导出到包命名空间，从而同时兼容两类引用方式，无需改动 40+ 处调用点。
子模块（settings / constants / ...）仍可正常通过 ``src.config.xxx`` 访问。
"""

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# src/config.py 位于 src/config/ 的上一级目录
_LEGACY_MODULE_PATH = os.path.join(os.path.dirname(_HERE), "config.py")

if os.path.isfile(_LEGACY_MODULE_PATH):
    _spec = importlib.util.spec_from_file_location(
        "_dsa_config_legacy", _LEGACY_MODULE_PATH
    )
    _legacy = importlib.util.module_from_spec(_spec)
    # 注册到 sys.modules，避免重复执行；模块内部不从 src.config 自引用，无递归风险
    sys.modules["_dsa_config_legacy"] = _legacy
    _spec.loader.exec_module(_legacy)

    # 重新导出历史模块的 API（排除 Python 双下划线魔术名称，如 __builtins__ /
    # __doc__；保留单下划线内部辅助函数，因为部分模块会显式导入它们，例如
    # ``from src.config import _get_litellm_provider``）
    for _name in dir(_legacy):
        if not _name.startswith("__"):
            globals()[_name] = getattr(_legacy, _name)

    del _spec, _legacy
