(function () {
  const statusBar = document.getElementById("statusBar");
  const loginCard = document.getElementById("loginCard");
  const profileCard = document.getElementById("profileCard");
  const providerTag = document.getElementById("providerTag");
  const displayNameEl = document.getElementById("displayName");
  const emailEl = document.getElementById("email");
  const avatarEl = document.getElementById("avatar");
  const inputDisplayName = document.getElementById("inputDisplayName");
  const inputAvatarUrl = document.getElementById("inputAvatarUrl");
  const refreshBtn = document.getElementById("refreshBtn");
  const logoutBtn = document.getElementById("logoutBtn");
  const form = document.getElementById("profileForm");
  const loginButtons = document.querySelectorAll("[data-provider]");

  if (!window.CONFIG) {
    statusBar.textContent = "缺少 config.js";
    return;
  }
  const { supabaseUrl, supabaseAnonKey, backendUrl } = window.CONFIG;
  if (!supabaseUrl || !supabaseAnonKey) {
    statusBar.textContent = "请在 config.js 配置 supabaseUrl/AnonKey";
    return;
  }
  const supabase = window.supabase.createClient(supabaseUrl, supabaseAnonKey);
  const apiBase = (backendUrl || "").replace(/\/$/, "");

  function setStatus(message) {
    if (statusBar) statusBar.textContent = message;
  }

  function toggleCards(isAuthed) {
    loginCard.classList.toggle("hidden", isAuthed);
    profileCard.classList.toggle("hidden", !isAuthed);
  }

  async function fetchProfile(accessToken) {
    if (!apiBase) {
      setStatus("缺少后端地址，无法读取资料");
      return null;
    }
    const res = await fetch(`${apiBase}/users/me`, {
      headers: { Authorization: `Bearer ${accessToken}` }
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`获取资料失败：${res.status} ${text}`);
    }
    return res.json();
  }

  function renderProfile(profile, claims) {
    const provider = claims?.app_metadata?.provider || "unknown";
    providerTag.textContent = provider;
    displayNameEl.textContent = profile.display_name || profile.name || "未设置";
    emailEl.textContent = profile.email || "无邮箱";
    const url = profile.avatar_url || "https://api.dicebear.com/7.x/shapes/svg?seed=user";
    avatarEl.src = url;
    inputDisplayName.value = profile.display_name || "";
    inputAvatarUrl.value = profile.avatar_url || "";
  }

  async function updateProfile(accessToken, payload) {
    const res = await fetch(`${apiBase}/users/me`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`
      },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`更新失败：${res.status} ${text}`);
    }
    return res.json();
  }

  async function bootstrap() {
    setStatus("检测会话中...");
    const { data, error } = await supabase.auth.getSession();
    if (error) {
      setStatus("会话获取失败，请重试登录");
      toggleCards(false);
      return;
    }
    const session = data.session;
    if (!session) {
      toggleCards(false);
      setStatus("未登录");
      return;
    }
    toggleCards(true);
    setStatus("已登录，正在同步资料...");
    try {
      const profile = await fetchProfile(session.access_token);
      renderProfile(profile, session.user);
      setStatus("资料已加载");
    } catch (err) {
      console.error(err);
      setStatus(err.message || "资料加载失败");
    }
  }

  loginButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const provider = btn.dataset.provider;
      setStatus("跳转登录中...");
      const { error } = await supabase.auth.signInWithOAuth({
        provider,
        options: { redirectTo: `${window.location.origin}/callback.html` }
      });
      if (error) {
        console.error(error);
        setStatus("登录失败：" + error.message);
      }
    });
  });

  refreshBtn.addEventListener("click", bootstrap);

  logoutBtn.addEventListener("click", async () => {
    await supabase.auth.signOut();
    toggleCards(false);
    setStatus("已退出登录");
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const { data } = await supabase.auth.getSession();
    if (!data.session) {
      setStatus("请先登录");
      return;
    }
    setStatus("更新资料中...");
    try {
      const profile = await updateProfile(data.session.access_token, {
        display_name: inputDisplayName.value,
        avatar_url: inputAvatarUrl.value
      });
      renderProfile(profile, data.session.user);
      setStatus("更新成功");
    } catch (err) {
      console.error(err);
      setStatus(err.message || "更新失败");
    }
  });

  bootstrap();
})();
