# 设计文档：Bytebase 风格登录页（GitHub Pages）+ Supabase + Python BFF

## 1. 目标与约束
- 前端：GitHub Pages 可访问的 Bytebase 风格登录页，支持 GitHub/Google 登录。
- 后端：使用 **Python + Supabase** 实现用户登录/管理接口（BFF 模式），不使用 SQLite。
- 第三方登录：GitHub、Google OAuth；需获取用户信息与头像；提供基础用户管理接口。
- 时限：24 小时内完成可用版本。

## 2. 架构总览
- 前端（静态）：GitHub Pages，纯静态 HTML/CSS/JS。负责 UI、发起 OAuth、持有会话、调用后端 API。
- Supabase：
  - Auth（GoTrue）：托管 OAuth（GitHub/Google），颁发会话/JWT。
  - Postgres：存储用户资料表 `profiles`；可选行级安全（RLS）。
  - Realtime/Storage 暂不使用。
- Python BFF（FastAPI，部署在 Render/Fly.io/Vercel Functions/自选主机）：
  - 校验 Supabase JWT（通过 Supabase JWK）。
  - 衔接 Supabase PostgREST 读写用户资料（`supabase-py` SDK）。
  - 提供用户管理接口（当前用户信息、更新资料、管理员查询列表）。
- 域名与回调：
  - 前端域：`https://<user>.github.io/<repo>/`。
  - Supabase 项目域：`https://<project>.supabase.co`。
  - OAuth Redirect URI：`https://<project>.supabase.co/auth/v1/callback`（Supabase Auth 托管），前端 `redirectTo=https://<user>.github.io/<repo>/callback.html`。
  - 后端 API 域：`https://<your-backend-domain>`，前端通过 HTTPS 调用。

## 3. 技术栈与理由
- 前端：原生 HTML/CSS/JS + `@supabase/supabase-js`（简化 OAuth 与会话管理）；Axios/Fallback fetch 调用后端。
- UI 风格：参考 Bytebase 登录（左右分栏、渐变背景/插画、品牌色、突出的登录卡片、明显的错误/加载状态）。
- 后端：FastAPI（Python），`supabase-py` 访问 PostgREST，`python-jose`/`PyJWT` 验证 Supabase JWT。
- 认证：使用 Supabase Auth 托管 GitHub/Google OAuth，支持 PKCE，内置会话/刷新。
- 数据：Supabase Postgres（表 `profiles`）；不使用 SQLite。
- 部署：前端 GitHub Pages；后端可选 Render/Fly.io/Vercel；Supabase 已托管。

## 4. 功能拆分
### 前端
- 登录页：GitHub/Google 按钮，点击触发 `supabase.auth.signInWithOAuth`（provider + redirectTo）。
- 回调页：解析 Supabase 重定向后的 `access_token`/`refresh_token`（supabase-js 自动处理）；显示状态、错误重试。
- 登录态展示：显示头像、昵称、邮箱；提供 Logout，状态指示（加载、已登录、未登录、错误）。
- 管理视图（简版）：调用后端 `/users/me`、`/users`，显示列表、空态/错误态。
- 安全：Token 存储在 `supabase-js` 内置存储（可选 localStorage）；前端仅通过 `Authorization: Bearer <access_token>` 调后端。

### 后端（FastAPI BFF）
- 中间件：验证 `Authorization: Bearer <token>`，使用 Supabase JWK 校验签名/过期，获取 `sub`、`email`。
- DB 访问：`supabase-py` 调用 PostgREST，对 `profiles` 表做 upsert/查询。
- API 设计：
  - `GET /health`：健康检查。
  - `GET /users/me`：返回当前用户资料（从 `profiles` 查询；若不存在则根据 Auth 信息补写）。
  - `PUT /users/me`：更新 `display_name`/`avatar_url`。
  - `GET /users`：简化管理；默认限制分页+需要登录（可加 admin flag）。
- 错误处理：统一返回 JSON，含错误码/提示；支持未授权/过期 Token 提示重新登录。

