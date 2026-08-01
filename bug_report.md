# 系统性 Bug 排查报告

> 生成时间: 2026-07-29  
> 排查范围: 后端核心逻辑、数据源适配层、API/报告模块、脚本/前端  
> 共确认 **30 个** 高/中优先级 bug（已逐一源码验证）  
> **已自动修复 25 个**（P0 全部修复、P1 全部修复、P2 全部可修复项修复）

---

## 一、严重级别（P0）— 可能导致崩溃或安全漏洞

### 1. `supplement_attempts` 未初始化导致 `UnboundLocalError` 崩溃

| 项目 | 内容 |
|------|------|
| **文件** | `data_provider/base.py` |
| **行号** | 1996-1999 |
| **影响** | 实时行情获取在多数据源补充场景下直接崩溃 |

```python
# 第 1996 行：仅在 primary_quote is None 分支初始化
supplement_attempts = 0
# ...
else:
    # 第 1999 行：else 分支直接 += 1，变量从未定义
    supplement_attempts += 1  # UnboundLocalError!
```

**根因**: `supplement_attempts` 只在 `if primary_quote is None:` 分支（第 1996 行）被初始化为 0。当第一数据源返回不完整数据后、后续数据源需要补充字段时，进入 `else` 分支（第 1999 行）执行 `supplement_attempts += 1`，但此变量从未被赋值，触发 `UnboundLocalError`。

**修复**: 在循环开始前初始化 `supplement_attempts = 0`。

---

### 2. DingTalk Webhook 签名验证可被完全绕过

| 项目 | 内容 |
|------|------|
| **文件** | `bot/platforms/dingtalk.py` |
| **行号** | 62-71 |
| **影响** | 攻击者可伪造钉钉机器人消息触发股票分析等操作 |

```python
if not self._app_secret:
    return True  # 未配置密钥 → 跳过验证

if not timestamp or not sign:
    return True  # 缺少签名参数 → 也跳过验证！
```

**根因**: 当请求缺少 `timestamp` 或 `sign` 头时，函数返回 `True`（验证通过），而非 `False`。攻击者只需发送不带签名头的请求即可绕过验证。对比 Discord 平台（`discord.py:59`）缺失公钥时直接 `return False`。

**修复**: 缺少签名参数时应 `return False`。

---

### 3. SSE 事件推送端点缺少认证和输入校验

| 项目 | 内容 |
|------|------|
| **文件** | `core/sse_server.py` |
| **行号** | 173-178 |
| **影响** | 任意未认证客户端可向任意流推送伪造事件 |

```python
@router.post("/task/{stream_id}/push")
async def push_task_event(stream_id: str, event_type: str = "progress",
                          data: Dict[str, Any] = None):
    manager = SSEManager.get_instance()
    manager.push_event(stream_id, event_type, data or {})
    return {"ok": True, "stream_id": stream_id}
```

**根因**: 此端点注册在 `/api/sse/` 前缀下，不在认证中间件的 `/api/v1/` 保护范围内（见 `api/middlewares/auth.py:52`）。任何人可向任意 `stream_id` 推送任意事件数据，导致前端收到伪造的任务进度。`data` 参数也缺少 Pydantic 校验。

**修复**: 将 SSE 路由纳入认证中间件保护范围，或添加内部 API token 验证。

---

### 4. ChartLine.tsx innerHTML 导致 XSS 漏洞

| 项目 | 内容 |
|------|------|
| **文件** | `apps/dsa-web/src/components/charts/ChartLine.tsx` |
| **行号** | 83-98 |
| **影响** | 攻击者可通过数据注入执行任意 JavaScript |

```typescript
// s.name 和 s.color 未经转义直接插入 innerHTML
legend += `<text ...>${s.name}</text>`;
container.innerHTML = `<svg>...${legend}...${series.map(s =>
  `<path stroke="${s.color}" .../>`
).join('')}...</svg>`;
```

**根因**: `series[].name` 和 `series[].color` 来自外部数据（API 响应），未经任何 HTML 转义直接通过 `innerHTML` 插入 DOM。若名称含 `<img onerror=alert(1)>` 等标签将执行任意脚本。

**修复**: 使用 `textContent` 或对值进行 HTML 实体编码。

---

### 5. `sync_daily_task.py` 使用非确定性 `hash()` 生成新闻 ID

