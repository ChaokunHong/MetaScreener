# MetaScreener 2.0 — 系统架构全景文档

> **版本**: 2.0.0a5 | **许可证**: Apache-2.0 | **作者**: Chaokun Hong
> **目标期刊**: The Lancet Digital Health
> **生成日期**: 2026-03-30

---

## 目录

1. [项目概述与设计哲学](#1-项目概述与设计哲学)
2. [技术栈与依赖](#2-技术栈与依赖)
3. [系统全局架构](#3-系统全局架构)
4. [配置中心 (configs/models.yaml)](#4-配置中心)
5. [核心层 (core/)](#5-核心层)
6. [LLM 后端抽象层 (llm/)](#6-llm-后端抽象层)
7. [IO 层 — 文件读写与 PDF 解析 (io/)](#7-io-层)
8. [Step 0: PICO 标准向导 (criteria/)](#8-step-0-pico-标准向导)
9. [Module 0: 文献检索管线 (module0_retrieval/)](#9-module-0-文献检索管线)
10. [文档理解引擎 (doc_engine/)](#10-文档理解引擎)
11. [Module 1: HCN 四层筛选系统 (module1_screening/)](#11-module-1-hcn-四层筛选系统)
12. [Module 2: PDF 数据提取系统 (module2_extraction/)](#12-module-2-pdf-数据提取系统)
13. [Module 3: 偏倚风险评估 (module3_quality/)](#13-module-3-偏倚风险评估)
14. [Meta 分析导出 (module2_extraction/export/)](#14-meta-分析导出)
15. [评价系统 (evaluation/)](#15-评价系统)
16. [API 层 (api/)](#16-api-层)
17. [前端 (frontend/)](#17-前端)
18. [数据流全链路](#18-数据流全链路)
19. [关键设计决策汇总](#19-关键设计决策汇总)

---

## 1. 项目概述与设计哲学

### 1.1 MetaScreener 是什么

MetaScreener 2.0 是一个开源的 AI 辅助系统评价 (Systematic Review, SR) 自动化平台。它利用 **多个开源大语言模型 (LLM) 构成集成学习网络**，自动化执行系统评价的核心工作流程：

1. **标准制定** — AI 辅助生成 PICO/PEO/SPIDER 纳排标准
2. **文献检索** — 多数据库并行检索 + 6 层去重 + PDF 下载 + 智能 OCR
3. **文献筛选** — 标题/摘要 + 全文两阶段 HCN 共识筛选
4. **数据提取** — 从 PDF 中提取结构化数据到 Excel 模板
5. **质量评估** — RoB 2 / ROBINS-I / QUADAS-2 偏倚风险评估
6. **Meta 分析导出** — RevMan XML / R metafor CSV / 效应量映射
7. **性能评价** — 对照金标准计算灵敏度、特异度、AUROC 等指标

### 1.2 核心设计哲学

| 原则 | 实现方式 |
|------|----------|
| **可复现性** | `temperature=0.0` + `seed=42` 贯穿全系统，符合 TRIPOD-LLM 规范 |
| **保守性** | 任何不确定性 → `HUMAN_REVIEW`，永远不会误排除 (maximise recall) |
| **多模型共识** | 4+ 开源 LLM 并行推理 → 语义规则 → 校准聚合 → 分层决策 |
| **透明性** | 每个决策附带逐元素评分、证据句引用、置信度，全程可审计 |
| **离线测试** | `MockLLMAdapter` 确保 903 个测试全部离线运行 |
| **厂商无关** | 通过 OpenRouter 统一 API 访问 200+ LLM，无厂商锁定 |

### 1.3 入口点

```
生产模式: python -m metascreener       → uvicorn on :8000
开发模式: python run.py                → FastAPI(:8000) + Vite(:5173)
         python run.py --api           → 仅后端
         python run.py --ui            → 仅前端
```

---

## 2. 技术栈与依赖

### 2.1 后端 (Python ≥3.11)

| 分类 | 库 | 用途 |
|------|----|------|
| Web 框架 | FastAPI + Uvicorn | 异步 REST API + SSE 流式传输 |
| 数据验证 | Pydantic v2 | 请求/响应模型，严格类型 |
| LLM 调用 | httpx (async) | OpenRouter HTTP 客户端 |
| Token 计数 | litellm | 精确 token 计数 (可选，有启发式后备) |
| PDF 解析 | PyMuPDF (fitz) | 文本提取 + OCR 后备 (Tesseract) |
| 文献导入 | rispy + bibtexparser v2 | RIS/BibTeX 解析 |
| Excel I/O | openpyxl | 模板编译 + 结果填充 |
| 数据处理 | pandas + numpy | 数据帧操作 |
| 统计计算 | scikit-learn + scipy | AUROC、Cohen's κ、Platt 校准 |
| 可视化 | plotly | ROC 曲线、校准图、热力图 |
| 日志 | structlog | 结构化日志 (永远不用 print) |
| 配置 | PyYAML + pydantic-settings | 模型注册表、阈值配置 |

### 2.2 前端 (Vue 3 + TypeScript)

| 库 | 版本 | 用途 |
|----|------|------|
| Vue 3 | 3.5.25 | Composition API + `<script setup>` |
| Vue Router | 4.6.4 | SPA 路由 |
| Pinia | 3.0.4 | 状态管理 (criteria store) |
| Axios | 1.13.5 | HTTP 客户端 |
| Chart.js + vue-chartjs | 4.5.1 / 5.3.3 | ROC 曲线、指标可视化 |
| PDF.js | 3.11.174 | 客户端 PDF 渲染 (CDN) |
| Vite | 7.3.1 | 构建工具 + HMR + API 代理 |

### 2.3 开发工具链

```bash
uv sync --extra dev          # 安装依赖
uv run pytest                # 运行测试 (903 tests, 全离线)
uv run ruff check src/       # Lint
uv run mypy src/             # 类型检查 (strict mode)
```

---

## 3. 系统全局架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Vue 3 前端 (SPA)                         │
│  Settings → Retrieval → Criteria → Screening → Extraction →    │
│  Quality → Evaluation → History                                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Axios → /api/* (Vite Proxy)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI API 层 (api/)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │retrieval │ │screening │ │extraction│ │ quality  │ ...       │
│  │  routes  │ │  routes  │ │  routes  │ │  routes  │          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
│       │ deps.py: 依赖注入 (LLM backends, config)                │
│       │ history_store.py: JSON 文件持久化                       │
│       │ schemas*.py: Pydantic 请求/响应模型                     │
└───────┼─────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                       业务逻辑层                                 │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────┐               │
│  │module0_      │ │criteria/ │ │module1_      │               │
│  │retrieval/   │ │PICO向导  │ │screening/   │               │
│  │5源检索+去重 │ │          │ │HCN 4层架构  │               │
│  │PDF下载+OCR  │ └──────────┘ └──────────────┘               │
│  └──────────────┘                                              │
│  ┌──────────────┐ ┌───────────┐ ┌──────────────┐              │
│  │module2_      │ │module3_   │ │evaluation/   │              │
│  │extraction/  │ │quality/   │ │指标+校准     │              │
│  │PDF数据提取  │ │RoB评估    │ │+可视化       │              │
│  │Meta分析导出 │ │           │ │              │              │
│  └──────────────┘ └───────────┘ └──────────────┘              │
└───────┬─────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    文档理解 + 基础设施层                          │
│  ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│  │ doc_engine/  │ │ llm/     │ │ io/      │ │ core/    │     │
│  │ PDF→结构文档 │ │后端抽象  │ │文件I/O   │ │数据模型  │     │
│  │ 节/表/图解析 │ │缓存/解析 │ │PDF解析   │ │枚举/异常 │     │
│  └──────────────┘ └──────────┘ └──────────┘ └──────────┘     │
└─────────────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────────────────────────────────────────────────┐
│           外部服务                                               │
│  OpenRouter API (200+ LLM) │ PubMed │ OpenAlex │ Scopus │ ... │
│  DeepSeek V3 | Qwen3 235B | Kimi K2.5 | Llama 4 Maverick      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 配置中心

**文件**: [configs/models.yaml](configs/models.yaml)

这是整个系统的**唯一配置源** (Single Source of Truth)。

### 4.1 模型注册表

系统注册了 **15 个开源 LLM**，跨 13 个厂商，分三个层级：

| 层级 | 模型 | 参数量 | 思维链 | 成本/1M tokens |
|------|------|--------|--------|----------------|
| **Tier 1 旗舰** | DeepSeek V3.2 | — | 否 | $0.26 |
| | Qwen3 235B-A22B | 235B (22B 活跃) | 是 | $0.45 |
| | Kimi K2.5 | — | 是 | $0.45 |
| **Tier 2 强力** | Kimi K2 0905 | — | 否 | $0.40 |
| | Llama 4 Maverick | 128专家MoE | 否 | $0.15 |
| | GLM-5 Turbo | — | 是 | $0.96 |
| | MiMo V2 Pro | — | 是 | $1.00 |
| | MiniMax M2.7 | — | 是 | $0.30 |
| | Nous Hermes 4 | 405B | 否 | $1.00 |
| | NVIDIA Nemotron 70B | 70B | 否 | $1.20 |
| | Cogito v2.1 671B | 671B | 否 | $1.25 |
| | AI21 Jamba Large | SSM-Transformer | 否 | $2.00 |
| **Tier 3 轻量** | Gemma 3 27B | 27B | 否 | $0.08 |
| | Mistral Small 4 | — | 否 | $0.15 |
| | Phi 4 | — | 否 | $0.07 |

### 4.2 推荐预设组合

| 预设 | 模型组合 | 成本/篇 |
|------|----------|---------|
| **Balanced (推荐)** | DeepSeek V3 + Qwen3 + Kimi K2 + Llama 4 | ~$0.005 |
| **Maximum Precision** | DeepSeek V3 + Qwen3 + Kimi K2.5 + Nous Hermes4 | ~$0.009 |
| **Budget Friendly** | DeepSeek V3 + Llama 4 + Gemma 3 + Mistral Small | ~$0.003 |
| **Comprehensive (8模型)** | 8模型全覆盖 | ~$0.019 |

### 4.3 阈值配置

```yaml
thresholds:
  tau_high: 0.50          # Tier 1 高置信度阈值
  tau_mid: 0.10           # Tier 2 中等阈值
  tau_low: 0.05           # Tier 3 低阈值
  dissent_tolerance: 0.15 # 异议容忍度: n≤6 须一致，n=7-13 允许1票异议
  target_sensitivity: 0.98

calibration:
  camd_alpha: 0.5         # 置信度感知少数检测灵敏度
  confidence_blend_alpha: 0.7  # 混合置信度权重
  ecs_threshold: 0.60     # 元素共识最低阈值
  heterogeneity_high: 0.60     # 分块异质性阈值
  prior_tier_weights:     # 贝叶斯先验权重
    1: 1.00               # Tier 1: 满权重
    2: 0.75               # Tier 2: 75%
    3: 0.50               # Tier 3: 50%
```

### 4.4 元素权重 (按框架)

```yaml
# PICO 框架
population: 1.0, intervention: 1.0, comparison: 0.6, outcome: 0.8, study_design: 0.7
# PEO 框架
population: 1.0, exposure: 1.0, outcome: 0.9, study_design: 0.7
# SPIDER 框架
sample: 1.0, phenomenon: 1.0, design: 0.8, evaluation: 0.8, research_type: 0.6
```

---

## 5. 核心层

### 5.1 数据模型 (core/models_screening.py)

```python
@dataclass
class Record:
    """一条文献记录"""
    record_id: str          # 唯一标识
    title: str
    abstract: str | None
    authors: list[str]
    year: int | None
    doi: str | None
    pmid: str | None
    journal: str | None
    keywords: list[str]
    language: str | None
    source_file: str | None
    full_text: str | None   # 全文阶段才有
```

```python
@dataclass
class ModelOutput:
    """单个 LLM 的筛选输出"""
    model_id: str
    decision: Decision          # INCLUDE / EXCLUDE / HUMAN_REVIEW / UNCLEAR
    score: float                # 纳入概率 [0, 1]
    confidence: float           # 模型自信度 [0, 1]
    rationale: str              # 推理文本
    element_assessment: dict    # 逐 PICO 元素评分
    error: str | None           # 错误信息
```

```python
@dataclass
class ScreeningDecision:
    """最终筛选决策 (Layer 4 输出)"""
    record_id: str
    decision: Decision
    tier: Tier                  # ZERO / ONE / TWO / THREE
    confidence: float           # 校准后置信度
    model_outputs: list[ModelOutput]
    rule_adjustments: list[RuleAdjustment]
    element_scores: dict[str, float]  # ECS 元素共识分
    rationale: str
```

### 5.2 枚举 (core/enums.py)

| 枚举 | 值 | 用途 |
|------|----|------|
| `Decision` | INCLUDE, EXCLUDE, HUMAN_REVIEW, UNCLEAR | 筛选决策 |
| `Tier` | ZERO, ONE, TWO, THREE | 决策层级 |
| `ScreeningStage` | TITLE_ABSTRACT, FULL_TEXT | 筛选阶段 |
| `RoBJudgement` | LOW, SOME_CONCERNS, MODERATE, HIGH, SERIOUS, CRITICAL, UNCLEAR | RoB 判定 |
| `RoBDomain` | D1-D7 (按工具不同) | RoB 领域 |
| `StudyType` | RCT, OBSERVATIONAL, DIAGNOSTIC | 研究类型 |
| `Confidence` | VERIFIED, HIGH, MEDIUM, LOW, SINGLE, FAILED | 提取置信度 |

### 5.3 异常体系 (core/exceptions.py)

```python
MetaScreenerError          # 基类
├── LLMError               # LLM 调用失败
│   ├── LLMTimeoutError    # 超时
│   ├── LLMRateLimitError  # 速率限制
│   └── LLMParseError      # 响应解析失败
├── FileFormatError        # 文件格式不支持
├── ConfigError            # 配置错误
└── ValidationError        # 数据验证失败
```

### 5.4 共识模型 (core/models_consensus.py)

```python
@dataclass
class ConsensusResult:
    """多模型共识结果"""
    decision: Decision
    score: float              # 聚合后的纳入概率
    confidence: float         # 校准后的置信度
    element_scores: dict      # 每个 PICO 元素的共识得分
    model_agreement: float    # 模型间一致率
    dissenting_models: list[str]  # 持异议的模型
```

---

## 6. LLM 后端抽象层

**目录**: [src/metascreener/llm/](src/metascreener/llm/)

### 6.1 架构概览

```
llm/
├── base.py              # 抽象基类 LLMBackend
├── factory.py           # 工厂: 从配置创建后端实例
├── response_parser.py   # 6 阶段 JSON 解析管线
├── response_cache.py    # LRU 响应缓存
├── parallel_runner.py   # 异步并行执行引擎
└── adapters/
    ├── openrouter.py    # OpenRouter HTTP 适配器
    └── mock.py          # 离线测试适配器
```

### 6.2 LLMBackend 抽象基类

```python
class LLMBackend(ABC):
    INFERENCE_TEMPERATURE = 0.0  # 始终为 0，保证可复现

    @abstractmethod
    async def _call_api(self, prompt: str, seed: int) -> str: ...

    async def complete(self, prompt: str, seed: int = 42) -> str:
        """通用补全，返回原始文本"""

    async def call_with_prompt(self, prompt: str, seed: int = 42) -> ModelOutput:
        """带结构化解析的调用"""
        # 1. 计算 prompt_hash = SHA256(prompt)
        # 2. 检查缓存: get_cached(model_id, prompt_hash)
        # 3. 缓存未命中 → _call_api() → put_cached()
        # 4. parse_llm_response() → 解析 JSON
        # 5. clamp(score, confidence) → [0, 1]
        # 6. 返回 ModelOutput

    async def screen(self, record, criteria, seed=42, stage=TA) -> ModelOutput:
        """筛选单条记录"""
        # 1. build_screening_prompt(record, criteria)
        # 2. _call_api()
        # 3. parse + clamp
        # 4. 返回 ModelOutput
```

### 6.3 OpenRouter 适配器

```python
class OpenRouterAdapter(LLMBackend):
    def __init__(self, model_id, openrouter_model_name, api_key,
                 thinking=False, reasoning_effort="none",
                 timeout_s=None, max_retries=2, max_tokens=None):
        # 超时: 非思维 45s, 思维 120s
        # max_tokens: 标准 4096, 思维 8192

    async def _call_api(self, prompt: str, seed: int) -> str:
        # 重试循环 (max_retries=2):
        #   构建 payload: model, messages, temperature=0.0, seed
        #   思维模型: reasoning.effort, 无 response_format
        #   非思维模型: response_format=json_object
        #   POST /chat/completions
        #   429 → LLMRateLimitError
        #   404 → LLMTimeoutError (模型不可用)
        #   空内容 → 重试
        #   指数退避: delay = 2 * 2^attempt
```

### 6.4 响应解析管线 (response_parser.py)

LLM 输出的 JSON 经常"不合规"，因此需要 **6 阶段渐进式修复**：

```
Stage 1: strip_thinking_tags()
         移除 <think>...</think> 块
         处理未闭合 <think> 标签
         搜索思维标签内部的 JSON (模型有时把 JSON 放进 <think> 中)

Stage 2: strip_code_fences() + json.loads()
         移除 ```json ... ``` 代码块
         尝试直接解析

Stage 3: _extract_json_object()
         找到第一个 { → 匹配花括号计数 → 提取子串
         处理字符串内转义

Stage 4: _repair_json()
         修复尾逗号: ,} → }
         修复断裂字符串值: "val1", "val2" (无冒号) → "val1; val2"
         最多 20 次迭代

Stage 5: 回退 — 从原始响应提取 + 修复

Stage 6: 最后手段 — 搜索整个原始响应中的任何 JSON 对象

失败: 抛出 LLMParseError
```

### 6.5 响应缓存 (response_cache.py)

```python
# LRU OrderedDict 实现
_MAX_CACHE_SIZE = 5000
_EVICT_FRACTION = 0.2  # 满时淘汰 20%

# 键: (model_id, SHA256(prompt))
# 值: 原始响应文本

# 函数:
get_cached(model_id, prompt_hash) → str | None  # 命中则移到末尾
put_cached(model_id, prompt_hash, response)      # 满则淘汰最旧 20%
evict_cached(model_id, prompt_hash)              # 解析失败时手动淘汰
cache_stats() → {hits, misses, size}
```

**设计原理**: temperature=0.0 时，相同 prompt 产生相同输出，缓存安全。

### 6.6 并行执行引擎 (parallel_runner.py)

```python
class ParallelRunner:
    def __init__(self, backends, timeout_s=180.0):
        self._max_consecutive_failures = 3  # 连续失败 3 次后跳过该模型

    async def run(self, record, criteria, seed=42, stage=TA) -> list[ModelOutput]:
        # asyncio.gather(*[_run_single(b, ...) for b in backends])
        # 失败的模型: error 字段非空, decision=HUMAN_REVIEW

    async def run_with_prompt(self, prompt, seed=42) -> list[ModelOutput]:
        # 使用预构建 prompt 的并行执行
```

### 6.7 工厂 (factory.py)

```python
def create_backends(cfg=None, api_key=None, enabled_model_ids=None,
                    reasoning_effort=None) -> list[LLMBackend]:
    # 1. API key 从参数或 OPENROUTER_API_KEY 环境变量
    # 2. 加载 configs/models.yaml
    # 3. 为每个启用的模型创建 OpenRouterAdapter
    # 4. 返回后端列表

def get_strongest_backend(backends, cfg) -> LLMBackend:
    # 返回第一个 Tier 1 后端，后备为第一个可用

def sort_backends_by_tier(backends, cfg) -> list[LLMBackend]:
    # 按 tier 排序 (tier 越低越强)
```

---

## 7. IO 层

**目录**: [src/metascreener/io/](src/metascreener/io/)

### 7.1 文献记录读取 (readers.py)

支持 5 种输入格式：

| 格式 | 库 | 编码策略 |
|------|----|----------|
| `.ris` | rispy | UTF-8 → Latin-1 后备 |
| `.bib` | bibtexparser v2 | Value 对象处理 |
| `.csv` | csv.Sniffer 自动检测分隔符 | 别名映射 |
| `.xml` (PubMed) | xml.etree | `<PubmedArticle>` 迭代 |
| `.xlsx` | openpyxl | 第一 sheet 作为数据 |

**统一字段映射**: 每种格式有独立的字段映射表（RIS_FIELD_MAP, BIBTEX_FIELD_MAP, CSV_COLUMN_ALIASES），最终通过 `normalize_record()` 统一为 `Record` 对象。

### 7.2 文献记录写出 (writers.py)

```python
def write_records(records, path, format_type=None) -> Path:
    # 支持: .ris, .csv, .json, .xlsx
    # CSV: UTF-8 BOM (Excel 兼容)
    # 导出字段: record_id, title, authors, year, abstract, doi, pmid, journal, keywords, language
```

### 7.3 PDF 解析 (pdf_parser.py)

```python
def extract_text_from_pdf(path: Path) -> str:
    # 1. PyMuPDF 逐页提取文本
    # 2. 空页面 → 尝试 OCR (Tesseract, DPI=300, 英文)
    # 3. Tesseract 未安装 → 优雅降级 (该页无文本)
    # 4. 页面间用 \n\n 连接
```

### 7.4 学术论文节检测 (section_detector.py)

**支持 7 种语言**: 英语、中文、日文、德文、法文、西班牙文、葡萄牙文

```python
def mark_sections(text, language=None, strip_references=False) -> str:
    # 50+ 正则模式:
    # "Abstract|Summary|Synopsis" → "## ABSTRACT"
    # "Methods|Materials and Methods" → "## METHODS"
    # "Results" → "## RESULTS"
    # "Discussion" → "## DISCUSSION"
    # "摘要" → "## ABSTRACT"  (中文)
    # "方法" → "## METHODS"   (中文)
    # ...
    # 可选: 裁剪 References 节之后的内容
```

**编号前缀处理**: `(?:\d+(?:\.\d+)*\.?\s+|[IVXLCDM]+\.?\s+)?` — 处理 "1. Methods", "III Methods" 等格式。

### 7.5 文本分块 (text_chunker.py)

```python
def chunk_text(text, max_chunk_tokens=6000, overlap_tokens=200) -> list[str]:
    # Token 估算:
    #   拉丁文: ~4 字符/token
    #   CJK: ~1.5 字符/token
    #   自动检测 (采样前 500 字符, CJK > 30% 则混合)
    #   可选: litellm.token_counter() 精确计算
    #
    # 分块策略:
    #   1. 若全文 ≤ max_chunk_tokens → 不分块
    #   2. 按段落边界 (\n\n) 分割
    #   3. 段落合并至 chunk，不超过 max_chunk_tokens
    #   4. 相邻 chunk 有 overlap_tokens 重叠
    #   5. 无段落边界 → 字符级切分 (后备)
```

### 7.6 文本质量评估 (text_quality.py)

PDF 提取质量的**前置门控**，避免对乱码文本浪费 API 调用：

```python
def assess_text_quality(text) -> TextQualityResult:
    # 三个信号:
    #   printable_ratio = 可打印字符比例
    #   word_len_score  = 平均词长 [3,8] 最优 → 1.0
    #   sentence_ratio  = 含句末标点的段落比例
    #
    # 综合分数 = 0.50 × printable + 0.25 × word_len + 0.25 × sentence
    #
    # 判定:
    #   printable < 0.70 OR score < 0.30 → FAIL (→ HUMAN_REVIEW，不排除)
    #   score < 0.60 → MARGINAL (继续但有警告)
    #   其他 → PASS
```

---

## 8. Step 0: PICO 标准向导

**目录**: [src/metascreener/criteria/](src/metascreener/criteria/)

### 8.1 架构概览

```
criteria/
├── wizard.py           # 主编排器 (CriteriaWizard)
├── consensus.py        # 多模型 Delphi 共识引擎
├── validator.py        # 标准质量验证
├── preprocessor.py     # 文本预处理
├── session.py          # 会话状态
├── models.py           # 数据模型 (PICOCriteria, CriteriaElement)
├── schema.py           # JSON Schema 定义
├── frameworks.py       # 框架定义 (PICO, PEO, SPIDER, PCC)
├── templates.py        # 框架模板
└── prompts/            # 10 个版本化 prompt 模板
    ├── generate_from_topic_v1.py    # 从主题生成标准
    ├── detect_framework_v1.py       # 检测研究框架
    ├── parse_text_v1.py             # 解析文本中的标准
    ├── suggest_terms_v1.py          # 建议搜索词
    ├── enhance_terminology_v1.py    # 增强术语 (MeSH)
    ├── validate_quality_v1.py       # 验证标准质量
    ├── refine_element_v1.py         # 精炼单个元素
    ├── auto_refine_v1.py            # 自动精炼
    ├── cross_evaluate_v1.py         # 跨模型评估
    ├── infer_from_examples_v1.py    # 从样例推断
    └── pilot_relevance_v1.py        # 试点相关性评估
```

### 8.2 CriteriaWizard 管线

```python
class CriteriaWizard:
    async def generate_from_topic(self, topic: str, backends, mode="thorough") -> PICOCriteria:
        # 1. 所有模型并行生成标准 (generate_from_topic_v1 prompt)
        # 2. 多模型 Delphi 共识:
        #    a. 每个模型独立生成 PICO 元素
        #    b. 语义去重 (合并近似术语)
        #    c. 投票: 仅保留 ≥ quorum (50%) 模型支持的术语
        #    d. 交叉评估: 每个模型评价其他模型的结果
        # 3. 术语增强 (MeSH 验证 + 同义词扩展)
        # 4. 质量验证 (完整性、歧义性、可操作性)
        # 5. 返回 PICOCriteria + 生成元数据
```

### 8.3 数据模型

```python
@dataclass
class CriteriaElement:
    name: str                       # 元素名 (population, intervention, ...)
    include: list[str]              # 纳入术语
    exclude: list[str]              # 排除术语
    element_quality: float | None   # 元素质量分 [0, 1]
    ambiguity_flags: list[str]      # 歧义标记
    model_votes: dict[str, int]     # 各模型投票计数

@dataclass
class PICOCriteria:
    framework: str                  # "pico" | "peo" | "spider" | "pcc"
    research_question: str | None
    elements: dict[str, CriteriaElement]
    study_design_include: list[str]
    study_design_exclude: list[str]
    publication_type_exclude: list[str]
    language_restriction: list[str] | None
    date_from: str | None
    date_to: str | None
    generation_meta: GenerationMeta
```

### 8.4 支持的框架

| 框架 | 元素 | 适用 |
|------|------|------|
| **PICO** | Population, Intervention, Comparison, Outcome | 干预类研究 |
| **PEO** | Population, Exposure, Outcome | 暴露类研究 |
| **SPIDER** | Sample, Phenomenon, Design, Evaluation, Research type | 质性/混合研究 |
| **PCC** | Population, Concept, Context | 范围综述 |

### 8.5 就绪度评分算法

```
readiness_score (0-100) =
    completeness (35%)    × 必填元素填充度
  + term_coverage (30%)   × 平均每元素术语数 (目标 ≥5)
  + model_consensus (20%) × 参与模型数 / 总模型数
  + dedup_quality (15%)   × 语义去重程度
```

---

## 9. Module 0: 文献检索管线

**目录**: [src/metascreener/module0_retrieval/](src/metascreener/module0_retrieval/)

### 9.1 总体架构

```
PICOCriteria
    ↓ build_query()
BooleanQuery (数据库无关 AST)
    ↓ translate_pubmed() / translate_openalex() / ...
各数据库原生查询语法
    ↓
┌──────── RetrievalOrchestrator.run() ────────┐
│                                              │
│  Stage 1: 并行搜索 (5 个检索源)             │
│    PubMed ─┐                                 │
│    OpenAlex ─┤                               │
│    Europe PMC ─┤→ list[RawRecord]            │
│    Scopus ─────┤                             │
│    Semantic Scholar ─┘                       │
│                                              │
│  Stage 2: 6 层去重                           │
│    L1: DOI → L2: PMID → L3: PMCID →         │
│    L4: 外部 ID → L5: 标题+年份 →            │
│    L6: 语义相似度 (cosine ≥ 0.95)           │
│                                              │
│  Stage 3: PDF 下载 (6 源级联)               │
│    OpenAlex直链 → EuropePMC → Unpaywall →   │
│    Semantic Scholar → PMC OA → DOI解析       │
│                                              │
│  Stage 4: 智能 OCR                          │
│    OCRRouter 按页面特征选择后端:             │
│    公式 → MinerU/VLM                         │
│    扫描件 → VLM/Tesseract                    │
│    表格 → MinerU/Marker                      │
│    纯文本 → PyMuPDF (最快)                   │
│                                              │
└──────────────────┬───────────────────────────┘
                   ↓
           RetrievalResult
           (records, dedup_log, download_results, ocr_results)
```

### 9.2 查询构建与 AST 翻译 (query/)

#### 查询构建器 (builder.py)

```python
def build_query(criteria: PICOCriteria) -> BooleanQuery:
    # 语义角色映射:
    #   population/participants/patients/sample → population 组
    #   intervention/exposure/index_test/phenomenon → intervention 组
    #   outcome/evaluation/research_type → outcome 组
    #   comparison/comparator/context/reference_standard → additional 组
    #   study_design_exclude + element exclude → exclusions 组
    #
    # 每组最多 8 个术语 (_MAX_TERMS_PER_GROUP = 8)
    # 组内 OR 连接，组间 AND 连接
```

**BooleanQuery** — 数据库无关的查询 AST:
```python
@dataclass
class BooleanQuery:
    population: QueryGroup      # OR 连接的 QueryTerm 列表
    intervention: QueryGroup
    outcome: QueryGroup
    additional: QueryGroup      # comparison 等补充条件
    exclusions: QueryGroup      # NOT 术语
```

#### AST 翻译 (ast.py)

每个数据库有独立的翻译器：

| 翻译器 | 特殊语法 | 示例 |
|--------|----------|------|
| `translate_pubmed()` | MeSH 标签、不加引号 (启用自动术语映射) | `diabetes[MeSH] AND insulin` |
| `translate_openalex()` | 多词加引号 | `"diabetes mellitus" AND insulin` |
| `translate_europepmc()` | 类 PubMed (无 MeSH) | `diabetes AND insulin` |
| `translate_scopus()` | TITLE-ABS-KEY() 包装 | `TITLE-ABS-KEY(diabetes) AND TITLE-ABS-KEY(insulin)` |
| (Semantic Scholar) | 纯文本拼接，最多 6 术语/组 | `diabetes insulin` |

### 9.3 检索源 (providers/)

#### 基类

```python
class SearchProvider(ABC):
    async def search(self, query: BooleanQuery, max_results) -> list[RawRecord]: ...
    async def fetch_metadata(self, identifiers) -> list[RawRecord]: ...
    name: str           # 提供者名称
    rate_limit: float   # 每秒请求数
```

内置 `TokenBucketLimiter` 实现令牌桶限速，支持突发。

#### 5 个检索源

| 提供者 | API | 速率限制 | 特点 |
|--------|-----|----------|------|
| **PubMed** | NCBI E-utilities (esearch+efetch) | 3/s (无 key), 10/s (有 key) | 两阶段: esearch 获取 PMID → efetch 批量获取元数据 (200/批), XML 解析 |
| **OpenAlex** | OpenAlex REST | 10/s (含 email) | 反转索引重建摘要, 查询截断 (≤8 术语/组), 分页 |
| **Europe PMC** | Europe PMC REST | 20/s | 游标分页, 全文 URL 提取, 支持大页面 (≤1000) |
| **Scopus** | Elsevier Scopus Search | 6/s | 需 Elsevier API key, TITLE-ABS-KEY() 语法, 偏移分页 (25/页) |
| **Semantic Scholar** | S2 Graph v1 | 1/s (无 key), 1.67/s (有 key) | 查询截断 (≤6 术语/组), 开放获取 PDF URL |

**工厂**: `create_provider(name, config)` 惰性加载，避免重量级导入。

### 9.4 六层去重引擎 (dedup/)

**核心**: Union-Find 数据结构，逐层合并等价记录。

```
Layer 1: DOI 匹配
  归一化: 去除 http/doi: 前缀, 小写
  → 相同归一化 DOI 的记录合并

Layer 2: PMID 匹配
  → 相同 PMID 合并

Layer 3: PMCID 匹配
  归一化: 大写 PMC 前缀格式
  → 相同 PMCID 合并

Layer 4: 外部 ID 匹配
  → OpenAlex ID / Scopus ID / S2 ID 分别匹配

Layer 5: 标题+年份匹配
  标题归一化: NFKD 分解 → 去重音 → ASCII → 小写 → 仅保留字母数字+空格
  → 归一化标题相同 AND 年份差 ≤ 1 → 合并

Layer 6: 语义相似度 (可选)
  模型: sentence-transformers (all-MiniLM-L6-v2)
  所有标题 → 嵌入向量 → L2 归一化 → 点积 = 余弦相似度
  → cosine ≥ 0.95 的记录对合并
  → sentence_transformers 不可用时优雅降级
```

**记录合并规则**:
- 标题: 取最长字符串 (锚定记录)
- 摘要: 取最长非空
- 作者: 取条目最多的列表
- 标量 ID: 取第一个非空值
- PDF URL: 去重合并，保留顺序
- source_db: 所有来源用 "+" 连接 (如 "pubmed+openalex")

**输出**: `DedupResult` 含去重后记录、完整审计日志 (MergeEvent per layer)、各层合并计数。

### 9.5 PDF 下载管理器 (downloader/)

#### 下载编排 (manager.py)

```python
class PDFDownloader:
    def __init__(self, sources, output_dir, cache=None,
                 validator=None, max_workers=16):
        # 信号量控制并发 (默认 16)

    async def download_batch(self, records, pdf_dir) -> list[DownloadResult]:
        # 每条记录:
        # 1. 检查缓存 (SQLite, 可选)
        # 2. 按优先级尝试 6 个来源
        # 3. 验证下载文件
        # 4. 缓存结果
```

#### 6 个 PDF 来源 (优先级递减)

| 优先级 | 来源 | 条件 | 策略 |
|--------|------|------|------|
| 10 | **OpenAlex 直链** | record.pdf_urls 非空 | 直接下载 |
| 20 | **Europe PMC** | 有 PMCID | `europepmc/rest/{pmcid}/fullTextPDF` |
| 30 | **Unpaywall** | 有 DOI | `api.unpaywall.org/v2/{doi}` → 最佳 OA 位置 |
| 40 | **Semantic Scholar** | 来源含 S2 | 使用 S2 提供的 PDF URL |
| 50 | **PMC OA** | 有 PMCID | `ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf` |
| 60 | **DOI 解析** | 有 DOI | 跟随 `doi.org/{doi}` 重定向 (最后手段) |

**流式下载**: 64KB 分块，首块验证 PDF 魔数 (`%PDF`)。

**文件命名**: PMID → `PMID_{id}.pdf`, PMCID → `PMCID_{id}.pdf`, DOI → `DOI_{safe}.pdf`, 无 ID → `TITLE_{sha256[:8]}.pdf`

#### PDF 验证器 (validator.py)

```python
def validate(path) -> bool:
    # 1. 文件存在
    # 2. 大小范围: 1KB ~ 500MB
    # 3. 魔数: %PDF
    # 4. HTML 拒绝模式: 403 Forbidden, Access Denied, <!DOCTYPE html
    # 5. 深度验证 (可选): PyMuPDF 打开 → 检查加密 → 页数>0 → 首页可提取文本
```

#### 下载缓存 (cache.py)

SQLite 数据库: `downloads` 表 (record_id, success, pdf_path, source, created_at)。异步访问 via `asyncio.to_thread`。

### 9.6 智能 OCR 路由 (ocr/)

#### OCR 路由器 (router.py)

每页独立分析特征，选择最优后端：

```python
class OCRRouter:
    def _analyze_page(self, page) -> PageFeatures:
        # has_text_layer: 可提取文本 ≥ 50 字符
        # has_tables: 检测到 ≥ 4 条线段/矩形
        # has_equations: 数学符号密度 ≥ 1%
        # is_scan: 无可提取文本 (纯图像)
```

**后端选择策略** (按优先级):

| 页面特征 | 后端优先级 |
|----------|-----------|
| 含公式 | MinerU → VLM → API → Marker → PyMuPDF |
| 扫描件 | VLM → API → Tesseract → PyMuPDF |
| 含表格 | MinerU → Marker → VLM → API → PyMuPDF |
| 纯文本 | **PyMuPDF** (最快，无 GPU) |

#### 5 个 OCR 后端

| 后端 | 能力 | GPU | 说明 |
|------|------|-----|------|
| **PyMuPDF** | 纯文本 | 否 | 原生提取 + 多语言节检测, 始终可用后备 |
| **VLM** | 表格+公式 | 是 | Qwen2.5-VL-7B, 页面→PNG→base64→VLM prompt |
| **Tesseract** | 扫描 OCR | 否 | 经典 OCR, 300 DPI |
| **Marker** | 学术文档结构 | 可选 | 学术论文专用提取 |
| **MinerU** | 科学文档+布局 | 可选 | 科学论文 OCR, 布局感知 |

**VLM Prompt**: "Convert to clean markdown. Preserve headings, lists, tables, equations."

**页面渲染**: 150 DPI PNG，全 PDF 后端 (Marker/MinerU) 转换一次后按页缓存。

### 9.7 数据模型

```python
@dataclass
class RawRecord:
    """单条文献记录 (检索源无关)"""
    title: str
    abstract: str | None
    authors: list[str]
    year: int | None
    journal: str | None
    doi: str | None
    pmid: str | None
    pmcid: str | None
    openalex_id: str | None
    scopus_id: str | None
    s2_id: str | None
    keywords: list[str]
    pdf_urls: list[str]
    source_db: str              # "pubmed" | "openalex" | ...

@dataclass
class DedupResult:
    records: list[RawRecord]    # 去重后的规范记录
    merge_log: list[MergeEvent] # 完整审计日志
    layer_counts: dict[int, int] # 各层合并计数

@dataclass
class MergeEvent:
    kept_id: str                # 保留的记录 ID
    merged_id: str              # 被合并的记录 ID
    layer: int                  # 去重层 (1-6)
    match_key: str              # 匹配键值

@dataclass
class RetrievalResult:
    search_counts: dict[str, int]  # {provider: count}
    total_found: int
    dedup_count: int
    downloaded: int
    ocr_completed: int
    records: list[RawRecord]
```

---

## 10. 文档理解引擎

**目录**: [src/metascreener/doc_engine/](src/metascreener/doc_engine/)

### 10.1 设计目的

doc_engine 将 PDF 从原始文件转化为**高度结构化的文档对象** (`StructuredDocument`)，供下游 Module 1 (全文筛选)、Module 2 (数据提取)、Module 3 (RoB 评估) 共用。它不仅仅是 OCR，而是完整的文档理解管线。

### 10.2 解析管线 (parser.py)

```python
class DocumentParser:
    def __init__(self, ocr_router, cache=None):
        # ocr_router: OCRRouter 实例 (来自 module0_retrieval/ocr/)
        # cache: DocumentCache (可选)

    async def parse(self, pdf_path: Path) -> StructuredDocument:
        # 1. 计算 PDF 内容哈希 (缓存键)
        # 2. 检查缓存
        # 3. OCR 转换 → raw_markdown
        # 4. 去除前言 (frontmatter)
        # 5. 若输出 < 100 字符 → 回退到 PyMuPDF 直接提取
        # 6. 从 Markdown 解析节层次结构 → sections tree
        # 7. 从 Markdown 提取表格 → tables list
        # 8. 从 Markdown 提取图表引用 → figures list
        # 9. 从 Markdown 提取元数据 → metadata
        # 10. 解析参考文献节 → references list
        # 11. 将表格关联到所属节
        # 12. 组装 StructuredDocument
        # 13. 缓存结果
```

### 10.3 结构化文档模型 (models.py)

```python
@dataclass
class StructuredDocument:
    doc_id: str
    source_path: Path
    metadata: DocumentMetadata        # 标题、作者、期刊、DOI、年份、研究类型
    sections: list[Section]           # 层次化节树
    tables: list[Table]               # 所有表格 (2D Cell 数组)
    figures: list[Figure]             # 所有图表 (含子图、提取数据)
    references: list[Reference]       # 参考文献列表
    raw_markdown: str                 # 完整 Markdown 原文
    ocr_report: OCRReport             # OCR 质量报告
    supplementary: list               # 补充材料

    def get_table(self, table_id) -> Table | None
    def get_figure(self, figure_id) -> Figure | None
    def to_markdown(self) -> str
```

#### 核心子模型

```python
@dataclass
class Section:
    heading: str                    # 节标题 (如 "Methods")
    level: int                      # 层级 (1=H1, 2=H2, ...)
    content: str                    # 节正文
    page_range: tuple[int, int]     # 起止页码
    children: list[Section]         # 子节
    tables_in_section: list[str]    # 所属表格 ID
    figures_in_section: list[str]   # 所属图表 ID

@dataclass
class Figure:
    figure_id: str
    caption: str
    type: FigureType                # FOREST_PLOT, BAR_CHART, KAPLAN_MEIER, ...
    extracted_data: dict            # VLM 预提取的数据
    sub_figures: list[SubFigure]    # 子面板
    image_path: Path | None
    page: int
    source_section: str | None

class FigureType(StrEnum):
    FOREST_PLOT = "forest_plot"     # Meta 分析森林图
    BAR_CHART = "bar_chart"
    LINE_CHART = "line_chart"
    SCATTER_PLOT = "scatter_plot"
    BOX_PLOT = "box_plot"
    FLOW_DIAGRAM = "flow_diagram"   # PRISMA 流程图
    KAPLAN_MEIER = "kaplan_meier"   # 生存曲线
    HEATMAP = "heatmap"
    OTHER = "other"
    UNKNOWN = "unknown"

@dataclass
class DocumentMetadata:
    title: str | None
    authors: list[str]
    journal: str | None
    doi: str | None
    year: int | None
    study_type: StudyType | None    # RCT / OBSERVATIONAL / DIAGNOSTIC

@dataclass
class Reference:
    ref_id: str
    raw_text: str
    doi: str | None
    title: str | None
    authors: list[str]
    year: int | None

@dataclass
class OCRReport:
    total_pages: int
    backend_usage: dict[str, int]   # {backend_name: page_count}
    conversion_time_s: float
    quality_scores: dict[int, float] # {page_num: quality_score}
    warnings: list[str]
```

### 10.4 子解析器

| 文件 | 职责 |
|------|------|
| `section_parser.py` | 从 Markdown 标题层级构建 Section 树 |
| `table_extractor.py` | 检测 Markdown 表格 → Table 对象 (2D Cell 数组) |
| `figure_extractor.py` | 提取图表引用、标题、类型分类 |
| `metadata_extractor.py` | 从标题区域提取书目元数据 |
| `reference_parser.py` | 解析参考文献列表为 Reference 列表 |
| `cache.py` | 异步文档缓存，键 = (pdf_hash, ocr_config_hash) |

### 10.5 在系统中的位置

```
module0_retrieval/ocr/ → OCRRouter → raw_markdown
                                ↓
                          doc_engine/parser.py
                                ↓
                        StructuredDocument
                          ↙     ↓      ↘
               Module 1      Module 2    Module 3
              (全文筛选)   (数据提取)  (RoB 评估)
              sections     tables +     sections
              + content    figures +    + full text
                           sections
```

---

## 11. Module 1: HCN 四层筛选系统

**目录**: [src/metascreener/module1_screening/](src/metascreener/module1_screening/)

### 11.1 HCN (Hierarchical Consensus Network) 总体架构

```
                     Record + PICOCriteria
                            │
                            ▼
               ┌───── Layer 1: 多模型推理 ─────┐
               │  4+ LLM 并行独立判断          │
               │  → 每个返回 ModelOutput        │
               │    (decision, score,           │
               │     confidence, element_scores) │
               └─────────────┬─────────────────┘
                            │ list[ModelOutput]
                            ▼
               ┌───── Layer 2: 语义规则引擎 ───┐
               │  7 条领域规则顺序执行         │
               │  → 硬规则: 直接覆盖决策       │
               │  → 软规则: 调整分数和置信度   │
               └─────────────┬─────────────────┘
                            │ 调整后的 list[ModelOutput]
                            ▼
               ┌───── Layer 3: 校准聚合 ───────┐
               │  3.1 Platt/Isotonic 校准       │
               │  3.2 加权聚合 (tier权重)       │
               │  3.3 Element Consensus Score   │
               │  3.4 异议检测 (CAMD)           │
               │  3.5 分块异质性 (全文)         │
               └─────────────┬─────────────────┘
                            │ ConsensusResult
                            ▼
               ┌───── Layer 4: 决策路由 ───────┐
               │  Tier 0: 规则硬覆盖            │
               │  Tier 1: 高置信度自动决策      │
               │  Tier 2: 多数票自动 (ECS≥0.60) │
               │  Tier 3: 人工审查              │
               └─────────────┬─────────────────┘
                            │
                            ▼
                    ScreeningDecision
```

### 11.2 Layer 1: 多模型并行推理

**文件**: [layer1/inference.py](src/metascreener/module1_screening/layer1/inference.py)

```python
class Layer1Inference:
    async def run(self, record, criteria, backends, seed=42, stage=TA) -> list[ModelOutput]:
        # ParallelRunner.run() → asyncio.gather 并行调用所有后端
        # 每个后端独立: build_prompt → _call_api → parse → ModelOutput
        # 失败的后端: decision=HUMAN_REVIEW, error 非空
```

**Prompt 结构** ([layer1/prompts/base.py](src/metascreener/module1_screening/layer1/prompts/base.py)):

```
你是一个系统评价筛选专家。

## 纳入标准
Population: [include terms] | Exclude: [exclude terms]
Intervention: ...
Comparison: ...
Outcome: ...
Study Design: include=[...], exclude=[...]

## 文献记录
Title: {title}
Abstract: {abstract}

## 输出格式
返回 JSON:
{
  "decision": "INCLUDE" | "EXCLUDE" | "UNCLEAR",
  "score": 0.0-1.0 (纳入概率),
  "confidence": 0.0-1.0 (你的确信度),
  "pico_assessment": {
    "population": {"met": true/false, "score": 0.0-1.0, "rationale": "..."},
    "intervention": {...},
    ...
  },
  "rationale": "整体推理"
}
```

### 11.3 Layer 2: 语义规则引擎

**文件**: [layer2/rule_engine.py](src/metascreener/module1_screening/layer2/rule_engine.py)

```python
class RuleEngine:
    def __init__(self, rules=None):
        self.rules = rules or [
            RetractionRule(),          # 撤稿检测
            PublicationTypeRule(),     # 发表类型过滤
            LanguageRule(),            # 语言限制
            StudyDesignRule(),         # 研究设计匹配
            PopulationRule(),          # 人群标准验证
            InterventionRule(),        # 干预措施验证
            OutcomeRule(),             # 结局指标验证
        ]

    def apply(self, outputs, criteria, record) -> list[ModelOutput]:
        for rule in self.rules:
            outputs = rule.apply(outputs, criteria, record)
        return outputs
```

**7 条规则详解**:

| # | 规则 | 类型 | 逻辑 |
|---|------|------|------|
| 1 | **RetractionRule** | 硬 | 标题含 "retracted"/"withdrawn" → 强制 EXCLUDE |
| 2 | **PublicationTypeRule** | 硬 | 标题匹配 "letter"/"editorial"/"commentary" + 在排除列表中 → 强制 EXCLUDE |
| 3 | **LanguageRule** | 硬 | 检测记录语言，若不在 language_restriction 中 → 强制 EXCLUDE |
| 4 | **StudyDesignRule** | 软 | 检测研究设计关键词，匹配排除设计 → 降低 score 30%，匹配纳入设计 → 提升 score 10% |
| 5 | **PopulationRule** | 软 | 标题/摘要匹配排除人群关键词 (animal, in vitro, pediatric) → 降低 score 20% |
| 6 | **InterventionRule** | 软 | 检测干预措施关键词匹配度，无匹配 → 降低 score 15% |
| 7 | **OutcomeRule** | 软 | 检测结局指标关键词匹配度，调整 score |

**规则基类**:
```python
class BaseRule(ABC):
    @abstractmethod
    def apply(self, outputs, criteria, record) -> list[ModelOutput]: ...

class RuleAdjustment:
    rule_name: str
    field: str           # "decision" | "score" | "confidence"
    original: Any
    adjusted: Any
    reason: str
```

### 11.4 Layer 3: 校准置信度聚合 (CCA)

**文件**: [layer3/aggregator.py](src/metascreener/module1_screening/layer3/aggregator.py)

```python
class CCAggregator:
    def aggregate(self, outputs, criteria, record,
                  prior_weights=None, fitted_calibrators=None,
                  heuristic_alpha=0.5) -> ConsensusResult:
```

**聚合算法**:

```
输入: [ModelOutput_1, ..., ModelOutput_n]
参数: prior_weights (tier 权重), fitted_calibrators (Platt/Isotonic)

步骤:
1. 置信度校准
   对每个模型 i:
     若有 fitted_calibrator[i] → φ_i = calibrator.transform(score_i)
     否则 → φ_i = score_i (原始分数)

2. 加权聚合
   w_i = prior_weights.get(tier_of_model_i, 1.0)
   aggregated_score = Σ(w_i × φ_i) / Σ(w_i)

3. Element Consensus Score (ECS)
   对每个 PICO 元素 e:
     element_score[e] = Σ(w_i × element_assessment_i[e].score) / Σ(w_i)
   ECS = Σ(element_weight[e] × element_score[e]) / Σ(element_weight[e])
   (element_weight 来自 configs/models.yaml → element_weights)

4. 决策聚合
   votes = Counter(output.decision for output in outputs)
   majority_decision = votes.most_common(1)[0]

5. 混合置信度
   decision_entropy = -Σ(p × log(p))  # p = 各决策的投票比例
   score_coherence = 1 - std([φ_i])    # 分数一致性
   confidence = α × (1 - decision_entropy) + (1 - α) × score_coherence
   (α = confidence_blend_alpha = 0.7)

6. CAMD (Confidence-Aware Minority Detection)
   dissent_count = n_outputs - majority_count
   max_allowed_dissent = floor(n_outputs × dissent_tolerance)
   若 dissent_count > max_allowed_dissent 且 minority 有高置信:
     → 标记异议，可能升级至 HUMAN_REVIEW

返回: ConsensusResult(decision, aggregated_score, confidence,
                      element_scores, model_agreement, dissenting_models)
```

### 11.5 Layer 3 子组件

#### 校准 (layer3/calibration.py)

```python
class PlattCalibrator:
    """Platt 缩放: logistic regression 将原始分数映射为概率"""
    def fit(self, scores, labels): ...    # LogisticRegression(C=1.0)
    def transform(self, scores): ...      # predict_proba()[:, 1]

class IsotonicCalibrator:
    """保序回归校准"""
    def fit(self, scores, labels): ...    # IsotonicRegression(y_min=0, y_max=1)
    def transform(self, scores): ...      # transform()
```

#### 异议检测 (layer3/disagreement.py)

```python
class DisagreementDetector:
    def detect(self, outputs, consensus) -> DisagreementReport:
        # 计算少数派模型
        # 检查少数派是否有高置信 (> 0.8)
        # 生成异议报告: 哪些模型异议、理由是什么
```

#### Element Consensus (layer3/element_consensus.py)

```python
class ElementConsensusScorer:
    def compute_ecs(self, outputs, criteria, element_weights) -> dict[str, float]:
        # 加权平均每个 PICO 元素的跨模型得分
        # 返回 {element_name: consensus_score}

    def compute_overall_ecs(self, element_scores, element_weights) -> float:
        # 加权综合所有元素 → 单一 ECS 分数
```

#### 运行时追踪器 (layer3/runtime_tracker.py)

```python
class RuntimeTracker:
    """跟踪模型运行时性能"""
    def record_latency(self, model_id, latency_s): ...
    def record_outcome(self, model_id, predicted, actual): ...
    def get_accuracy(self, model_id) -> float: ...
```

#### 权重优化器 (layer3/weight_optimizer.py)

```python
class WeightOptimizer:
    """基于验证数据优化 prior_weights"""
    def optimize(self, validation_results, gold_labels) -> dict[str, float]:
        # 基于模型历史准确率调整权重
```

### 11.6 Layer 4: 决策路由

**文件**: [layer4/router.py](src/metascreener/module1_screening/layer4/router.py)

```python
class DecisionRouter:
    def route(self, consensus, rule_adjustments, thresholds) -> ScreeningDecision:
```

**四层决策逻辑**:

```
Tier 0: 规则硬覆盖
  若 rule_adjustments 中有硬规则覆盖 (RetractionRule, PublicationTypeRule, LanguageRule)
  → 直接使用覆盖决策, tier=ZERO, confidence=1.0

Tier 1: 高置信度自动决策
  条件: confidence ≥ tau_high (0.50)
        AND 所有模型一致 (或异议在容忍范围内)
        AND ECS ≥ ecs_threshold (0.60)
  → 使用 majority decision, tier=ONE

Tier 2: 多数票自动纳入
  条件: confidence ≥ tau_mid (0.10)
        AND majority decision = INCLUDE
        AND ECS ≥ ecs_threshold (0.60)
  → decision=INCLUDE, tier=TWO
  注意: 仅自动纳入，不自动排除 (保守策略)

Tier 3: 人工审查
  所有不满足上述条件的:
    confidence < tau_mid
    OR 模型严重分歧
    OR ECS < ecs_threshold
    OR 分块异质性高 (全文筛选)
  → decision=HUMAN_REVIEW, tier=THREE
```

### 11.7 阈值优化器 (layer4/threshold_optimizer.py)

```python
class ThresholdOptimizer:
    def optimize(self, validation_data, gold_labels, seed=42,
                 min_sensitivity=0.95) -> Thresholds:
        # 网格搜索: 在满足 min_sensitivity ≥ 0.95 的约束下
        # 最大化 specificity × automation_rate
        # 返回优化后的 tau_high, tau_mid, dissent_tolerance
```

### 11.8 全文筛选特有组件

#### 全文分块策略 (ft_chunking.py)

```python
class FTChunkingStrategy:
    def chunk_for_screening(self, text, sections) -> list[TextChunk]:
        # 按学术论文节结构分块:
        # Methods, Results, Discussion 分别为独立块
        # 过长的节进一步按 6000 token 切分
        # 每块保留节名上下文
```

#### 分块异质性检测 (chunk_heterogeneity.py)

```python
class ChunkHeterogeneityDetector:
    def assess(self, chunk_results: list[ConsensusResult]) -> HeterogeneityReport:
        # 计算跨分块决策的异质性
        # 若不同块给出不同决策 → 异质性高 → HUMAN_REVIEW
        # 阈值: heterogeneity_high = 0.60, heterogeneity_moderate = 0.30
```

#### 主动学习 (active_learning.py)

```python
class ActiveLearningSelector:
    def select_pilot_batch(self, records, n=5) -> list[Record]:
        # 选择最具信息量的记录作为试点批次
        # 策略: 多样性采样 + 不确定性采样

    def incorporate_feedback(self, feedback) -> None:
        # 将用户反馈纳入后续筛选校准
```

### 11.9 T/A 筛选编排器 (ta_screener.py)

```python
class TAScreener:
    """Title/Abstract 筛选全流程编排"""
    async def screen_batch(self, records, criteria, backends,
                          pilot_size=5, seed=42) -> list[ScreeningDecision]:
        # 1. 试点筛选: 先筛 pilot_size 篇
        # 2. 用户审查试点结果、提供反馈
        # 3. 校准 (可选): 基于反馈调整阈值
        # 4. 批量筛选: 对剩余记录执行完整 4 层 HCN
        # 5. 返回所有决策
```

---

## 12. Module 2: PDF 数据提取系统

**目录**: [src/metascreener/module2_extraction/](src/metascreener/module2_extraction/)

### 12.1 总体架构

```
Excel 模板 → Compiler → ExtractionSchema
                                │
PDF 文本 → StructuredDocument   │
                │               │
                ▼               ▼
        ┌── NewOrchestrator.extract() ──┐
        │                               │
        │  1. Sheet 分类 (DATA vs MAPPING) │
        │  2. 字段收集                   │
        │  3. FieldRouter 路由           │
        │     → 每个字段分配策略         │
        │  4. 构建 ExtractionPlan       │
        │     → 3 阶段分组              │
        │                               │
        │  Phase 0: DIRECT_TABLE        │
        │    → TableReader 直接读表     │
        │    → 零 LLM 调用              │
        │                               │
        │  Phase 1: LLM_TEXT + VLM      │
        │    → 双模型 LLM 提取          │
        │    → Alpha + Beta prompt      │
        │    → asyncio.gather 并行      │
        │                               │
        │  Phase 2: COMPUTED            │
        │    → 效应量计算               │
        │    → OR, RR, MD, NNT, SE/CI  │
        │                               │
        │  四层验证:                     │
        │    V1: 源一致性 (证据在文中)  │
        │    V2: 规则验证 (类型/范围)   │
        │    V3: 模型一致性分析         │
        │    V4: 数值连贯性             │
        │                               │
        │  最终置信度聚合               │
        └─────────────┬─────────────────┘
                      │
                      ▼
           DocumentExtractionResult
                      │
           ┌──────────┼──────────┐
           ▼          ▼          ▼
      模板填充    平面Excel   JSON 导出
   (保留格式)   (带颜色编码)
```

### 12.2 模板编译管线 (compiler/)

```python
def compile_template(path: Path, llm_backend=None) -> ExtractionSchema:
    # 步骤:
    # 1. 结构扫描 (scanner.py)
    #    → 读取工作簿: sheet 名、列头、单元格类型
    #    → 返回 RawSheetInfo per sheet
    #
    # 2. 角色推断 (relationships.py)
    #    → 分类 sheet: DATA (提取目标), MAPPING, REFERENCE, DOCUMENTATION
    #    → 启发式: 行数、列数、命名模式
    #
    # 3. 关系推断 (relationships.py)
    #    → 检测跨 sheet 外键
    #    → 构建 sheet 依赖图
    #    → 确定提取顺序 (父表先于子表)
    #
    # 4. 字段增强 (ai_enhancer.py)
    #    → 为每个 DATA sheet 分析字段名/描述
    #    → 分配语义标签: AGE, SAMPLE_SIZE_ARM, EFFECT_ESTIMATE, ...
    #    → 有 LLM → AI 分类; 无 LLM → 启发式后备
    #    → 填充 dropdown_options 和 validation rules
    #
    # 5. 映射表提取
    #    → 读取 MAPPING sheet 的查找表
    #
    # 6. Schema 组装
    #    → ExtractionSchema: 所有 sheet + 字段 + 依赖关系
    #    → schema_id (UUID), version
    #
    # 缓存: LRU 32 条目，按文件内容哈希避免重复编译
```

### 12.3 字段路由 (field_router.py)

**核心**: 无 LLM 参与，纯启发式路由，确定性、快速、可测试。

```python
class FieldRouter:
    def route(self, fields, doc) -> list[FieldRoutingPlan]:
        for field in fields:
            strategy = self._determine_strategy(field, doc)
```

**路由优先级**:

| 优先级 | 策略 | 条件 | 置信先验 |
|--------|------|------|----------|
| 1 | **DIRECT_TABLE** | 字段名匹配表格列头 (精确→令牌重叠≥50%→子串≥5字符) | 0.50-0.95 |
| 2 | **COMPUTED** | 可计算统计量 (OR, RR, MD, NNT 等关键词) | 0.90 |
| 3 | **VLM_FIGURE** | 引用图表 (forest plot, figure, chart) | 0.80 |
| 4 | **LLM_TEXT** | 默认后备，附带节提示 (Methods, Results, ...) | 0.75 |

**三阶段执行计划**:
```
Phase 0: 所有 DIRECT_TABLE 字段 → 一组 (无依赖)
Phase 1: LLM_TEXT 按节分组; VLM_FIGURE 每个一组 → 可并行
Phase 2: 所有 COMPUTED 字段 → 一组 (依赖 Phase 0+1 的输出)
```

### 12.4 双模型 LLM 提取 (llm_extractor.py)

```python
class LLMExtractor:
    async def extract_field_group(self, fields, doc, section_names,
                                  backend_a, backend_b, ...)
        -> dict[str, tuple[RawExtractionResult, RawExtractionResult]]:
        # 1. 构建上下文: 相关节文本 + 可选表格 markdown
        # 2. 生成两种 prompt:
        #    Alpha (fields_first): 先列字段定义，后给文本
        #    Beta (text_first):   先给文本，后列字段定义
        # 3. asyncio.gather 并行调用两个后端
        # 4. 重试逻辑: 最多 2 次重试，3 秒间隔
        # 5. 解析 JSON 响应 → {field_name: (result_a, result_b)}
```

**Prompt 示例 (Alpha 风格)**:
```
You are an expert data extractor for systematic reviews.

## FIELDS TO EXTRACT
- **sample_size** (number): Total number of participants [REQUIRED]
- **mean_age** (number): Mean age of participants

## PAPER TEXT
[section text from PDF]

## OUTPUT FORMAT
Return ONLY valid JSON:
{
  "extracted_fields": {"sample_size": 150, "mean_age": 62.3},
  "evidence": {"sample_size": "A total of 150 patients were enrolled", ...}
}

## RULES
- Extract ONLY from provided text
- Use null for not found
- Quote exact supporting text
```

### 12.5 四层验证系统

#### V1: 源一致性 (source_coherence.py)

```python
def validate(field, raw_result, doc) -> list[ValidationIssue]:
    # DIRECT_TABLE → 直接通过
    # 无证据句 → 警告 (无法验证)
    # 证据句在文档中存在 → 模糊令牌重叠率 > 0.80 (必须)
    # 提取值出现在证据句中 → 子串或数值匹配
    # 失败严重性: "error" (潜在幻觉)
```

#### V2: 规则验证 (rule_validator.py)

```python
def validate(field, value, schema) -> list[ValidationIssue]:
    # 1. 必填字段缺失 → error
    # 2. 类型不匹配 (number/text/boolean) → warning
    # 3. 范围约束 (min_value, max_value) → warning
    # 4. 语义合理性:
    #    AGE > 200 → error
    #    SAMPLE_SIZE < 0 → error
    #    负百分比 → error
    #    比例 > 100% → error
```

#### V3: 模型一致性分析 (aggregator.py)

```python
# 在 LLM 提取阶段构建:
# 双模型同意 → HIGH (置信先验 0.90)
# 双模型不同意 + 仲裁解决 → MEDIUM (0.70)
# 双模型不同意 + 无仲裁 → LOW (0.50)
# 仅单模型成功 → SINGLE (0.60)
```

#### V4: 数值连贯性 (numerical_coherence.py)

```python
def check(all_fields) -> list[ValidationIssue]:
    # 7 条检查规则:
    # 1. 样本量求和: sum(n_arm) ≈ n_total (误差 5%)
    # 2. CI 包含估计值: ci_lower ≤ estimate ≤ ci_upper
    # 3. p 值 / CI 一致: p < 0.05 ↔ CI 不包含 null
    # 4. 事件数 ≤ 样本量: events_arm ≤ n_arm
    # 5. 百分比求和 ≈ 100% (误差 5pp)
    # 6. SD/SE 关系: SE ≈ SD / √N (误差 10%)
    # 7. 跨表一致性: 同标签字段共享一致的 N
```

### 12.6 最终置信度聚合

```python
def aggregate_confidence(v1_issues, v2_issues, v3_confidence, v4_issues,
                         strategy) -> Confidence:
    # 起点: V3 一致性置信度 (或 SINGLE)
    # 每个 V1 error → 降一级
    # 每个 V2 error → 降一级
    # 每个 V4 error → 降一级
    # DIRECT_TABLE + HIGH → 升级为 VERIFIED
    #
    # 级别映射:
    # VERIFIED (最高) ← DIRECT_TABLE + HIGH
    # HIGH:   双模型一致，无 error
    # MEDIUM: 双模型一致 + 有 warning
    # LOW:    不一致，无仲裁
    # SINGLE: 仅单模型成功
    # FAILED: 提取值为 None
```

### 12.7 仲裁机制 (arbitrator.py)

```python
class Arbitrator:
    async def arbitrate(self, field_name, value_a, evidence_a,
                        value_b, evidence_b, context_text, backend) -> ArbitrationResult:
        # 构建 prompt: 展示两个值 + 证据
        # 第三个 LLM 判断: {chosen: "A"|"B"|"neither", correct_value, reasoning}
        # seed=42 保证可复现
```

### 12.8 效应量计算 (computation.py)

```python
class ComputationEngine:
    odds_ratio(a, b, c, d)           → (a×d) / (b×c)
    risk_ratio(e1, n1, e2, n2)       → (e1/n1) / (e2/n2)
    mean_difference(m1, m2)          → m1 - m2
    ci_lower_or(or_val, se)          → exp(ln(or) - 1.96×se)
    ci_upper_or(or_val, se)          → exp(ln(or) + 1.96×se)
    nnt(arr)                         → 1 / |arr|
    se_from_ci(ci_lo, ci_hi)        → (ln(ci_hi) - ln(ci_lo)) / 3.92
    # 除零、NaN、Inf → 返回 None
```

### 12.9 导出策略

#### 模板填充 (export/template_filler.py)

```python
def export_filled_template(template_path, results, schema, output_path) -> Path:
    # 1. 逐字复制原始模板 (保留格式、公式、验证)
    # 2. 按 (pdf_id, sheet_name, row_index) 组织结果
    # 3. 对每个 DATA sheet:
    #    - 按字段名找到 EXTRACT 角色的列
    #    - 匹配提取值到单元格
    #    - 跳过公式单元格 (以 = 开头)
    #    - 逐行追加
    # 结果: 与原始模板结构相同，仅 EXTRACT 列被填充
```

#### 平面 Excel 导出 (export/excel.py)

```python
# 颜色编码:
# VERIFIED → 深绿 (#15803d)
# HIGH     → 绿色 (#22c55e)
# MEDIUM   → 黄色 (#eab308)
# LOW      → 橙色 (#f97316)
# SINGLE   → 灰色 (#a3a3a3)
# FAILED   → 红色 (#ef4444)
```

### 12.10 MANY_PER_STUDY 处理

对于一篇文献有多行数据的场景（如多个结局指标、多个亚组）：

```python
async def extract_field_group_many(self, fields, doc, section_names,
                                    backend_a, backend_b)
    -> list[dict[str, tuple[RawExtractionResult, RawExtractionResult]]]:
    # 提取返回多行: 每行是一个 dict[field_name → (result_a, result_b)]
    # LLM prompt 中明确指示: 返回 JSON 数组
    # 每行独立进行四层验证
```

### 12.11 数据模型

```python
@dataclass
class ExtractionStrategy(StrEnum):
    DIRECT_TABLE = "direct_table"
    LLM_TEXT = "llm_text"
    VLM_FIGURE = "vlm_figure"
    COMPUTED = "computed"

@dataclass
class SourceHint:
    table_id: str | None       # DIRECT_TABLE
    table_column: str | None
    section_name: str | None   # LLM_TEXT
    figure_id: str | None      # VLM_FIGURE
    panel_label: str | None
    computation_formula: str | None  # COMPUTED

@dataclass
class ExtractedField:
    field_name: str
    value: Any
    confidence: Confidence     # VERIFIED | HIGH | MEDIUM | LOW | SINGLE
    evidence: SourceLocation
    strategy: ExtractionStrategy
    validation_passed: bool
    warnings: list[str]

@dataclass
class DocumentExtractionResult:
    doc_id: str
    pdf_filename: str
    sheets: dict[str, SheetExtractionResult]
    errors: list[str]
```

---

## 13. Module 3: 偏倚风险评估

**目录**: [src/metascreener/module3_quality/](src/metascreener/module3_quality/)

### 13.1 支持的评估工具

| 工具 | 适用研究类型 | 领域数 | 信号问题数 |
|------|-------------|--------|-----------|
| **RoB 2** | 随机对照试验 (RCT) | 5 | 22 |
| **ROBINS-I** | 观察性研究 | 7 | 24 |
| **QUADAS-2** | 诊断准确性研究 | 4 | 11 |

### 13.2 RoB 2 领域详情

| 领域 | 名称 | 信号问题 | 判定选项 |
|------|------|---------|----------|
| D1 | 随机化过程 | 3 | Low / Some Concerns / High |
| D2 | 偏离预期干预 | 7 | Low / Some Concerns / High |
| D3 | 缺失结局数据 | 4 | Low / Some Concerns / High |
| D4 | 结局测量 | 5 | Low / Some Concerns / High |
| D5 | 选择性报告 | 3 | Low / Some Concerns / High |

**总体判定规则**: 最差情况 — 任一 HIGH → 总体 HIGH; 否则任一 SOME_CONCERNS → 总体 SOME_CONCERNS; 否则 LOW

### 13.3 ROBINS-I 领域详情

7 领域: 混杂偏倚、选择偏倚、分类偏倚、偏离干预、缺失数据、测量偏倚、选择性报告

**4 级严重度**: LOW (0) → MODERATE (1) → SERIOUS (2) → CRITICAL (3)

### 13.4 QUADAS-2 领域详情

4 领域: 患者选择、指标试验、参考标准、流程与时间

**3 级严重度**: LOW (0) → UNCLEAR (1) → HIGH (2)

### 13.5 评估管线 (assessor.py)

```python
class RoBAssessor:
    def __init__(self, backends, timeout_s=120.0, max_chunk_tokens=6000):
        # 至少 1 个后端

    async def assess(self, text, tool_name, record_id="", seed=42) -> RoBResult:
        # 手动选择工具

    async def assess_auto(self, text, study_type, ...) -> RoBResult:
        # 自动选择工具: RCT→RoB2, OBSERVATIONAL→ROBINS-I, DIAGNOSTIC→QUADAS-2
```

**评估管线**:

```
全文文本
    ↓
文本分块 (6000 tokens/块, 200 tokens 重叠)
    ↓
并行评估: 所有分块 × 所有模型
    每对 (块, 模型) → 独立 LLM 调用
    Prompt: 工具名 + 论文文本 + 所有领域信号问题 + JSON 输出格式
    ↓
按模型合并分块 (最差情况)
    对每个领域: 取所有块中最严重的判定
    理由: 若任一块检测到高偏倚，该领域应反映该风险
    引用: 收集所有块的支持引文
    ↓
跨模型多数投票 (按领域)
    对每个领域: 计算各判定的票数
    选择最常见判定 (多数)
    标记: 若共识未达 >50% → requires_review = true
    引用: 去重 (最多保留 5 条)
    ↓
总体判定 (via tool_schema)
    RoB2:     worst-case(LOW, SOME_CONCERNS, HIGH)
    ROBINS-I: worst-case(LOW, MODERATE, SERIOUS, CRITICAL)
    QUADAS-2: worst-case(LOW, UNCLEAR, HIGH)
    ↓
RoBResult:
    record_id, tool_name, domain_results[], overall_judgement,
    requires_human_review (= 任一领域共识未达)
```

### 13.6 Prompt 构建 (prompts/rob_v1.py)

```python
def build_rob_prompt(tool_schema, text_chunk) -> str:
    # [系统消息: 工具名]
    #
    # === PAPER TEXT ===
    # [文本块]
    #
    # === ASSESSMENT DOMAINS ===
    # ### [领域名]
    # Signaling questions:
    #   [1.1]: [问题文本] [可选回答]
    # Judgement options: [有效判定值]
    #
    # === OUTPUT FORMAT ===
    # 返回 JSON:
    # {
    #   "[领域枚举值]": {
    #     "judgement": "<valid>",
    #     "rationale": "简要说明",
    #     "supporting_quotes": ["引文1", "引文2"]
    #   }
    # }
```

---

## 14. Meta 分析导出

**目录**: [src/metascreener/module2_extraction/export/](src/metascreener/module2_extraction/export/)

MetaScreener 采用**导出驱动**的 Meta 分析策略：系统负责高质量的结构化数据提取和字段语义标注，然后导出为 Cochrane RevMan 或 R metafor 等专业 Meta 分析软件的原生格式，而非内置统计合并。

### 14.1 语义字段标签体系

Module 2 提取的每个字段可被标注为 Meta 分析相关的语义标签 (`FieldSemanticTag`)：

```python
class FieldSemanticTag(StrEnum):
    # 样本量
    SAMPLE_SIZE_TOTAL = "n_total"      # 研究总 N
    SAMPLE_SIZE_ARM = "n_arm"          # 每臂 N

    # 二分类数据 (dichotomous)
    EVENTS_ARM = "events_arm"          # 每臂事件数

    # 连续型数据 (continuous)
    MEAN = "mean"                      # 每臂均值
    SD = "sd"                          # 标准差
    SE = "se"                          # 标准误
    MEDIAN = "median"
    IQR_LOWER = "iqr_lower"
    IQR_UPPER = "iqr_upper"

    # 效应量
    EFFECT_ESTIMATE = "effect_estimate" # 预计算效应量 (OR, RR, MD)
    CI_LOWER = "ci_lower"
    CI_UPPER = "ci_upper"
    P_VALUE = "p_value"

    # 描述性
    PROPORTION = "proportion"
    STUDY_ID = "study_id"
    INTERVENTION = "intervention"
    COMPARATOR = "comparator"
    OUTCOME = "outcome"
    FOLLOW_UP = "follow_up"
```

这些标签在模板编译阶段由 `ai_enhancer.py` 自动或手动分配，贯穿整个提取和导出流程。

### 14.2 效应量映射器 (effect_size_mapper.py)

将扁平的提取字段转换为类型化的 Meta 分析数据结构：

```python
@dataclass
class DichotomousData:
    events_e: int        # 实验组事件数
    total_e: int         # 实验组总数
    events_c: int        # 对照组事件数
    total_c: int         # 对照组总数
    study_id: str

@dataclass
class ContinuousData:
    mean_e: float        # 实验组均值
    sd_e: float          # 实验组标准差
    n_e: int             # 实验组 N
    mean_c: float        # 对照组均值
    sd_c: float          # 对照组标准差
    n_c: int             # 对照组 N
    study_id: str

class EffectSizeMapper:
    def map_to_dichotomous(self, pdf_data, field_tags) -> DichotomousData | None:
        # 通过语义标签定位 EVENTS_ARM 和 SAMPLE_SIZE_ARM 字段
        # 假设第一个出现 = 实验组, 第二个 = 对照组
        # 非数值或缺失字段 → 返回 None

    def map_to_continuous(self, pdf_data, field_tags) -> ContinuousData | None:
        # 通过语义标签定位 MEAN, SD, SAMPLE_SIZE_ARM
        # 同上逻辑
```

### 14.3 Cochrane RevMan XML 导出 (revman.py)

```python
def export_to_revman(results, field_tags, output_path) -> Path:
    # 自动检测数据类型:
    #   两个 EVENTS_ARM 标签 → 二分类 → DICH_DATA 条目
    #   两个 MEAN 标签 → 连续型 → CONT_DATA 条目
    #   其他 → 通用 STUDY 条目
    #
    # 输出 XML 结构:
    # <COCHRANE_REVIEW>
    #   <ANALYSES_AND_DATA>
    #     <COMPARISON>
    #       <DICH_OUTCOME>
    #         <DICH_DATA EVENTS_1="..." TOTAL_1="..." EVENTS_2="..." TOTAL_2="..."/>
    #       </DICH_OUTCOME>
    #       <CONT_OUTCOME>
    #         <CONT_DATA MEAN_1="..." SD_1="..." TOTAL_1="..." MEAN_2="..." SD_2="..." TOTAL_2="..."/>
    #       </CONT_OUTCOME>
    #     </COMPARISON>
    #   </ANALYSES_AND_DATA>
    # </COCHRANE_REVIEW>
```

**用途**: 直接导入 Cochrane Review Manager 5，进行固定/随机效应模型合并、森林图生成、异质性检验。

### 14.4 R metafor CSV 导出 (r_meta.py)

```python
def export_to_r_meta(results, field_tags, output_path) -> Path:
    # 根据检测到的数据类型输出不同列格式:
    #
    # 二分类: study_id, ai (实验事件), n1i (实验N), ci (对照事件), n2i (对照N)
    # 连续型: study_id, m1i, sd1i, n1i, m2i, sd2i, n2i
    # 通用:   study_id, yi (效应估计), vi (方差)
```

**用途**: 直接用于 R 的 `metafor::rma()` 函数:

```r
library(metafor)
dat <- read.csv("extraction_metafor.csv")
# 二分类
res <- rma(ai=ai, n1i=n1i, ci=ci, n2i=n2i, data=dat, measure="OR")
# 连续型
res <- rma(m1i=m1i, sd1i=sd1i, n1i=n1i, m2i=m2i, sd2i=sd2i, n2i=n2i, data=dat, measure="MD")
forest(res)
```

### 14.5 导出策略对比

| 导出格式 | 文件 | 用途 | 下游工具 |
|----------|------|------|----------|
| **RevMan XML** | revman.py | Cochrane 系统评价 | Review Manager 5 |
| **R metafor CSV** | r_meta.py | 统计 Meta 分析 | R metafor / meta |
| **模板填充 Excel** | template_filler.py | 保留原始格式 | 任意 Excel 工具 |
| **平面 Excel** | excel.py | 置信度颜色编码 | 人工审查 |
| **CSV** | csv_export.py | 通用数据交换 | 任意统计软件 |

### 14.6 设计哲学: 为什么不内置 Meta 分析计算？

**专业分工原则**: Meta 分析的统计合并 (固定/随机效应模型、异质性 I²/Q 检验、发表偏倚漏斗图) 是成熟领域，已有 RevMan、R metafor、Stata 等经过广泛验证的专业工具。MetaScreener 的价值在于**上游自动化** — 高质量、结构化、带置信度的数据提取，而非重复实现下游统计。

**实际效果**: Module 2 的双模型提取 + 四层验证 + 语义标签，确保导出数据的质量足以直接用于 Meta 分析，无需人工重新核对每个数值。

---

## 15. 评价系统

**目录**: [src/metascreener/evaluation/](src/metascreener/evaluation/)

### 15.1 指标计算 (metrics.py)

#### 筛选指标

```python
def compute_screening_metrics(decisions, labels) -> ScreeningMetrics:
    # 混淆矩阵构建:
    #   INCLUDE 和 HUMAN_REVIEW 视为阳性预测 (保守: HUMAN_REVIEW → 纳入)
    #
    # sensitivity = TP / (TP + FN)          # 灵敏度 (召回率)
    # specificity = TN / (TN + FP)          # 特异度
    # precision   = TP / (TP + FP)          # 精确率
    # f1 = 2 × precision × sensitivity / (precision + sensitivity)
    # wss_at_95 = (TN + FN) / N - 1 + sensitivity  # 95% 召回率下的工作节省
    # automation_rate = count(非 HUMAN_REVIEW) / N
    # auto_sensitivity = 自动决策中的正确纳入率
```

#### AUROC

```python
def compute_auroc(scores, labels) -> AUROCResult:
    # scikit-learn: roc_auc_score + roc_curve
    # 返回 auroc, fpr[], tpr[]
```

#### 校准指标

```python
def compute_calibration_metrics(scores, labels, n_bins=10) -> CalibrationMetrics:
    # 10 个等宽 bin [0, 1)
    # ECE = Σ(bin_size/total × |mean_pred - frac_pos|)
    # MCE = max(|mean_pred - frac_pos|)
    # Brier = mean((scores - labels)²)
```

#### Bootstrap 置信区间

```python
def bootstrap_ci(metric_fn, data, n_iter=1000, seed=42) -> BootstrapResult:
    # 全数据点估计
    # 1000 次有放回重采样
    # 95% CI: 第 2.5 和 97.5 百分位
```

#### Lancet 格式化

```python
def format_lancet(point, ci_lower, ci_upper, decimals=2) -> str:
    # 输出: "0·95 (0·92–0·97)"
    # 使用中点 (U+00B7) 替代小数点
    # 使用长划线 (U+2013) 表示范围
```

### 15.2 评价运行器 (calibrator.py)

```python
def evaluate_screening(decisions, gold_labels, seed=42) -> EvaluationReport:
    # 1. 按 record_id 匹配决策和金标准
    # 2. compute_screening_metrics()
    # 3. compute_auroc() (单类则跳过)
    # 4. compute_calibration_metrics()
    # 5. bootstrap_ci() for 5 个指标 (sensitivity, specificity, precision, F1, WSS@95)
    # 6. 构建元数据 (n_records, seed, timestamp)
    # 7. 返回 EvaluationReport

def optimize_thresholds(decisions, gold_labels, min_sensitivity=0.95) -> Thresholds:
    # 委托给 Layer 4 ThresholdOptimizer

def run_calibration(decisions, gold_labels, method="platt") -> dict[str, Calibrator]:
    # 按模型拟合 Platt/Isotonic 校准器
```

### 15.3 可视化 (visualizer_charts.py + visualizer_calibration.py)

| 图表 | 函数 | 描述 |
|------|------|------|
| ROC 曲线 | `plot_roc_curve()` | FPR vs TPR + AUROC 注释 |
| 分数分布 | `plot_score_distribution()` | 纳入/排除的分数直方图 |
| 校准曲线 | `plot_calibration_curve()` | 预测概率 vs 实际阳性率 + ECE |
| RoB 热力图 | `plot_rob_heatmap()` | 研究 × 领域 交通灯矩阵 |
| 混淆矩阵 | `plot_confusion_matrix()` | TP/FP/TN/FN 可视化 |
| Tier 分布 | `plot_tier_distribution()` | Tier 0-3 的记录数分布 |

**颜色体系**:
```python
include:  "#2ecc71"  (绿)    Tier.ZERO:  "#e74c3c" (红, 规则覆盖)
exclude:  "#e74c3c"  (红)    Tier.ONE:   "#2ecc71" (绿, 高置信自动)
review:   "#f39c12"  (橙)    Tier.TWO:   "#3498db" (蓝, 多数票)
primary:  "#3498db"  (蓝)    Tier.THREE: "#f39c12" (橙, 人工审查)
```

---

## 16. API 层

**目录**: [src/metascreener/api/](src/metascreener/api/)

### 16.1 应用创建 (api/main.py 或 __init__.py)

```python
def create_app() -> FastAPI:
    app = FastAPI(title="MetaScreener 2.0")
    # 注册路由
    app.include_router(settings_router, prefix="/api/settings")
    app.include_router(screening_router, prefix="/api/screening")
    app.include_router(extraction_router, prefix="/api/v2/extraction")
    app.include_router(quality_router, prefix="/api/quality")
    app.include_router(evaluation_router, prefix="/api/evaluation")
    app.include_router(history_router, prefix="/api/history")
    # CORS 中间件
    # 静态文件服务 (生产模式)
    return app
```

### 16.2 依赖注入 (deps.py)

```python
def get_config() -> MetaScreenerConfig:
    # 加载 configs/models.yaml 单例

def get_backends() -> list[LLMBackend]:
    # create_backends() 缓存

def get_history_store() -> HistoryStore:
    # JSON 文件存储单例
```

### 16.3 路由详情

#### 设置路由 (routes/settings.py)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/settings/api-keys` | GET/PUT | 管理 API 密钥 |
| `/api/settings/models` | GET | 获取模型列表和状态 |
| `/api/settings/presets` | GET | 获取推荐预设 |
| `/api/health` | GET | 健康检查 (返回版本) |

#### 检索路由 (routes/retrieval.py)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/retrieval/search` | POST | 启动文献检索 (后台任务) |
| `/api/retrieval/search/{id}` | GET | 获取检索状态 (轮询进度) |
| `/api/retrieval/results/{id}` | GET | 获取检索结果 (支持部分结果) |
| `/api/retrieval/stop/{id}` | POST | 停止检索 |

检索使用内存 dict `_sessions` 管理会话状态（单用户本地模式）。后台任务 `_run_search` 按提供者**顺序**搜索（非并行，便于前端实时显示当前提供者进度），阶段追踪: searching → deduplicating → downloading → done。

#### 筛选路由 (routes/screening.py)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/screening/ta/run` | POST | 启动 T/A 筛选 (SSE 流) |
| `/api/screening/ft/run` | POST | 启动全文筛选 (SSE 流) |
| `/api/screening/results/{id}` | GET | 获取筛选结果 |
| `/api/screening/results/{id}/override` | PUT | 覆盖单条决策 |

#### 提取路由 (routes/extraction_runner.py)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v2/extraction/sessions` | POST | 创建提取会话 |
| `/api/v2/extraction/sessions/{id}/template` | POST | 上传 Excel 模板 |
| `/api/v2/extraction/sessions/{id}/pdfs` | POST | 上传 PDF 文件 |
| `/api/v2/extraction/sessions/{id}/run` | POST | 启动提取 (SSE 流) |
| `/api/v2/extraction/sessions/{id}/results` | GET | 获取提取结果 |
| `/api/v2/extraction/plugins` | GET | 获取可用插件 |

#### 质量路由 (routes/quality.py)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/quality/upload-pdfs` | POST | 上传 PDF |
| `/api/quality/assess` | POST | 启动 RoB 评估 |
| `/api/quality/results/{id}` | GET | 获取评估结果 |

#### 评价路由 (routes/evaluation.py + evaluation_viz.py)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/evaluation/upload-labels` | POST | 上传金标准标签 |
| `/api/evaluation/run` | POST | 运行评价 |
| `/api/evaluation/results/{id}` | GET | 获取评价报告 |

#### 历史路由 (routes/history.py)

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/history` | GET | 列出模块会话 |
| `/api/history/{module}/{id}` | GET/PUT/DELETE | CRUD 单个会话 |
| `/api/history/{module}` | DELETE | 清除模块所有会话 |

### 16.4 历史存储 (history_store.py)

```python
class HistoryStore:
    """JSON 文件持久化存储"""
    def __init__(self, base_dir: Path):
        # 目录结构: base_dir/{module}/{session_id}.json

    def save(self, module, session_id, data): ...
    def load(self, module, session_id) -> dict: ...
    def list_sessions(self, module) -> list[SessionInfo]: ...
    def delete(self, module, session_id): ...
    def clear_module(self, module): ...
```

### 16.5 SSE 流式传输模式

长时间运行的操作（筛选、提取、评估）使用 Server-Sent Events：

```python
async def run_extraction_stream(session_id):
    async def event_generator():
        yield {"event": "progress", "data": json.dumps({"pct": 0.1})}
        yield {"event": "pdf_start", "data": json.dumps({"pdf_id": "..."})}
        yield {"event": "pdf_done", "data": json.dumps({"pdf_id": "...", "results": [...]})}
        yield {"event": "batch_done", "data": json.dumps({"total": 10})}
    return EventSourceResponse(event_generator())
```

**事件类型**:
- `progress` — 进度百分比
- `pdf_start` — PDF 开始处理
- `doc_parsed` — PDF 解析完成 (质量指标)
- `pdf_done` — 单个 PDF 提取完成
- `pdf_error` — 提取错误
- `warning` — 非致命警告
- `paused` / `resumed` — 会话暂停/恢复
- `batch_done` — 整批完成

---

## 17. 前端

**目录**: [frontend/](frontend/)

### 17.1 技术架构

```
Vue 3 (Composition API + <script setup>)
├── Pinia Store: criteria.ts (全局标准状态, localStorage 持久化)
├── Composables:
│   ├── useBulkOperations.ts (提取结果批量操作)
│   └── useExtraction.ts (提取 SSE 流管理)
├── 12 个 View 页面
├── 3 个共享组件 (CriteriaSelector, TagInput, SchemaPreview)
└── Glassmorphism Aurora 主题
```

### 17.2 12 个页面与工作流

| # | 页面 | 路由 | 功能 |
|---|------|------|------|
| 1 | HomeView | `/` | 着陆页，管线概览，后端健康检查 |
| 2 | SettingsView | `/settings` | API 密钥管理，模型选择，推理配置 |
| 3 | RetrievalView | `/retrieval` | 多数据库文献检索 (PubMed, Scopus, ...) |
| 4 | CriteriaView | `/criteria` | PICO 标准定义 (AI辅助/手动/导入) |
| 5 | ScreeningLandingView | `/screening` | T/A vs 全文选择页 |
| 6 | TAScreeningView | `/screening/ta` | 标题/摘要筛选 (4步向导) |
| 7 | FTScreeningView | `/screening/ft` | 全文筛选 (4步向导) |
| 8 | ExtractionView | `/extraction` | 数据提取 (5步: 模板→PDF→提取→审查→导出) |
| 9 | ExtractionV2View | `/extraction/v2` | 备选提取工作流 |
| 10 | QualityView | `/quality` | RoB 偏倚风险评估 |
| 11 | EvaluationView | `/evaluation` | 对照金标准评价性能 |
| 12 | HistoryView | `/history` | 历史会话浏览与管理 |

### 17.3 用户完整工作流

```
1. Settings → 配置 API Key (OpenRouter) + 选择 4 个模型
       ↓
2. Criteria → AI 辅助生成 PICO 标准 (或手动输入)
       ↓                                就绪度评分 ≥ 70
3. Retrieval → 选择标准 → 选择数据库 → 搜索 → 去重 → 导出 RIS
       ↓
4. Screening T/A → 上传 RIS → 试点 5 篇 → 用户反馈 → 全量筛选
       ↓                                                纳入的文献
5. Screening FT → 上传 PDF → 全文分块筛选 → 审查 → 最终纳入
       ↓
6. Extraction → 上传 Excel 模板 → 上传 PDF → 双模型提取 → 审查 → 导出
       ↓
7. Quality → 选择 RoB 工具 → 上传 PDF → 多模型评估 → 交通灯表
       ↓
8. Evaluation → 上传金标准 → 计算指标 → Lancet 格式输出 → 发表就绪
```

### 17.4 设计系统

**Aurora Dream 主题** — 浅色毛玻璃风格:

```css
/* 品牌色 */
--primary-purple:    #8b5cf6
--tiffany-green:     #81d8d0
--robin-egg-green:   #00cccc

/* 毛玻璃效果 */
--glass-bg:          rgba(255, 255, 255, 0.22)
--glass-border:      rgba(255, 255, 255, 0.48)
backdrop-filter: blur(16px)

/* 背景: 柔和径向渐变 (粉、青、紫、黄、蓝绿) */
/* 固定附着，产生视差滚动效果 */
```

**字体**: SF Pro Display/Text (Apple) → Inter (后备)

### 17.5 状态管理策略

| 范围 | 方式 | 说明 |
|------|------|------|
| 全局 (标准) | Pinia Store + localStorage | 跨页面共享，刷新持久 |
| 页面级 | 组件 ref/reactive | 每个向导独立管理工作流状态 |
| SSE 流 | Composable (useExtraction) | 封装 EventSource 生命周期 |
| 批量操作 | Composable (useBulkOperations) | 封装选中/审查/标记逻辑 |

### 17.6 前后端通信

```
Vue 组件 → api.ts (apiGet/Post/Put/Delete/Upload)
    → Axios (baseURL: /api)
    → Vite Dev Server Proxy (/api → localhost:8000)
    → FastAPI 后端
```

长时间操作通过 **SSE (Server-Sent Events)** 实现实时反馈：
```typescript
const eventSource = new EventSource(`/api/v2/extraction/sessions/${id}/run`)
eventSource.addEventListener('pdf_done', (e) => { ... })
eventSource.addEventListener('progress', (e) => { ... })
```

---

## 18. 数据流全链路

### 18.0 检索数据流

```
PICOCriteria (from criteria wizard)
    ↓ build_query()
BooleanQuery (数据库无关 AST)
    ↓ translate_pubmed() / translate_openalex() / ...
各数据库原生查询
    ↓
RetrievalOrchestrator._search_all()
    ↓ PubMed + OpenAlex + EuropePMC + Scopus + S2 并行搜索
[list[RawRecord]]  (可能含大量重复)
    ↓
DedupEngine.deduplicate()
    ↓ L1:DOI → L2:PMID → L3:PMCID → L4:外部ID → L5:标题+年份 → L6:语义
[DedupResult]  (去重后记录 + 审计日志)
    ↓
PDFDownloader.download_batch()
    ↓ 6 源级联: OpenAlex → EuropePMC → Unpaywall → S2 → PMCOA → DOI
[list[DownloadResult]]  (PDF 文件 + 验证结果)
    ↓
OCRRouter.convert_pdf()  (per PDF)
    ↓ 按页面特征选择后端: PyMuPDF / VLM / Tesseract / Marker / MinerU
[OCRResult]  (raw_markdown per PDF)
    ↓
DocumentParser.parse()  (per PDF)
    ↓ 节解析 + 表格提取 + 图表识别 + 元数据提取 + 参考文献解析
[StructuredDocument]
    ↓
供 Module 1 (筛选) / Module 2 (提取) / Module 3 (RoB) 使用
```

### 18.1 筛选数据流

```
[RIS/BibTeX/CSV 文件]
    ↓ readers.py → normalize_record()
[list[Record]]
    ↓ + PICOCriteria (from criteria wizard)
[HCN Layer 1]
    ↓ ParallelRunner → 4 × build_screening_prompt → 4 × OpenRouter API
[list[ModelOutput]]  (每个含 decision, score, confidence, element_assessment)
    ↓
[HCN Layer 2]
    ↓ RuleEngine.apply() → 7 条规则顺序执行
[list[ModelOutput]]  (部分被硬覆盖或分数调整)
    ↓
[HCN Layer 3]
    ↓ CCAggregator.aggregate()
    ↓   校准 → 加权聚合 → ECS → CAMD → 混合置信度
[ConsensusResult]  (decision, score, confidence, element_scores)
    ↓
[HCN Layer 4]
    ↓ DecisionRouter.route()
    ↓   Tier 0/1/2/3 分流
[ScreeningDecision]  (decision, tier, confidence, rationale, ...)
    ↓
[前端展示 / JSON+CSV 导出]
```

### 18.2 提取数据流

```
[Excel 模板]
    ↓ compile_template()
[ExtractionSchema]  (sheets, fields, roles, relationships)

[PDF 文件]
    ↓ extract_text_from_pdf() → mark_sections()
[StructuredDocument]  (raw_markdown, sections, tables, figures)

[NewOrchestrator.extract()]
    ↓ FieldRouter.route()
[ExtractionPlan]  (Phase 0: TABLE, Phase 1: LLM+VLM, Phase 2: COMPUTED)

Phase 0:  TableReader → 直接读表 → [RawExtractionResult]
Phase 1:  LLMExtractor → 双 prompt × 双模型 → [(result_a, result_b)]
          FigureReader → 预提取数据 → [RawExtractionResult]
Phase 2:  ComputationEngine → 效应量公式 → [RawExtractionResult]

[四层验证]
    V1: 源一致性 (证据在文中?)
    V2: 规则验证 (类型、范围、语义)
    V3: 模型一致性 (双模型同意?)
    V4: 数值连贯性 (统计一致?)

[FinalConfidenceAggregator]
    ↓ V3 基准 → V1/V2/V4 错误降级 → TABLE升级
[DocumentExtractionResult]
    ↓
[模板填充 / 平面 Excel / JSON]
```

### 18.3 RoB 评估数据流

```
[PDF 全文]
    ↓ chunk_text()
[list[TextChunk]]  (6000 tokens/块, 200 重叠)

[RoBAssessor._assess_all_chunks()]
    ↓ 所有块 × 所有模型 → asyncio.gather
[dict[model_id → list[chunk_result]]]

[_merge_chunks_worst_case()]
    ↓ 每个领域: 取最严重判定
[dict[model_id → dict[domain → {judgement, rationale, quotes}]]]

[_compute_consensus()]
    ↓ 每个领域: 多数投票
[list[RoBDomainResult]]  (judgement, consensus_reached, quotes)

[tool_schema.get_overall_judgement()]
    ↓ 最差情况聚合
[RoBResult]  (overall_judgement, domain_results, requires_human_review)
```

---

## 19. 关键设计决策汇总

### 19.1 为什么用多模型而不是单模型？

**问题**: 单个 LLM 对系统评价筛选的可靠性不足，存在幻觉、遗漏和偏见。

**方案**: 4+ 开源模型组成集成网络，通过共识提高鲁棒性。模型来自不同厂商 (DeepSeek, Qwen, Moonshot, Meta, ...)，训练数据不同，偏见方向不同，集成后可互相校正。

### 19.2 为什么 HUMAN_REVIEW 而不是 EXCLUDE？

**问题**: 系统评价要求最大化灵敏度 (recall)，误排除比误纳入代价更高。

**方案**: 任何不确定性 → HUMAN_REVIEW。包括：LLM 解析失败、PDF 质量差、模型严重分歧、置信度低。这确保系统永远不会自动排除有争议的文献。

### 19.3 为什么四层架构？

**Layer 1 (推理)**: 独立多模型意见，避免"群体思维"
**Layer 2 (规则)**: 领域知识硬编码 (撤稿检测、类型过滤)，比 LLM 更可靠
**Layer 3 (聚合)**: 统计校准 + 加权共识，处理不确定性
**Layer 4 (路由)**: 决策透明度 — 用户知道每条记录为什么被筛入/筛出/送人工

### 19.4 为什么 temperature=0.0 + seed=42？

**TRIPOD-LLM 规范**要求 AI 辅助研究工具的可复现性。相同输入必须产生相同输出。这也使得响应缓存安全有效。

### 19.5 为什么用 OpenRouter 而不是直接调用各厂商 API？

**统一接口**: 一个 API 密钥访问 200+ 模型，无厂商锁定。
**成本优化**: OpenRouter 支持价格路由、负载均衡。
**简化代码**: 只需一个适配器实现。

### 19.6 为什么提取用双模型 + 不同 prompt？

**认知多样性**: Alpha prompt (先字段后文本) 和 Beta prompt (先文本后字段) 激活模型的不同推理路径。两个模型 + 两种 prompt = 更高的错误检出率。当两者同意时置信度高；不同意时可通过仲裁或降级处理。

### 19.7 为什么字段路由不用 LLM？

**确定性**: 启发式路由是确定性的，不依赖 LLM 的不确定输出。
**速度**: 微秒级完成，无 API 延迟。
**可测试**: 纯函数，易于单元测试。
**优先级**: TABLE > COMPUTED > VLM > LLM 确保最快路径优先。

### 19.8 为什么 RoB 评估用"最差情况"合并分块？

**保守原则**: 如果论文的任何部分暗示高偏倚风险，该领域就应反映该风险。这避免了长文章中偏倚信号被大量"正常"内容稀释。

### 19.9 为什么响应解析需要 6 个阶段？

**现实问题**: 不同 LLM 输出 JSON 的方式各不相同 — 有的包裹在 `<think>` 标签中，有的加代码围栏，有的有尾逗号，有的截断字符串。6 阶段渐进式修复覆盖了所有已知的失败模式，确保 > 99% 的响应可被成功解析。

### 19.10 为什么文献检索用 6 层去重？

**问题**: 跨数据库检索产生大量重复，同一文献在不同库中的元数据格式不同（有的有 DOI，有的有 PMID，有的只有标题）。

**方案**: 6 层渐进式匹配 — 先精确 ID 匹配 (DOI→PMID→PMCID→外部ID)，再模糊匹配 (标题+年份)，最后语义相似度 (cosine ≥ 0.95)。Union-Find 数据结构确保传递性合并，完整审计日志支持可追溯。

### 19.11 为什么 Meta 分析采用导出驱动而非内置计算？

**专业分工**: Meta 分析统计方法 (固定/随机效应、I²异质性、漏斗图) 已有 RevMan、R metafor 等经过数十年验证的工具。MetaScreener 的价值在于上游自动化 — 确保导出数据的质量足以直接用于 Meta 分析，而非重复造轮子。

---

## 附录 A: 文件清单

```
src/metascreener/
├── __init__.py
├── __main__.py              # 入口: uvicorn 服务器
├── config.py                # MetaScreenerConfig (加载 YAML)
│
├── core/
│   ├── enums.py             # Decision, Tier, ScreeningStage, ...
│   ├── exceptions.py        # 异常层次结构
│   ├── models_screening.py  # Record, ModelOutput, ScreeningDecision
│   └── models_consensus.py  # ConsensusResult
│
├── llm/
│   ├── base.py              # LLMBackend ABC
│   ├── factory.py           # create_backends()
│   ├── response_parser.py   # 6 阶段 JSON 解析
│   ├── response_cache.py    # LRU 缓存
│   ├── parallel_runner.py   # 异步并行引擎
│   └── adapters/
│       ├── openrouter.py    # OpenRouter HTTP
│       └── mock.py          # 离线测试
│
├── io/
│   ├── readers.py           # 多格式读取 (RIS/BibTeX/CSV/XML/Excel)
│   ├── writers.py           # 多格式写出
│   ├── parsers.py           # 字段规范化
│   ├── pdf_parser.py        # PyMuPDF + OCR
│   ├── section_detector.py  # 学术论文节检测 (7种语言)
│   ├── text_chunker.py      # Token 感知分块
│   └── text_quality.py      # 文本质量门控
│
├── criteria/
│   ├── wizard.py            # CriteriaWizard 主编排器
│   ├── consensus.py         # Delphi 多模型共识
│   ├── validator.py         # 标准质量验证
│   ├── preprocessor.py      # 文本预处理
│   ├── session.py           # 会话状态
│   ├── models.py            # PICOCriteria, CriteriaElement
│   ├── schema.py            # JSON Schema
│   ├── frameworks.py        # PICO/PEO/SPIDER/PCC 定义
│   ├── templates.py         # 框架模板
│   └── prompts/             # 10 个版本化 prompt
│       ├── generate_from_topic_v1.py
│       ├── detect_framework_v1.py
│       ├── parse_text_v1.py
│       ├── suggest_terms_v1.py
│       ├── enhance_terminology_v1.py
│       ├── validate_quality_v1.py
│       ├── refine_element_v1.py
│       ├── auto_refine_v1.py
│       ├── cross_evaluate_v1.py
│       ├── infer_from_examples_v1.py
│       └── pilot_relevance_v1.py
│
├── module0_retrieval/
│   ├── orchestrator.py      # RetrievalOrchestrator 主编排器
│   ├── models.py            # RawRecord, BooleanQuery, DedupResult, ...
│   ├── providers/
│   │   ├── base.py          # SearchProvider ABC + TokenBucketLimiter
│   │   ├── pubmed.py        # PubMed (NCBI E-utilities)
│   │   ├── openalex.py      # OpenAlex REST API
│   │   ├── europepmc.py     # Europe PMC REST API
│   │   ├── scopus.py        # Elsevier Scopus API
│   │   └── semantic_scholar.py  # Semantic Scholar Graph v1
│   ├── query/
│   │   ├── builder.py       # PICO → BooleanQuery
│   │   └── ast.py           # AST → 各数据库原生语法
│   ├── dedup/
│   │   ├── engine.py        # 6 层去重引擎 (Union-Find)
│   │   ├── rules.py         # L1-L5 规则匹配器
│   │   └── semantic.py      # L6 语义相似度 (sentence-transformers)
│   ├── downloader/
│   │   ├── manager.py       # PDFDownloader 级联下载器
│   │   ├── sources.py       # 6 个 PDF 来源
│   │   ├── cache.py         # SQLite 下载缓存
│   │   └── validator.py     # PDF 文件验证
│   └── ocr/
│       ├── router.py        # OCRRouter 智能后端选择
│       ├── base.py          # OCRBackend ABC
│       ├── pymupdf_backend.py   # 原生文本提取
│       ├── vlm_backend.py       # VLM 视觉模型
│       ├── tesseract_backend.py # OCR
│       ├── marker_backend.py    # 学术文档结构
│       ├── mineru_backend.py    # 科学文档 OCR
│       └── api_backend.py       # API OCR 服务
│
├── doc_engine/
│   ├── parser.py            # DocumentParser 主编排器
│   ├── models.py            # StructuredDocument, Section, Figure, ...
│   ├── section_parser.py    # Markdown → 节层次树
│   ├── table_extractor.py   # Markdown → Table 对象
│   ├── figure_extractor.py  # 图表引用提取
│   ├── metadata_extractor.py # 书目元数据提取
│   ├── reference_parser.py  # 参考文献解析
│   └── cache.py             # 文档缓存
│
├── module1_screening/
│   ├── hcn_screener.py      # HCN 基类编排器
│   ├── ta_screener.py       # T/A 筛选器 (含试点)
│   ├── ft_chunking.py       # 全文分块策略
│   ├── chunk_heterogeneity.py  # 分块异质性检测
│   ├── active_learning.py   # 主动学习/试点选择
│   ├── layer1/
│   │   ├── inference.py     # 多模型并行推理
│   │   └── prompts/
│   │       └── base.py      # 筛选 prompt 构建器
│   ├── layer2/
│   │   ├── rule_engine.py   # 规则引擎
│   │   └── rules/
│   │       ├── base.py      # BaseRule ABC
│   │       ├── helpers.py   # 关键词匹配工具
│   │       ├── retraction.py    # 撤稿检测 (硬)
│   │       ├── publication_type.py  # 类型过滤 (硬)
│   │       ├── language.py      # 语言限制 (硬)
│   │       ├── study_design.py  # 研究设计 (软)
│   │       ├── population.py    # 人群匹配 (软)
│   │       ├── intervention.py  # 干预匹配 (软)
│   │       └── outcome.py       # 结局匹配 (软)
│   ├── layer3/
│   │   ├── aggregator.py        # CCA 聚合器
│   │   ├── calibration.py       # Platt/Isotonic 校准
│   │   ├── element_consensus.py # ECS 计算
│   │   ├── disagreement.py      # CAMD 异议检测
│   │   ├── runtime_tracker.py   # 运行时性能追踪
│   │   └── weight_optimizer.py  # 权重优化
│   └── layer4/
│       ├── router.py            # 决策路由 (Tier 0-3)
│       └── threshold_optimizer.py  # 阈值优化
│
├── module2_extraction/
│   ├── models.py                # 提取数据模型
│   ├── exporter.py              # 导出入口
│   ├── new_orchestrator.py      # 主编排器
│   ├── session.py               # 会话状态
│   ├── engine/
│   │   ├── field_router.py      # 字段路由 (启发式)
│   │   ├── llm_extractor.py     # 双模型 LLM 提取
│   │   ├── llm_execution.py     # LLM 执行辅助
│   │   ├── table_reader.py      # 表格直读
│   │   ├── figure_reader.py     # 图表读取
│   │   ├── computation.py       # 效应量计算
│   │   ├── arbitrator.py        # 分歧仲裁
│   │   ├── layer1_extract.py    # 双模型提取层
│   │   ├── layer2_rules.py      # 规则验证层
│   │   ├── layer3_confidence.py # 置信聚合层
│   │   ├── routing_helpers.py   # 路由查找表
│   │   └── pdf_chunker.py       # 提取用分块
│   ├── validation/
│   │   ├── models.py            # 验证数据模型
│   │   ├── source_coherence.py  # V1: 源一致性
│   │   ├── rule_validator.py    # V2: 规则验证
│   │   ├── aggregator.py        # V3+最终聚合
│   │   └── numerical_coherence.py  # V4: 数值连贯
│   ├── compiler/
│   │   ├── compiler.py          # 模板编译管线
│   │   ├── scanner.py           # 结构扫描
│   │   ├── relationships.py     # 角色/关系推断
│   │   └── ai_enhancer.py       # 语义标签增强
│   ├── export/
│   │   ├── template_filler.py   # 模板填充导出
│   │   ├── excel.py             # 平面 Excel 导出 (置信度颜色编码)
│   │   ├── csv_export.py        # CSV 平面导出
│   │   ├── revman.py            # Cochrane RevMan XML 导出
│   │   ├── r_meta.py            # R metafor CSV 导出
│   │   └── effect_size_mapper.py # 效应量类型映射 (二分类/连续)
│   └── prompts.py               # Alpha/Beta prompt 模板
│
├── module3_quality/
│   ├── assessor.py              # RoBAssessor 编排器
│   ├── tools/
│   │   ├── base.py              # RoBToolSchema ABC
│   │   ├── rob2.py              # RoB 2 (RCT, 5 领域)
│   │   ├── robins_i.py          # ROBINS-I (观察性, 7 领域)
│   │   └── quadas2.py           # QUADAS-2 (诊断, 4 领域)
│   └── prompts/
│       └── rob_v1.py            # Schema 驱动 prompt 构建
│
├── evaluation/
│   ├── metrics.py               # 指标计算函数
│   ├── models.py                # ScreeningMetrics, AUROCResult, ...
│   ├── calibrator.py            # EvaluationRunner
│   ├── visualizer.py            # 可视化入口
│   ├── visualizer_charts.py     # Plotly 图表生成
│   └── visualizer_calibration.py  # 校准曲线 + RoB 热力图
│
└── api/
    ├── main.py / __init__.py    # FastAPI 应用创建
    ├── deps.py                  # 依赖注入
    ├── history_store.py         # JSON 文件存储
    ├── schemas.py               # 通用 Pydantic 模型
    ├── schemas_screening.py     # 筛选请求/响应
    ├── schemas_quality.py       # 质量请求/响应
    └── routes/
        ├── settings.py          # API 密钥 + 模型配置
        ├── screening.py         # 筛选端点
        ├── extraction_runner.py # 提取端点
        ├── quality.py           # RoB 评估端点
        ├── evaluation.py        # 评价端点
        ├── evaluation_viz.py    # 可视化端点
        └── history.py           # 历史管理端点

frontend/
├── package.json
├── vite.config.ts
├── index.html                   # PDF.js CDN, FontAwesome
├── src/
│   ├── main.ts                  # 应用入口
│   ├── App.vue                  # 根组件 (导航 + 全局提示)
│   ├── api.ts                   # Axios HTTP 客户端
│   ├── router/index.ts          # 11 路由定义
│   ├── stores/criteria.ts       # Pinia 标准状态
│   ├── composables/
│   │   ├── useBulkOperations.ts # 批量操作逻辑
│   │   └── useExtraction.ts     # SSE 流管理
│   ├── components/
│   │   ├── CriteriaSelector.vue # 标准选择下拉
│   │   ├── TagInput.vue         # 标签输入
│   │   ├── SchemaPreview.vue    # Schema 预览/编辑
│   │   ├── ExtractionDashboard.vue
│   │   ├── ExtractionPivotTable.vue
│   │   ├── PdfViewer.vue
│   │   └── SessionManager.vue
│   ├── views/
│   │   ├── HomeView.vue
│   │   ├── SettingsView.vue
│   │   ├── RetrievalView.vue
│   │   ├── CriteriaView.vue
│   │   ├── ScreeningLandingView.vue
│   │   ├── TAScreeningView.vue
│   │   ├── FTScreeningView.vue
│   │   ├── ExtractionView.vue
│   │   ├── ExtractionV2View.vue
│   │   ├── QualityView.vue
│   │   ├── EvaluationView.vue
│   │   └── HistoryView.vue
│   └── styles/main.css          # Aurora 毛玻璃主题

configs/models.yaml              # 唯一配置源
run.py                           # 开发启动器
pyproject.toml                   # 项目元数据 + 工具配置
```

---

## 附录 B: 缩写与术语表

| 缩写 | 全称 | 说明 |
|------|------|------|
| HCN | Hierarchical Consensus Network | 层级共识网络，本系统核心筛选架构 |
| CCA | Calibrated Confidence Aggregation | 校准置信度聚合 (Layer 3) |
| ECS | Element Consensus Score | 元素共识分，衡量 PICO 各元素的跨模型一致性 |
| CAMD | Confidence-Aware Minority Detection | 置信度感知少数检测 |
| PICO | Population, Intervention, Comparison, Outcome | 干预类系统评价标准框架 |
| RoB | Risk of Bias | 偏倚风险 |
| SR | Systematic Review | 系统评价 |
| T/A | Title/Abstract | 标题摘要筛选阶段 |
| FT | Full-Text | 全文筛选阶段 |
| SSE | Server-Sent Events | 服务器推送事件 |
| WSS@95 | Work Saved over Sampling at 95% recall | 95% 召回率下的工作节省指标 |
| AUROC | Area Under Receiver Operating Characteristic | ROC 曲线下面积 |
| ECE | Expected Calibration Error | 期望校准误差 |
| MoE | Mixture of Experts | 混合专家模型架构 |
