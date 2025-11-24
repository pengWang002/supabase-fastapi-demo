# Bytebase 风格登录（Supabase + Python BFF + GitHub Pages）

本仓库包含：
- 前端静态页（`frontend/`）：使用 `@supabase/supabase-js` 触发 GitHub/Google 登录，运行于本地或 GitHub Pages。
- 后端 BFF（`backend/`）：FastAPI 校验 Supabase JWT，读写 Supabase Postgres 的 `profiles` 表。
- 设计文档：`shejiwend.md`（v1）、`shejiwend_v2.md`（v2），CR：`cr.md`，需求：`xuqiu.md`。

## 环境准备
- Python 3.10+
- Node.js（用于本地静态文件服务，可用 `python -m http.server` 替代）
- Supabase 项目（需开启 GitHub/Google OAuth）

## 本地开发（先跑通）
1) 创建 Supabase 项目  
   - 在 Supabase 控制台启用 GitHub/Google OAuth，Callback 使用默认 `https://<project>.supabase.co/auth/v1/callback`。  
   - 临时 redirectTo：`http://localhost:3000/callback.html`。上线前换成 GitHub Pages 域。  
   - 创建表 `profiles`（见 `backend/app.py` 中的表结构注释或 `shejiwend_v2.md`）。

2) 前端本地起服务  
   ```bash
   cd frontend
   cp config.example.js config.js  # 填写 SUPABASE_URL、SUPABASE_ANON_KEY、BACKEND_URL（本地 http://localhost:8000）
   npx serve . -l 3000  # 或 python -m http.server 3000
   ```
   访问 `http://localhost:3000`。

3) 后端本地运行  
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env  # 填写 SUPABASE_URL、SUPABASE_ANON_KEY、SUPABASE_SERVICE_ROLE_KEY、ALLOWED_ORIGINS=http://localhost:3000
   uvicorn app:app --reload --port 8000
   ```

4) 联调路径  
   - 打开前端 -> 点击 GitHub/Google 登录 -> Supabase 授权 -> 回到本地 `callback.html`。  
   - 前端用 Supabase access token 调后端 `GET /users/me`，应返回/创建用户资料。

## 上线部署（本地验证后）
- 前端：将 `frontend/` 内容推到仓库根或 `docs/`，开启 GitHub Pages，域名 `https://<user>.github.io/<repo>/`。
- Supabase：将 redirectTo 改为 Pages 域：`https://<user>.github.io/<repo>/callback.html`；Callback 仍为默认 Supabase 域。
- 后端：部署 FastAPI 到云（Render/Fly.io 等），配置环境变量与 CORS（允许 Pages 域），更新前端 `config.js` 中 `BACKEND_URL` 为云端域名。

## 关键路径/文件
- 前端：`frontend/index.html`（登录页）、`frontend/callback.html`（回调）、`frontend/main.js`、`frontend/styles.css`、`frontend/config.js`（用户自填）。
- 后端：`backend/app.py`（API）、`backend/requirements.txt`、`backend/.env.example`。

## 测试要点
- GitHub/Google OAuth 全链路；Token 过期后应返回 401。
- GitHub 无公开邮箱时的提示/补采。
- `/users/me` upsert/返回数据；`/users` 分页。
- CORS/HTTPS 配置是否正确。
