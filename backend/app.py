import os
from functools import lru_cache
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from jose.exceptions import JWTError
from pydantic import BaseModel
import uvicorn
from supabase import Client, create_client
from fastapi.logger import logger

# 自动加载 .env，便于本地开发
load_dotenv()


class Settings(BaseModel):
  supabase_url: str
  supabase_anon_key: str
  supabase_service_role_key: str
  jwt_audience: str = "authenticated"
  jwt_issuer: Optional[str] = None
  jwks_url: Optional[str] = None
  jwt_secret: Optional[str] = None
  allowed_origins: list[str] = []


@lru_cache()
def get_settings() -> Settings:
  supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
  if not supabase_url:
    raise RuntimeError("缺少 SUPABASE_URL 环境变量")

  issuer = os.getenv("SUPABASE_JWT_ISS") or f"{supabase_url}/auth/v1"
  jwks_url = os.getenv("SUPABASE_JWKS_URL") or f"{supabase_url}/auth/v1/keys"
  allowed = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

  return Settings(
    supabase_url=supabase_url,
    supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
    supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
    jwt_audience=os.getenv("SUPABASE_JWT_AUD", "authenticated"),
    jwt_issuer=issuer,
    jwks_url=jwks_url,
    jwt_secret=os.getenv("SUPABASE_JWT_SECRET"),
    allowed_origins=allowed,
  )


settings = get_settings()
app = FastAPI(title="Supabase BFF", version="0.1.0")

if settings.allowed_origins:
  app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
  )


def get_supabase() -> Client:
  if not settings.supabase_service_role_key:
    raise HTTPException(status_code=500, detail="缺少 SUPABASE_SERVICE_ROLE_KEY")
  return create_client(settings.supabase_url, settings.supabase_service_role_key)


_jwks_cache: Optional[Dict[str, Any]] = None


async def fetch_jwks() -> Dict[str, Any]:
  """
  拉取 JWKS，兼容不同路径：
  1) 显式 SUPABASE_JWKS_URL（默认 <url>/auth/v1/keys）
  2) /auth/v1/jwks
  3) /.well-known/jwks.json
  """
  candidates = [
    settings.jwks_url,
    f"{settings.supabase_url}/auth/v1/.well-known/jwks.json",
    f"{settings.supabase_url}/auth/v1/jwks",
    f"{settings.supabase_url}/.well-known/jwks.json",
  ]
  headers = {"apikey": settings.supabase_anon_key} if settings.supabase_anon_key else {}
  last_error = None
  async with httpx.AsyncClient(timeout=5.0) as client:
    for url in candidates:
      try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        logger.info(f"JWKS fetched from {url}")
        return resp.json()
      except httpx.HTTPStatusError as exc:
        last_error = exc
        logger.warning(f"JWKS fetch failed from {url}: {exc}")
        # 继续尝试下一个候选
        continue
    if last_error:
      raise last_error
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无法获取 JWKS")


async def get_jwk(kid: str) -> Dict[str, Any]:
  global _jwks_cache
  if not kid:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token header 缺少 kid")
  if _jwks_cache:
    match = next((key for key in _jwks_cache.get("keys", []) if key.get("kid") == kid), None)
    if match:
      return match
  try:
    _jwks_cache = await fetch_jwks()
  except httpx.HTTPError as exc:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED, detail=f"获取 JWKS 失败: {exc}"
    ) from exc
  match = next((key for key in _jwks_cache.get("keys", []) if key.get("kid") == kid), None)
  if not match:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的 kid")
  return match


class AuthedUser(BaseModel):
  sub: str
  email: Optional[str] = None
  provider: Optional[str] = None
  raw: Dict[str, Any]


async def get_current_user(authorization: str = Header(default=None)) -> AuthedUser:
  if not authorization or not authorization.lower().startswith("bearer "):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 Bearer Token")
  token = authorization.split(" ", 1)[1]
  try:
    header = jwt.get_unverified_header(token)
    if settings.jwt_secret:
      alg = header.get("alg") or "HS256"
      claims = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[alg],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
      )
    else:
      key = await get_jwk(header.get("kid"))
      claims = jwt.decode(
        token,
        key,
        algorithms=[key.get("alg", "RS256")],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
      )
  except (JWTError, httpx.HTTPError) as exc:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token 无效: {exc}") from exc

  return AuthedUser(
    sub=claims.get("sub"),
    email=claims.get("email"),
    provider=claims.get("app_metadata", {}).get("provider"),
    raw=claims,
  )


class ProfileUpdate(BaseModel):
  display_name: Optional[str] = None
  avatar_url: Optional[str] = None


def profile_payload(user: AuthedUser) -> Dict[str, Any]:
  meta = user.raw.get("user_metadata", {}) if user.raw else {}
  display_name = (
    meta.get("full_name")
    or meta.get("name")
    or meta.get("user_name")
    or user.email
  )
  avatar = meta.get("avatar_url") or meta.get("picture")
  return {
    "id": user.sub,
    "provider": user.provider or "unknown",
    "provider_id": user.raw.get("user_metadata", {}).get("sub") or user.sub,
    "email": user.email,
    "display_name": display_name,
    "avatar_url": avatar,
  }


def upsert_profile(client: Client, user: AuthedUser) -> Dict[str, Any]:
  data = profile_payload(user)
  res = client.table("profiles").upsert(data, on_conflict="id").execute()
  # Supabase Python returns the inserted/updated rows by default (return=representation)
  return res.data[0] if res.data else data


def get_profile(client: Client, user: AuthedUser) -> Dict[str, Any]:
  res = client.table("profiles").select("*").eq("id", user.sub).limit(1).execute()
  if res.data:
    return res.data[0]
  return upsert_profile(client, user)


@app.get("/health")
async def health():
  return {"status": "ok"}


@app.get("/users/me")
async def me(current: AuthedUser = Depends(get_current_user)):
  client = get_supabase()
  profile = get_profile(client, current)
  return profile


@app.put("/users/me")
async def update_me(payload: ProfileUpdate, current: AuthedUser = Depends(get_current_user)):
  client = get_supabase()
  updates = {k: v for k, v in payload.dict().items() if v is not None}
  if not updates:
    return get_profile(client, current)
  res = client.table("profiles").update(updates).eq("id", current.sub).execute()
  if res.data:
    return res.data[0]
  # 如果未返回数据（某些配置下 return=minimal），再查一次
  refreshed = client.table("profiles").select("*").eq("id", current.sub).limit(1).execute()
  if not refreshed.data:
    raise HTTPException(status_code=404, detail="未找到用户")
  return refreshed.data[0]


@app.get("/users")
async def list_users(
  limit: int = 20,
  offset: int = 0,
  current: AuthedUser = Depends(get_current_user),
):
  client = get_supabase()
  res = client.table("profiles").select("*").range(offset, offset + limit - 1).execute()
  return {"items": res.data, "count": len(res.data)}


def main():
  host = os.getenv("APP_HOST", "0.0.0.0")
  port = int(os.getenv("APP_PORT", "8000"))
  reload = os.getenv("APP_RELOAD", "false").lower() in {"1", "true", "yes", "y"}
  uvicorn.run(app, host=host, port=port, reload=reload)


if __name__ == "__main__":
  main()