## 5. 数据模型（Supabase Postgres）
表名：`profiles`
| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | uuid | PK，默认 `uuid_generate_v4()` | 与 Supabase Auth `user.id` 对齐 |
| provider | text | not null | `github`/`google` |
| provider_id | text | not null | 第三方平台用户 ID |
| email | text | unique, not null | 允许空时从 OAuth `user:email` 获取或回退前端补采 |
| display_name | text |  | 显示名称 |
| avatar_url | text |  | 头像 |
| created_at | timestamptz | default now() | 创建时间 |
| last_sign_in_at | timestamptz |  | 最近登录 |
索引：`provider_id` 唯一索引；`provider` + `email` 索引。
RLS（可选上线前开启）：`auth.uid() = id` 允许用户读写自身，管理员角色可读全表。

## 6. OAuth/会话流程（Supabase 托管）
1) 前端调用 `supabase.auth.signInWithOAuth({ provider: 'github'|'google', options: { redirectTo: <front-callback> }})`；Supabase 自动生成 `state`/PKCE。  
2) 用户完成授权 -> Supabase `auth/v1/callback` -> 重定向回前端 `callback.html`，带访问令牌信息；`supabase-js` 自动存储会话。  
3) 前端获取当前 session（`supabase.auth.getSession()`），拿到 access_token。  
4) 前端请求后端 API，附带 `Authorization: Bearer <access_token>`。  
5) 后端校验 JWK（Supabase JWKS endpoint），验证签名/过期，提取 `sub`/`email`。  
6) 后端用 `sub` 作为 `profiles.id` 进行 upsert/查询，返回用户数据。  
7) Logout：前端调用 `supabase.auth.signOut()`，后端无状态。

## 7. CORS/安全
- 全站 HTTPS；GitHub Pages/后端/Supabase 域名均为 HTTPS。
- CORS：后端允许源 `https://<user>.github.io`；限制方法/头。
- OAuth：使用 Supabase 默认 state/PKCE；不自管 client secret。
- Token：使用 Supabase 短期 access token + refresh token；后端仅接受 access token；不自生成 JWT。
- 存储：避免手动 localStorage；使用 `supabase-js` 默认存储（可配置 sessionStorage）。
- 速率限制：后端可选简单 rate limit（如 Starlette middleware）。

## 8. 部署与配置
- Supabase 项目：创建 OAuth Provider（GitHub/Google），配置 redirect：`https://<project>.supabase.co/auth/v1/callback` 与 `redirectTo=https://<user>.github.io/<repo>/callback.html`。
- 环境变量（后端）：`SUPABASE_URL`、`SUPABASE_ANON_KEY`（读）、`SUPABASE_SERVICE_ROLE_KEY`（仅内部 upsert/管理）、`JWT_AUDIENCE/ISSUER`（Supabase 默认值）。
- GitHub Pages：构建静态文件放仓库根或 `docs/`；设置 Pages 来源。
- 后端部署：Render/Fly.io 等，暴露 `https://<backend-domain>`；配置 CORS、健康检查。

## 9. 开发与交付里程碑（24h 内）
- T0-T2h：初始化前端模板（登录页/回调页）、接入 `supabase-js`；建 Supabase 项目与 OAuth 配置。
- T2h-T6h：FastAPI BFF 脚手架，JWT 校验中间件；实现 `/health`、`/users/me`。
- T6h-T10h：`profiles` 表建模 + upsert；实现 `/users` 列表、`/users/me` 更新；联调前端。
- T10h-T14h：UI 打磨（Bytebase 风格）、加载/错误态、空态；CORS 调试。
- T14h-T24h：部署后端、开通 Pages，真实 OAuth 回调验证；冒烟测试，补充 README/环境变量说明。

## 10. 测试要点
- GitHub/Google 登录全链路（授权 -> 回调 -> 会话 -> API）。
- Token 过期/登出后 API 拒绝访问。
- 邮箱缺失场景：GitHub 无公开邮箱时的兜底采集/提示。
- 头像/昵称更新同步（前端调用 `PUT /users/me`）。
- CORS 与 HTTPS：确保生产域名下无混合内容/跨域报错。
