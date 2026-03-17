# Super Agent Platform — 架构与工作流说明

## 1. 系统架构概览

### 1.1 客户端层
| 组件 | 技术栈 | 端口 |
|------|--------|------|
| Web 前端 | React + Vite + TypeScript | :5173 |

前端通过 SSE (Server-Sent Events) 与后端通信，实现流式聊天响应。用户认证通过 Amazon Cognito SSO 或开发模式 Token 完成。

### 1.2 后端服务层
| 组件 | 技术栈 | 端口 |
|------|--------|------|
| API 服务 | Node.js + Fastify + TypeScript | :3000 |
| ORM | Prisma (PostgreSQL adapter) | — |
| 任务队列 | BullMQ (Redis) | — |

核心服务模块：
- Auth Middleware — JWT/Cognito 认证，开发模式支持 `Bearer dev` 跳过
- Chat Service — 会话管理、消息持久化、SSE 流式推送
- Strands Agent Service — AgentCore Runtime 调用、本地 Python 回退
- Skill Service — 技能加载与管理
- Business Scope Service — 业务域管理、Agent 分组
- Workspace Manager — 会话工作区隔离
- Agent Metrics Service — 调用指标统计

### 1.3 数据层
| 组件 | 用途 | 端口 |
|------|------|------|
| PostgreSQL | 业务数据持久化 (会话、消息、Agent、技能、工作流) | :8125 |
| Redis | BullMQ 任务队列、缓存 | :8124 |

### 1.4 AWS 云服务层

| 服务 | 用途 |
|------|------|
| Amazon Bedrock AgentCore | 8 个 Agent 运行时托管 (ARM64 容器) |
| Amazon Bedrock | Claude Sonnet 4 模型推理 (ConverseStream API) |
| Strands Agents SDK | Agent 框架 (系统提示 + 工具调用) |
| Amazon S3 | 技能文件存储 (`s3://super-agent-files/skills/`) |
| Amazon Cognito | 用户认证 (SSO) |
| AWS CodeBuild | Agent 容器镜像构建 (ARM64) |
| Amazon ECR | 容器镜像仓库 |
| Amazon CloudWatch | 日志收集 |
| AWS X-Ray | 分布式追踪 |
| OTEL (OpenTelemetry) | 可观测性数据采集 |

---

## 2. Agent 列表与技能映射

| Agent | 显示名 | 业务域 | 自动加载技能 (S3) |
|-------|--------|--------|-------------------|
| player-analyst | 玩家数据分析师 | Game Operations | game-player-retention, user-behavior-funnel |
| event-planner | 活动策划助手 | Game Operations | game-player-retention |
| content-localizer | 多语言内容生成器 | Global Marketing | global-marketing |
| ad-optimizer | 广告投放优化师 | Global Marketing | global-marketing, user-behavior-funnel |
| site-generator | AI建站助手 | AI Website Builder | — |
| seo-optimizer | SEO优化助手 | AI Website Builder | — |
| hr-assistant | HR Assistant | Human Resources | — |
| it-support | IT Support Agent | Information Technology | — |

---

## 3. 技能存储与加载机制

### 3.1 S3 存储结构

```
s3://super-agent-files/skills/
├── skills-index.json              # 技能清单 (name, folder, description)
├── game-player-retention/
│   └── SKILL.md                   # 玩家留存分析技能
├── user-behavior-funnel/
│   └── SKILL.md                   # 用户行为漏斗分析技能
├── global-marketing/
│   └── SKILL.md                   # 出海营销技能
├── app-builder/
│   └── SKILL.md                   # 应用构建技能
├── app-publisher/
│   ├── SKILL.md                   # 应用发布技能
│   └── scripts/publish-app.sh
└── skill-creator/
    └── SKILL.md                   # 技能创建器
```

### 3.2 加载机制

```
Agent 冷启动
  │
  ├─ 1. 读取 RELEVANT_SKILLS 列表 (编译时确定)
  ├─ 2. 从 S3 逐个加载 SKILL.md → 缓存到内存
  ├─ 3. 将技能内容注入 system_prompt (<skill> 标签包裹)
  └─ 4. 初始化 Strands Agent (model + system_prompt + tools)

Agent 运行时 (热启动)
  │
  ├─ 技能已在 system_prompt 中，无需重新加载
  └─ 可通过 list_skills() / load_skill() 工具按需加载额外技能
```