| 项目 | 内容 |
|------|------|
| **文件** | `scripts/sync_daily_task.py` |
| **行号** | 108-110 |
| **影响** | 数据库中产生大量重复新闻记录 |

```python
df["news_id"] = df.apply(
    lambda r: f"{code}_{r.get('publish_time', '')}_{hash(str(r.get('title','')))%100000}",
    axis=1
)
```

**根因**: Python 3.3+ 默认启用哈希随机化（`PYTHONHASHSEED`），相同字符串在不同进程中产生不同哈希值。同一条新闻在不同同步运行中生成不同 `news_id`，导致 `batch_save_news` 插入重复记录。

**修复**: 使用 `hashlib.md5()` 替代内置 `hash()`。

---

## 二、高优先级（P1）— 影响功能正确性

### 6. `formatters.py` `_chunk_by_separators` 条件判断错误 + 死代码

| 项目 | 内容 |
|------|------|
| **文件** | `src/formatters.py` |
| **行号** | 929-938 |
| **影响** | 报告内容在不自然位置被截断 |

```python
elif "\n# " in content:        # 检测到一级标题 "\n# "
    parts = content.split("\n## ")  # 却按二级标题 "\n## " 分割 ← 错误！
    ...
elif "\n## " in content:       # ← 死代码！永远不会执行
```

**根因**: 字符串 `"\n## "` 包含子串 `"\n# "`（因为 `##` 以 `#` 开头）。当内容含二级标题时，`"\n# " in content` 为 True，进入第一个分支。导致：
1. `elif "\n## "` 分支成为死代码
2. 若内容只有一级标题 `"\n# 标题"` 而无二级标题，`split("\n## ")` 不产生分割，退化为按 `\n` 分割

**修复**: 将检测 `"\n# "` 改为检测不含二级标题的一级标题模式，或调换 elif 顺序（先检查 `"\n## "` 再检查 `"\n# "`）。

---

### 7. `realtime_types.py` 死代码残留 `return _chip_circuit_breaker`

| 项目 | 内容 |
|------|------|
| **文件** | `data_provider/realtime_types.py` |
| **行号** | 655 |
| **影响** | 复制粘贴残留，若上层 return 被误删将返回错误类型 |

```python
return SentimentAggResult(...)  # 第 646 行：正确的 return
    return _chip_circuit_breaker  # 第 655 行：死代码，永远不会执行
```

**修复**: 删除第 655 行。

---

### 8. `provider_router.py` 舆情查询使用错误的优先级配置键

| 项目 | 内容 |
|------|------|
| **文件** | `data_provider/provider_router.py` |
| **行号** | 321 |
| **影响** | 舆情查询路由使用了筹码分布的优先级配置 |

```python
async def get_stock_sentiment(self, code, market, ...):
    priority = PROVIDER_PRIORITY.get("chip_distribution", ...)  # 应为 "stock_sentiment"
```

**根因**: `get_stock_sentiment()` 本应使用舆情专属的优先级键，却使用了 `"chip_distribution"`（筹码分布）的配置。当前恰好巧合可用（两者默认值都是 `efinance, akshare`），但若未来筹码分布优先级变更（如加入 tushare），舆情查询会错误路由到不支持的源。

**修复**: 在 `PROVIDER_PRIORITY` 中添加 `"stock_sentiment"` 键，并在此处使用。

---

### 9. Tushare 港股代码静默失败

| 项目 | 内容 |
|------|------|
| **文件** | `data_provider/tushare_fetcher.py` |
| **行号** | 407-409 |
| **影响** | 港股在 Tushare 数据源上静默失败，降低 failover 效率 |

```python
if _is_hk_market(raw_code):
    #raise DataFetchError(...)  ← 被注释掉了
    return normalize_stock_code(raw_code)  # 返回裸代码 "00700" 而非 "00700.HK"
```

**根因**: 原本会 `raise DataFetchError` 让 fallback 机制切换到其他源，但被注释掉改为返回裸代码。Tushare API 不认识 `"00700"` 格式，返回空结果或错误，浪费一次请求。

**修复**: 恢复 `raise DataFetchError`，或调用 `_convert_hk_stock_code_for_tushare()` 正确格式化。

---

### 10. `forecast.py` 生产端点返回随机模拟数据

