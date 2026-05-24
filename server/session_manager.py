###############################################################################
#  全局会话管理器 (Session Manager)
###############################################################################

import asyncio
import time
import uuid
from typing import Dict, Optional
from utils.logger import logger
from avatars.base_avatar import BaseAvatar

import os
ADMIN_PASSWORD = "Kittu.2002"
SESSION_IDLE_TIMEOUT = int(os.environ.get("SESSION_IDLE_TIMEOUT", 120))  # auto-remove after 120s idle (2 minutes)
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", 86400))     # absolute max session lifetime 24 hours

def _rand_session_id() -> str:
    """生成 UUID session ID"""
    return str(uuid.uuid4())

class SessionManager:
    """
    全局数字人会话管理器。
    
    统一管理 avatar_sessions 生命周期，并在脱离 WebRTC 时依然保持服务可用。
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.sessions: Dict[str, BaseAvatar] = {}
            self.build_session_fn = None
            self.blocked_ips: set = set()
            self._created_at: Dict[str, float] = {}
            self._last_active: Dict[str, float] = {}
            self._metadata: Dict[str, dict] = {}
            self._on_remove = None
            self.initialized = True

    def init_builder(self, build_session_fn):
        """配置用于构建 avatar_session 的工厂函数"""
        self.build_session_fn = build_session_fn

    def set_on_remove(self, callback):
        """Register callback(sessionid) called when a session is removed"""
        self._on_remove = callback
        
    def get_session(self, sessionid: str) -> Optional[BaseAvatar]:
        """获取已存活的会话"""
        return self.sessions.get(sessionid)

    def has_session(self, sessionid: str) -> bool:
        """检查会话是否存在"""
        return sessionid in self.sessions and self.sessions[sessionid] is not None
        
    async def create_session(self, params: dict, sessionid: str = None) -> str:
        """
        在异步环境中创建一个新会话
        如果 sessionid 为 None，则自动生成。
        """
        if self.build_session_fn is None:
            raise Exception("SessionManager builder not initialized")
            
        if sessionid is None:
            sessionid = _rand_session_id()
            
        logger.info('Creating sessionid=%s, current session num=%d', sessionid, len(self.sessions))
        # 预先占位防止重复
        self.sessions[sessionid] = None
        now = time.time()
        self._created_at[sessionid] = now
        self._last_active[sessionid] = now

        # 在线程池中构建 session（加载模型非常耗时）
        avatar_session = await asyncio.get_event_loop().run_in_executor(
            None, self.build_session_fn, sessionid, params
        )
        self.sessions[sessionid] = avatar_session
        return sessionid
        
    def add_session(self, sessionid: str, avatar_session: BaseAvatar):
        """同步添加静态或外部管理的会话（供非服务端入口调用）"""
        self.sessions[sessionid] = avatar_session
        now = time.time()
        self._created_at[sessionid] = now
        self._last_active[sessionid] = now
        
    def update_active(self, sessionid: str):
        """更新会话活跃时间/状态"""
        if sessionid in self.sessions and self.sessions[sessionid] is not None:
            now = time.time()
            self._last_active[sessionid] = now
            if sessionid not in self._created_at:
                self._created_at[sessionid] = now
            
    def active_count(self) -> int:
        return sum(1 for s in self.sessions.values() if s is not None)

    def all_sessions_info(self) -> list:
        now = time.time()
        result = []
        for sid in list(self.sessions.keys()):
            avatar = self.sessions[sid]
            if avatar is not None:
                s_opt = getattr(avatar, 'opt', None)
                meta = self._metadata.get(sid, {})
                created = self._created_at.get(sid)
                last_active = self._last_active.get(sid)
                entry = {
                    "sessionid": sid,
                    "speaking": avatar.is_speaking() if hasattr(avatar, 'is_speaking') else False,
                    "recording": getattr(avatar, 'recording', False),
                    "ip": meta.get("ip", ""),
                    "device": meta.get("device", ""),
                    "created_at": created,
                    "age_seconds": round(now - created, 1) if created else None,
                    "idle_seconds": round(now - last_active, 1) if last_active else None,
                }
                if s_opt:
                    entry.update({
                        "model": getattr(s_opt, "model", ""),
                        "avatar_id": getattr(s_opt, "avatar_id", ""),
                        "REF_FILE": getattr(s_opt, "REF_FILE", ""),
                        "transport": getattr(s_opt, "transport", ""),
                        "batch_size": getattr(s_opt, "batch_size", 0),
                        "customopt": getattr(s_opt, "customopt", []),
                    })
                result.append(entry)
        return result

    def remove_session(self, sessionid: str):
        """销毁会话资源"""
        if sessionid in self.sessions:
            logger.info(f"Removing session {sessionid}")
            self.sessions.pop(sessionid, None)
            self._created_at.pop(sessionid, None)
            self._last_active.pop(sessionid, None)
            self._metadata.pop(sessionid, None)
            if self._on_remove:
                try:
                    self._on_remove(sessionid)
                except Exception as e:
                    logger.error("on_remove callback failed: %s", e)

    def set_session_metadata(self, sessionid: str, ip: str = "", user_agent: str = ""):
        """Store IP and device info for a session"""
        if sessionid not in self.sessions:
            return
        self._metadata[sessionid] = {"ip": ip, "device": user_agent[:100] if user_agent else ""}

    def cleanup_expired_sessions(self):
        """Remove sessions idle longer than SESSION_IDLE_TIMEOUT or older than SESSION_MAX_AGE"""
        now = time.time()
        expired = []
        for sid in list(self.sessions.keys()):
            last_active = self._last_active.get(sid)
            created = self._created_at.get(sid)
            if last_active and (now - last_active) > SESSION_IDLE_TIMEOUT:
                expired.append((sid, "idle"))
            elif created and (now - created) > SESSION_MAX_AGE:
                expired.append((sid, "max_age"))
        for sid, reason in expired:
            logger.info("Session %s expired (%s)", sid, reason)
            self.remove_session(sid)
        return len(expired)

    def is_ip_blocked(self, ip: str) -> bool:
        return ip in self.blocked_ips

    def block_ip(self, ip: str):
        self.blocked_ips.add(ip)
        logger.info("Blocked IP: %s", ip)

    def unblock_ip(self, ip: str):
        self.blocked_ips.discard(ip)
        logger.info("Unblocked IP: %s", ip)

    def get_blocked_ips(self) -> list:
        return sorted(self.blocked_ips)

# 单例抛出
session_manager = SessionManager()
