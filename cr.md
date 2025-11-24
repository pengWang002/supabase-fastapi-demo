# CR - 需求对比与设计评估

## 发现的问题（按严重度排序）
1. [阻塞] 未采用 Supabase：需求要求“通过 python + supabase 实现后端用户登录/管理”，`shejiwend.md` 选用 FastAPI + SQLite + Render/Fly.io，完全绕过 Supabase Auth/DB/Edge Functions，也未规划 Supabase 部署与密钥配置，无法满足硬性约束。
2. [阻塞] 前后端域与 OAuth 回调未落地：需求是 GitHub Pages 前端 + Supabase 后端；设计只给了云主机选项，未绑定固定域名/回调地址，缺少 CORS/HTTPS/Redirect URI 规范，GitHub/Google 可能拒绝回调或产生跨域失败。
3. [高] Bytebase 登录体验缺失：需求明确“bytebase 的登录页面”，设计仅笼统提到 UI/UX，未定义视觉风格、左右分栏、状态反馈（加载/错误）、注销/会话指示等体验要素。
4. [高] OAuth 安全细节不全：`/auth/{provider}/callback` 流程未提到 `state`/PKCE 防 CSRF；JWT 未说明过期/刷新/吊销策略；第三方 Token 的存储/清理缺失，存在重放与长期有效风险。
5. [中] 数据模型与需求不吻合：需求强调头像和用户信息管理，设计中邮箱必填且唯一，但 GitHub 可能无公开邮箱（需要 `user:email` 额外调用或兜底表单）；也未与 Supabase 用户表/行级安全策略对齐，后续迁移成本高。
6. [中] 前端回调与 Token 处理缺口：GitHub Pages 的回调页需要处理错误码/过期提示、Token 存储安全（localStorage 易受 XSS）、注销与 Session 失效，设计未覆盖。
7. [低] 交付节奏未呼应“24 小时内 + AI”要求：缺少压缩时间线的开发/测试/发布计划和 AI 辅助策略，影响可交付性。

## 优化建议
- 选型：迁移到 Supabase（Auth + Postgres + Edge Functions），用 Python（supabase-py/FastAPI）封装业务或直接使用 Supabase OAuth Provider，消除与需求的技术栈偏差。
- 部署/域名：明确前端 `https://<user>.github.io/<repo>`，后端使用 Supabase 默认域或自定义域；在 GitHub/Google 控制台登记精确 redirect URI，配置 CORS/HTTPS。
- 安全：在 OAuth 引入 `state`/PKCE；JWT 设置短有效期并配合 Refresh Token 或使用 Supabase Session；回调页处理错误场景并提供重试/注销。
- 体验：补充 Bytebase 风格界面（品牌色、左右分栏/插画/渐变背景）、加载与错误提示、登录态指示与 Logout；为管理接口增加空态/失败提示。
- 数据：处理邮箱缺失场景（fallback 表单或使用 provider_id 作为唯一键）；头像占位与更新同步；若使用 Supabase，利用其 RLS/Policy 做最小权限管理。