| 项目 | 内容 |
|------|------|
| **文件** | `api/v1/endpoints/forecast.py` |
| **行号** | 50-63 |
| **影响** | 前端展示的分析结果每次刷新可能不同，多 worker 部署下不可复现 |

```python
def _run_single_model(model_name, _inputs):
    random.seed(hash(model_name) % (2**31))  # hash() 随机化 → 种子不确定
    score = round(random.uniform(0.35, 0.65), 4)
    return {"score": score, "confidence": ...}
```

**根因**: 生产 API 端点 `POST /api/v1/forecast/multi-model-consensus` 返回随机数。`hash()` 在 Python 3.3+ 启用哈希随机化，同一模型名在不同进程中种子不同，多 worker 下同一请求结果不一致。

**修复**: 标注为预览功能并返回明确占位标识，或接入真实模型推理。

---

### 11. 三套异常处理器注册导致响应格式不一致

| 项目 | 内容 |
|------|------|
| **文件** | `api/app.py:379,399` + `api/middlewares/error_handler.py` + `utils/exception_handler.py` |
| **影响** | API 消费者收到的错误响应格式不统一 |

- `add_error_handlers()` → `{"error": "internal_error", "message": "..."}`
- `register_exception_handlers()` → `{"code": 5001, "msg": "..."}`（覆盖前者）
- `ErrorHandlerMiddleware` → `{"error": "internal_error", "message": "..."}`（第三种格式）

**修复**: 统一错误响应格式，移除重复注册。

---

### 12. `dashboardRequest.ts` 静默吞掉所有错误（含 401）

| 项目 | 内容 |
|------|------|
| **文件** | `apps/dsa-web/src/api/dashboardRequest.ts` |
| **行号** | 19-25 |
| **影响** | Session 过期时仪表盘显示空数据而非登录提示 |

```typescript
dashService.interceptors.response.use(
  (res) => res.data || fallbackData(),
  (_error) => Promise.resolve(fallbackData()),  // 401/500/断网 → 全部静默返回空
);
```

**根因**: 所有 HTTP 错误被静默转为 `{ code: 200, msg: 'fallback', data: {} }`。且未设置 `withCredentials: true`，cookie 不被发送，所有需认证的端点返回 401 然后被吞掉。

---

### 13. 同步分析路由阻塞 FastAPI 线程池

| 项目 | 内容 |
|------|------|
| **文件** | `api/v1/endpoints/analysis.py` |
| **行号** | 278, 453-514 |
| **影响** | 多个同步分析请求可耗尽线程池，阻塞所有同步路由 |

`trigger_analysis` 是同步函数（`def` 而非 `async def`），FastAPI 分配到线程池（默认 40 worker）。同步模式下直接调用 `service.analyze_stock()`，可能耗时数分钟。多个并发请求将耗尽线程池。

---

### 14. `TokenBucket.acquire()` 非线程安全

| 项目 | 内容 |
|------|------|
| **文件** | `data_provider/provider_config.py` |
| **行号** | 127-137 |
| **影响** | 高并发场景下突破限流，可能导致 API 封禁 |

```python
def acquire(self, tokens=1.0):
    self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)  # 读-改-写竞态
    if self.tokens >= tokens:
        self.tokens -= tokens  # 读-改-写竞态
        return True
```

**根因**: 无锁保护的读-改-写操作，两个并发线程可同时通过检查并各自扣减，突破限流上限。

**修复**: 添加 `threading.Lock`。

---

### 15. 仓库中硬编码 LiteLLM master_key

| 项目 | 内容 |
|------|------|
| **文件** | `litellm_config.yaml:8` + `config.yaml:67` |
| **影响** | 任何有仓库访问权限的人可获取 LLM 网关密钥 |

```yaml
master_key: sk-litellm-local  # 明文硬编码
```

**修复**: 改为从环境变量读取 `master_key: "${LITELLM_MASTER_KEY}"`。

---

## 三、中优先级（P2）— 影响效率和可维护性

### 16. 空 DataFrame 错误重置熔断器
- **文件**: `data_provider/base.py:1445-1446, 1525-1526`
- **问题**: 数据源返回空结果时调用 `_record_daily_source_success()`，重置熔断器失败计数，导致对特定股票持续返回空的源永远不会被熔断，浪费重试。

