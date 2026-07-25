# TeamSync — 项目文档

## 项目概述

- **项目名称**：TeamSync
- **项目目标**：将产品/技术团队的会议记录，通过 AI 自动提取为可直接导入 Jira 的结构化任务（JSON/CSV）
- **目标用户**：Scrum Master、Tech Lead、产品经理
- **运行平台**：本地浏览器（Streamlit Web 应用）

---

## 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 应用框架 | Streamlit | Python 写 Web UI，无需前端代码 |
| AI 模型 | DeepSeek V4 | 通过 OpenAI 兼容 SDK 调用 |
| 模型选项 | `deepseek-v4-flash`（默认）、`deepseek-v4-pro` | Flash 快且便宜，Pro 质量更高 |
| API 调用 | openai SDK | base_url 指向 `https://api.deepseek.com` |
| 数据处理 | pandas | 任务表格展示与 CSV 导出 |
| 环境变量 | python-dotenv | 从 `.env` 加载 API Key |

---

## 项目目录结构

```
TeamSync/
├── CLAUDE.md              # 项目文档（本文件）
├── app.py                 # Streamlit 主应用（UI + 交互逻辑）
├── llm_client.py          # DeepSeek API 调用封装 + JSON 解析
├── prompt_engine.py       # System Prompt 模板 + 示例会议记录
├── requirements.txt       # Python 依赖
├── .env.example           # API Key 配置模板
└── .gitignore
```

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `app.py` | Streamlit UI：侧边栏配置、会议记录输入、任务表格展示、导出 JSON/CSV |
| `llm_client.py` | 封装 DeepSeek API 调用：JSON 提取（3 级容错）、自动重试（最多 2 次）、错误分类（Key 无效/网络异常/API 错误） |
| `prompt_engine.py` | 业务 Prompt 模板：System Prompt（任务提取规则）、示例会议记录、`build_user_prompt()` 拼接函数 |
| `requirements.txt` | 4 个依赖：`streamlit`、`openai`、`pandas`、`python-dotenv` |
| `.env.example` | API Key 模板，复制为 `.env` 后填写真实 Key |

---

## 核心 API 参数

调用 DeepSeek V4 时的关键参数（见 `llm_client.py:88-98`）：

```python
client.chat.completions.create(
    model="deepseek-v4-flash",
    max_tokens=4096,
    temperature=0.1,                              # 低温保证输出稳定
    extra_body={"thinking": {"type": "disabled"}}, # 必须关闭思考模式，否则输出含推理链导致 JSON 解析失败
    messages=[...],
)
```

> **重要：** V4 模型默认开启 thinking 模式，不关闭会导致返回内容包含推理过程，JSON 解析失败。

---

## JSON 提取容错机制

`llm_client.py:_extract_json()` 按 3 级优先级尝试：

1. 直接 `json.loads()` 解析全文
2. 正则提取 ` ```json ... ``` ` 代码块后解析
3. 正则匹配 `[...]` 数组后解析

3 级都失败则抛出 `ValueError`，触发重试（最多 2 次）。重试时会在 user prompt 末尾追加格式纠正提示。

---

## 数据流

```
用户粘贴会议记录
  → app.py 点击「生成任务」
  → llm_client.generate_tasks() 拼接 Prompt + 调用 DeepSeek API
  → _extract_json() 提取 JSON 数组
  → 返回 (tasks, metadata)
  → app.py 展示可编辑表格
  → 用户编辑后导出 JSON / CSV
```

---

## 输出数据结构

```json
[
  {
    "title": "以动词开头的任务标题",
    "description": "包含背景、完成标准、关键讨论点",
    "assignee": "负责人姓名 或「待认领」",
    "priority": "P0 | P1 | P2",
    "due_date": "YYYY-MM-DD",
    "confirmation_notes": "待确认项备注，无则为空字符串"
  }
]
```

---

## 优先级规则

| 级别 | 含义 | 示例 |
|------|------|------|
| P0 | 阻塞上线、造成资损 | 支付接口超时、安全漏洞 |
| P1 | 本迭代核心需求 | 新功能开发、接口文档 |
| P2 | 优化类、非阻塞 | 性能优化、代码重构 |

---

## 开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 启动应用（本地浏览器访问 http://localhost:8501）
streamlit run app.py

# 配置 API Key（二选一）
# 方式一：创建 .env 文件
echo DEEPSEEK_API_KEY=sk-你的key > .env

# 方式二：启动后在侧边栏输入
```

---

## 环境注意事项

- Python 版本 ≥ 3.10
- DeepSeek API Key 从 https://platform.deepseek.com/api_keys 获取
- API Key 存储在 `.env` 文件中，已加入 `.gitignore`，不会被提交到 Git
- 会议记录会发送至 DeepSeek 服务器，请勿包含敏感信息
- 当前为 MVP 版本，无数据库、无用户系统、无历史记录