更新技能只需：
1. 编辑 `backend/skills/{name}/SKILL.md`
2. 运行 `python3 backend/agentcore-deploy/upload_skills_s3.py`
3. 无需重新部署 Agent — 下次冷启动自动加载最新版本

---

## 4. 核心工作流

### 4.1 用户聊天流程

```
用户 (浏览器)
  │
  │  POST /api/chat/sessions/:id/stream
  │  Headers: Authorization: Bearer <token>
  │  Body: { message, business_scope_id, agent_id? }
  ▼
Auth Middleware
  │  验证 JWT / Cognito Token / dev Token
  ▼
Chat Service (streamChat)
  │  1. 加载 Business Scope + Agents + Skills
  │  2. 创建/恢复会话
  │  3. 持久化用户消息到 PostgreSQL
  │  4. 设置 SSE 响应头
  ▼
Strands Agent Service (runConversation)
  │  1. 加载 runtime_arns.json → 查找 Agent ARN
  │  2. 加载最近 20 条聊天历史 (PostgreSQL)
  │  3. 构建 payload: { prompt, history }
  ▼
InvokeAgentRuntimeCommand (AWS SDK)
  │  发送到 AgentCore Runtime
  ▼
AgentCore Runtime (云端容器)
  │  1. [冷启动] 从 S3 加载技能 → 注入 system_prompt
  │  2. [冷启动] 初始化 Strands Agent + BedrockModel
  │  3. 构建上下文提示 (含历史对话)
  │  4. 调用 Claude Sonnet 4 (ConverseStream)
  │  5. [可选] Agent 调用 list_skills/load_skill 工具
  │  6. 返回 { result: "..." }
  ▼
Chat Service
  │  1. 解析响应 → 生成 SSE 事件
  │  2. 持久化 AI 消息到 PostgreSQL
  │  3. 记录 Agent 指标
  │  4. 发送 [DONE] 结束 SSE 流
  ▼
用户 (浏览器)
     实时显示流式响应
```

### 4.2 Agent 部署流程

```
开发者
  │
  │  python3 deploy_cloud.py
  ▼
deploy_cloud.py
  │  1. 为每个 Agent 生成 Python 入口文件
  │     - 嵌入 system_prompt + RELEVANT_SKILLS 列表
  │     - 包含 list_skills/load_skill Strands 工具
  │  2. 生成 .bedrock_agentcore.yaml 配置
  │  3. 生成 requirements.txt
  ▼
agentcore deploy -a <name> (× 8)
  │  1. 打包源码 → 上传 S3
  │  2. 触发 CodeBuild (ARM64)
  │  3. 构建 Docker 镜像 → 推送 ECR
  │  4. 创建/更新 AgentCore Runtime
  │  5. 配置 Observability (CloudWatch + X-Ray)
  │  6. 等待 Endpoint READY
  ▼
runtime_arns.json
     保存 Agent Name → Runtime ARN 映射
```

### 4.3 技能更新流程

```
开发者
  │
  │  编辑 backend/skills/{name}/SKILL.md
  ▼
python3 upload_skills_s3.py
  │  1. 遍历 backend/skills/ 目录
  │  2. 上传每个 SKILL.md 到 S3
  │  3. 更新 skills-index.json 清单
  ▼
S3 (super-agent-files/skills/)
  │  技能文件已更新
  ▼
下次 Agent 冷启动时
     自动从 S3 加载最新技能内容
```

---

## 5. 可观测性

| 数据类型 | 目标 | 说明 |
|----------|------|------|
| 运行时日志 | CloudWatch Logs | `/aws/bedrock-agentcore/runtimes/{agent}-DEFAULT` |
| OTEL Spans | CloudWatch Logs | `/aws/spans` |
| 分布式追踪 | X-Ray | Transaction Search 已启用，100% 采样率 |
| GenAI 仪表盘 | CloudWatch | `console.aws.amazon.com/cloudwatch/home#gen-ai-observability/agent-core` |

---

## 6. 关键配置

| 配置项 | 值 |
|--------|-----|
| AWS Account | 632930644527 |
| Region | us-east-1 |
| IAM Role | AgentCoreRuntimeRole |
| Model | us.anthropic.claude-sonnet-4-20250514-v1:0 |
| S3 Bucket | super-agent-files |
| S3 Skills Prefix | skills/ |
| Cognito User Pool | us-east-1_18QE4Fyfz |