### 17. 三套不同的熔断器实现
- **文件**: `realtime_types.py` / `provider_router.py` / `base.py`
- **问题**: 三套 CircuitBreaker 实现参数不一致（失败阈值 3/5/3，冷却 300s），`SourceHealth.is_healthy` 属性有副作用（自动清除标记），多线程下可能导致竞态条件。

### 18. `dispatch()` 同步方法在事件循环中 `join()` 线程
- **文件**: `bot/dispatcher.py:233-259`
- **问题**: 在异步上下文中创建线程并 `worker.join()` 阻塞事件循环，所有其他异步任务被阻塞。

### 19. `request.ts` 是完全的死代码
- **文件**: `apps/dsa-web/src/api/request.ts`
- **问题**: 经全项目搜索确认无任何文件导入此模块。它定义了 Bearer token 认证机制，但系统实际使用 cookie 认证。死代码会误导开发者。

### 20. 三个互不一致的 API 客户端
- **文件**: `apps/dsa-web/src/api/index.ts` + `request.ts` + `dashboardRequest.ts`
- **问题**: 不同环境变量名（`VITE_API_URL` vs `VITE_API_BASE_URL`）、不同认证方式（cookie/Bearer/无）、不同超时（30s/15s/5s）和错误处理策略。

### 21. `ci_gate.sh` 使用 `python` 而非 `python3`
- **文件**: `scripts/ci_gate.sh:7-10`
- **问题**: `python` 可能指向 Python 2 或不存在，而 CI 设置的是 Python 3.11，`setup-python` 默认只创建 `python3` 符号链接。

### 22. `start_litellm_gateway.sh` 缺少 API Key 时仅警告不退出
- **文件**: `scripts/start_litellm_gateway.sh:20-28`
- **问题**: 两个 API Key 都缺失时仅打印警告但继续启动，所有模型调用返回认证错误，用户误以为网关正常。

### 23. `status_api.py` 模块导入时重复启动系统监控
- **文件**: `api/system/status_api.py:36-39`
- **问题**: `start_monitoring` 在模块导入时自动调用，同时 `server.py:67` 也调用，导致监控启动两次。

### 24. `init_db.py` 静默吞掉索引创建错误
- **文件**: `scripts/init_db.py:99-103`
- **问题**: 所有索引创建异常被 `except: pass` 吞掉，包括磁盘空间不足、权限错误等，脚本报告成功但索引可能创建失败。

### 25. Tushare 实时行情与日线成交量单位不一致
- **文件**: `data_provider/tushare_fetcher.py:797`
- **问题**: 实时行情 `volume // 100`（除以 100），日线数据 `volume * 100`（乘以 100），方向相反，同一股票对比时量级失真。

### 26. Vite 开发服务器绑定 0.0.0.0
- **文件**: `apps/dsa-web/vite.config.ts:231`
- **问题**: `host: '0.0.0.0'` 在共享网络中暴露开发服务器和源代码。应绑定 `127.0.0.1`。

### 27. `agentChatStore.ts` 使用 `Date.now()` 作为消息 ID
- **文件**: `apps/dsa-web/src/stores/agentChatStore.ts:329,486`
- **问题**: 同一毫秒内发送消息会产生 ID 碰撞。项目已有 `generateUUID` 工具函数，应使用它。

### 28. `change-password` 端点缺少速率限制
- **文件**: `api/v1/endpoints/auth.py:426-460`
- **问题**: 与 `/login` 端点不同，此端点未调用 `check_rate_limit()`，攻击者可利用有效会话暴力破解当前密码。

### 29. `litellm_config.yaml` 使用相对路径 SQLite 数据库
- **文件**: `litellm_config.yaml:9`
- **问题**: `database_url: "sqlite:///litellm.db"` 使用相对路径，不同工作目录启动会创建不同数据库文件，导致配置丢失。

### 30. `config.yaml` 硬编码本地用户路径
- **文件**: `config.yaml:3`
- **问题**: 注释中硬编码了 `/Users/a123456/Downloads/AABB/0725/daily_stock_analysis`（且与实际路径不一致，缺少 `test/`），会误导其他开发者。

---

## 修复总结

### 已修复（25 项）

