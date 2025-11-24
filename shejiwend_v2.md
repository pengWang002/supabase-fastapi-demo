she# 设计文档 v2：Bytebase 风格登录页（GitHub Pages）+ Supabase + Python BFF

> 本文为 v2，不覆盖 `shejiwend.md`。在保持 Supabase 技术栈的前提下，补充更细的实现细节、配置清单与风险对策。

## 1. 目标与约束
- 前端：GitHub Pages 提供 Bytebase 风格登录体验，支持 GitHub/Google 登录。
- 后端：Python（FastAPI BFF）+ Supabase（Auth + Postgres），不使用 SQLite。
- 能力：第三方登录获取用户信息/头像，提供基础用户管理接口。
- 时限：24 小时内可用版本，首要保证 OAuth 通路、会话与用户表落地。

## 2. 架构与数据流
- 前端（静态，GitHub Pages）：
  - 使用 `@supabase/supabase-js` 发起 OAuth，管理 session。
  - UI：Bytebase 风格左右分栏/渐变背景/卡片，明显的加载与错误反馈。
- Supabase（托管）：
  - Auth（GoTrue）：GitHub/Google OAuth，state/PKCE、会话、刷新。
  - Postgres：`profiles` 表存用户资料，可选 RLS。
- Python BFF（FastAPI，云主机）：
  - 校验 Supabase JWT（JWKS）。
  - `supabase-py` 读写 `profiles`，对前端暴露简化 API。
- 域名与回调：
  - 前端：`https://<user>.github.io/<repo>/`
  - OAuth Redirect（Supabase 托管）：`https://<project>.supabase.co/auth/v1/callback?redirect_to=https://<user>.github.io/<repo>/callback.html`
  - 后端：`https://<backend-domain>`；CORS 允许 GitHub Pages 域。

## 3. 数据模型（Supabase Postgres）
表 `profiles`
| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | uuid | PK，默认 `uuid_generate_v4()` | 对齐 Supabase Auth `user.id` |
| provider | text | not null | `github`/`google` |
| provider_id | text | not null, unique | 第三方用户 ID |
| email | text | unique | GitHub 无公开邮箱时允许空，后续补采 |
| display_name | text |  | 显示名 |
| avatar_url | text |  | 头像 |
| created_at | timestamptz | default now() | 创建时间 |
| last_sign_in_at | timestamptz |  | 最近登录 |
索引：`provider_id` 唯一；`provider`、`email` 索引。  
RLS（上线可开启）：策略 `auth.uid() = id` 允许用户读/写自身；管理端可通过 service role。

## 4. API 设计（FastAPI BFF）
- `GET /health`：健康检查。
- `GET /users/me`：返回当前用户资料；若无记录则基于 Token 信息 upsert 后返回。
- `PUT /users/me`：更新 `display_name`、`avatar_url`。
- `GET /users`：列表（分页）；需登录，默认仅返回基础字段，可在 service role 下扩展。
- 中间件：解析 `Authorization: Bearer <token>`，用 Supabase JWKS 校验签名/过期，取 `sub`、`email`、`app_metadata.provider`。
- 错误：401（未登录/过期）、403（无权限）、4xx（参数）、5xx（内部）。统一 JSON `{error, message}`。

## 5. 前端页面
- `index.html`：登录页，左右分栏 + 登录卡片（GitHub/Google 按钮），显示加载/错误。
- `callback.html`：处理 Supabase 重定向，`supabase-js` 自动存 session，显示成功/失败/重试。
- `dashboard.html`（可选）：展示用户信息/头像，调用 `/users/me`，提供更新资料、登出。
- 交互：
  - 登录：`supabase.auth.signInWithOAuth({ provider, options: { redirectTo: <callback> }})`
  - 登出：`supabase.auth.signOut()`
  - Session 获取：`supabase.auth.getSession()`；将 access_token 作为 Bearer 调用 BFF。
- 安全：默认使用 `supabase-js` 存储；若担心 XSS，可配置为 sessionStorage。

## 6. 配置清单
- Supabase 控制台：
  - OAuth Provider：GitHub/Google 启用；Callback：`https://<project>.supabase.co/auth/v1/callback`
  - `redirectTo`：前端回调 URL（GitHub Pages）。
  - 数据库：执行建表 SQL，确保扩展 `uuid-ossp` 可用。
- 后端环境变量：
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`（前端可用，后端仅读）
  - `SUPABASE_SERVICE_ROLE_KEY`（后端安全存储，用于 upsert/管理）
  - `SUPABASE_JWT_ISS`、`SUPABASE_JWT_AUD`（通常默认值）
  - `PORT`、`ALLOWED_ORIGINS`（CORS）
- 部署：
  - 前端：推送静态文件到仓库，开启 GitHub Pages。
  - 后端：Render/Fly.io/Vercel Functions 任一；配置 HTTPS、CORS、健康检查。

## 7. 安全与合规
- OAuth：使用 Supabase 默认 state/PKCE，避免自管 client secret。
- Token：只接受 Supabase access token；短有效期 + refresh 由 supabase-js 管理；后端无状态。
- CORS：仅允许 GitHub Pages 域；限制方法/头；开启 HTTPS。
- 速率限制：在 BFF 层可加入简单 rate limit 中间件。
- 日志：避免打印 Token；错误日志含请求 ID。

## 8. 交付计划（24h）
- 0-2h：Supabase 项目/OAuth 配置；建表；前端模板 + supabase-js 接入。
- 2-6h：FastAPI 脚手架，JWT 中间件，`/health`、`/users/me`。
- 6-10h：`/users`、`PUT /users/me`，资料 upsert；联调前端。
- 10-14h：UI 打磨（Bytebase 风格）、加载/错误态、空态；CORS 调试。
- 14-24h：部署后端 + Pages，真实 OAuth 验证；冒烟测试、文档更新。

## 9. 测试要点
- GitHub/Google 登录全链路（授权 -> 回调 -> 会话 -> API）。
- Token 过期/登出后访问受限接口返回 401。
- GitHub 无公开邮箱时的兜底提示/补采。
- 头像/昵称更新流程；列表分页。
- CORS、HTTPS、混合内容检查。
