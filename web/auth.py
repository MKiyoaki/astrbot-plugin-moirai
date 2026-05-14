"""WebUI 认证模块 — bcrypt 密码哈希 + 进程内会话管理。

设计要点：
  - 密码哈希文件存于 data_dir/.webui_password（bcrypt $2b$ 格式）
  - 若配置中未指定密码，则由服务器生成随机访问 Token
  - 登录成功后颁发 session token（默认 24h），存入响应 cookie
  - 写操作（重置任务、清空缓存等）需要二级 sudo 验证（默认 30min 超时）
  - bcrypt 依赖通过软导入兼容：未安装时降级为 sha256（仅开发期）
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Callable

logger = logging.getLogger(__name__)

try:
    import bcrypt as _bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _bcrypt = None
    _BCRYPT_AVAILABLE = False
    logger.warning(
        "[WebUI/Auth] bcrypt 未安装，将降级为 sha256（仅开发用，生产请 pip install bcrypt）"
    )

_PASSWORD_FILENAME = ".webui_password"
_SESSION_TOKEN_BYTES = 32
_DEFAULT_SESSION_HOURS = 24
_DEFAULT_SUDO_MINUTES = 30


@dataclass(slots=True)
class _Session:
    token: str
    created_at: float
    last_active: float
    sudo_until: float = 0.0


@dataclass(slots=True)
class AuthState:
    """单次请求的认证上下文，由 server 中间件构造并传给 handler。"""
    is_authenticated: bool
    is_sudo: bool
    session_token: str | None = None
    sudo_remaining_seconds: int = 0


def _hash_password(password: str) -> str:
    if _BCRYPT_AVAILABLE:
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
    return "sha256$" + hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith("$2"):
        if not _BCRYPT_AVAILABLE:
            return False
        try:
            return _bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False
    if hashed.startswith("sha256$"):
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == hashed[len("sha256$"):]
    return False


class AuthManager:
    """密码 + 会话管理；线程安全无要求（aiohttp 单事件循环）。"""

    def __init__(
        self,
        data_dir: Path,
        session_hours: int = _DEFAULT_SESSION_HOURS,
        sudo_minutes: int = _DEFAULT_SUDO_MINUTES,
        secret_token: str | None = None,
        is_token_configured: bool = False,
        on_password_changed: Callable[[str], None] | None = None,
    ) -> None:
        self._password_file = data_dir / _PASSWORD_FILENAME
        self._session_seconds = session_hours * 3600
        self._sudo_seconds = sudo_minutes * 60
        self._sessions: dict[str, _Session] = {}
        self._secret_token = secret_token
        self._is_token_configured = is_token_configured
        self._on_password_changed = on_password_changed

    # ------------------------------------------------------------------
    # 密码管理
    # ------------------------------------------------------------------

    def update_secret_token(self, token: str | None, is_configured: bool) -> None:
        """从外部（如配置更新）同步静态 Token。"""
        self._secret_token = token
        self._is_token_configured = is_configured

    def is_password_set(self) -> bool:
        """返回是否已设置持久化密码。不再依赖配置中的静态密码。"""
        return self._password_file.exists()

    def setup_password(self, password: str) -> None:
        """首次设置密码，仅在未设置时可用；调用方负责前置检查。"""
        if not password or len(password) < 4:
            raise ValueError("password too short (min 4 chars)")
        self._password_file.parent.mkdir(parents=True, exist_ok=True)
        self._password_file.write_text(_hash_password(password), encoding="utf-8")
        try:
            self._password_file.chmod(0o600)
        except OSError:
            pass
        
        # 只要设了持久化密码，内存中的临时 Token 就该滚蛋
        self._secret_token = None
        self._is_token_configured = False
        
        # 同步回配置
        if self._on_password_changed:
            self._on_password_changed(password)

    def change_password(self, old_password: str, new_password: str) -> bool:
        # 验证旧密码：由于现在是单源，直接用 verify_password
        if not self.verify_password(old_password):
            return False
            
        self.setup_password(new_password)
        self._sessions.clear()
        return True

    def verify_password(self, password: str) -> bool:
        if not password:
            return False
        # 1. 优先校验持久化哈希文件
        if self._password_file.exists():
            current = self._password_file.read_text(encoding="utf-8").strip()
            if current and _verify_password(password, current):
                return True
            # 如果哈希文件存在但校验失败，不应该再往下走去校验 Token，防止后门
            return False
            
        # 2. 只有在没有哈希文件时，才校验内存 Token（生成的或配置临时传入的）
        if self._secret_token and password == self._secret_token:
            return True
            
        return False

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------

    def login(self, password: str) -> str | None:
        """密码正确则返回新会话 token，否则返回 None。"""
        if not self.verify_password(password):
            return None
        token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
        now = time.time()
        self._sessions[token] = _Session(token=token, created_at=now, last_active=now)
        return token

    def logout(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def verify_sudo(self, token: str | None, password: str) -> bool:
        """已登录会话再次输入密码以激活 sudo 模式。"""
        if not token or token not in self._sessions:
            return False
        if not self.verify_password(password):
            return False
        self._sessions[token].sudo_until = time.time() + self._sudo_seconds
        return True

    def exit_sudo(self, token: str | None) -> None:
        if token and token in self._sessions:
            self._sessions[token].sudo_until = 0.0

    def check(self, token: str | None) -> AuthState:
        """返回当前 token 的认证状态（含 sudo 剩余时间）。"""
        if not token or token not in self._sessions:
            return AuthState(is_authenticated=False, is_sudo=False)
        session = self._sessions[token]
        now = time.time()
        if now - session.last_active > self._session_seconds:
            del self._sessions[token]
            return AuthState(is_authenticated=False, is_sudo=False)
        session.last_active = now
        is_sudo = session.sudo_until > now
        sudo_remaining = max(0, int(session.sudo_until - now)) if is_sudo else 0
        return AuthState(
            is_authenticated=True,
            is_sudo=is_sudo,
            session_token=token,
            sudo_remaining_seconds=sudo_remaining,
        )


# 路由权限级别枚举，便于装饰器和文档复用
PermLevel = Literal["public", "auth", "sudo"]