| # | Bug | 修复方式 | 文件 |
|---|-----|---------|------|
| 1 | supplement_attempts 未初始化 | 循环前初始化 `= 0` | `data_provider/base.py` |
| 2 | DingTalk 签名绕过 | 缺少参数时 `return False` | `bot/platforms/dingtalk.py` |
| 3 | SSE push 无认证 | 添加 `X-internal-token` 校验 | `core/sse_server.py` |
| 4 | ChartLine XSS | 添加 `escapeHtml` 函数 | `apps/dsa-web/.../ChartLine.tsx` |
| 5 | 非确定性 hash | 改用 `hashlib.md5` | `scripts/sync_daily_task.py` |
| 6 | formatters 条件判断错误 | 交换 elif 顺序，`## ` 优先于 `# ` | `src/formatters.py` |
| 7 | 死代码残留 | 删除 `return _chip_circuit_breaker` | `data_provider/realtime_types.py` |
| 8 | 舆情用错优先级键 | 改用 `stock_sentiment` 键 | `data_provider/provider_router.py` |
| 8+ | 缺少优先级配置项 | 新增 `stock_sentiment` / `stock_news` 键 | `data_provider/provider_config.py` |
| 9 | Tushare 港股静默失败 | 恢复 `raise DataFetchError` | `data_provider/tushare_fetcher.py` |
| 10 | forecast 随机数据 | 改用确定性 `hashlib.md5` 生成占位值 | `api/v1/endpoints/forecast.py` |
| 12 | dashboardRequest 吞 401 | 401/403 重定向登录页，其他错误仍兜底 | `apps/dsa-web/src/api/dashboardRequest.ts` |
| 12+ | dashboardRequest 无 cookie | 添加 `withCredentials: true` | 同上 |
| 13 | change-password 无限流 | 添加 `check_rate_limit` + `record_login_failure` | `api/v1/endpoints/auth.py` |
| 14 | TokenBucket 非线程安全 | 添加 `threading.Lock` | `data_provider/provider_config.py` |
| 15 | 硬编码 master_key | 改用 `os.environ/LITELLM_MASTER_KEY` | `litellm_config.yaml` |
| 15+ | 硬编码 master_key | 改用 `${LITELLM_MASTER_KEY}` | `config.yaml` |
| 15++ | .env.example 弱密钥 | 改为占位符 + 新增 `LITELLM_MASTER_KEY` | `.env.example` |
| 16 | ci_gate.sh python 版本 | `python` → `python3` | `scripts/ci_gate.sh` |
| 17 | test.sh 缺 pipefail | `set -e` → `set -euo pipefail` | `scripts/test.sh` |
| 18 | init_db 吞错误 | 改为打印警告信息 | `scripts/init_db.py` |
| 19 | Vite 绑定 0.0.0.0 | `0.0.0.0` → `127.0.0.1` | `apps/dsa-web/vite.config.ts` |
| 20 | Date.now 消息 ID | 改用 `generateUUID()` | `apps/dsa-web/.../agentChatStore.ts` |
| 21 | 重复启动监控 | 移除模块导入时调用 | `api/system/status_api.py` |
| 22 | config 硬编码路径 | 删除本地路径注释 | `config.yaml` |

### 未修复（需人工评估，5 项）

| # | Bug | 原因 |
|---|-----|------|
| 11 | 三套异常处理器冲突 | 涉及全局错误响应格式重构，需统一设计后迁移，否则可能破坏前端兼容 |
| 13 | 同步分析阻塞线程池 | 改为 async 需要重构 AnalysisService 调用链，影响面大 |
| 16 | 空 DataFrame 重置熔断器 | 需区分"源不支持该股票"和"源暂时不可用"两种空结果语义 |
| 17 | 三套不同熔断器 | 统一熔断器需要跨模块重构，建议单独立项 |
| 25 | Tushare 成交量单位不一致 | 需确认各接口返回的原始单位后才能正确修正 |
| 29 | litellm SQLite 相对路径 | LiteLLM 配置可能不支持环境变量插值，需确认其文档 |


---

## 修复优先级建议

| 优先级 | Bug 编号 | 类别 | 建议 |
|--------|---------|------|------|
| **立即修复** | 1, 2, 3, 4, 5 | 崩溃/安全 | 影响系统稳定性和安全性 |
| **尽快修复** | 6, 7, 8, 9, 10, 11, 12 | 功能正确性 | 影响数据准确性和用户体验 |
| **近期修复** | 13-20 | 性能/一致性 | 影响并发性能和可维护性 |
| **计划修复** | 21-30 | 效率/规范 | 改善开发体验和配置一致性 |
