###############################################################################
#  全局会话管理器 (Session Manager)
###############################################################################

import asyncio
import time
import uuid
from typing import Dict, Optional
from utils.logger import logger
from avatars.base_avatar import BaseAvatar

ADMIN_PASSWORD = "Kittu.2002"

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
            self.initialized = True

    def init_builder(self, build_session_fn):
        """配置用于构建 avatar_session 的工厂函数"""
        self.build_session_fn = build_session_fn
        
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

        # 在线程池中构建 session（加载模型非常耗时）
        avatar_session = await asyncio.get_event_loop().run_in_executor(
            None, self.build_session_fn, sessionid, params
        )
        self.sessions[sessionid] = avatar_session
        return sessionid
        
    def add_session(self, sessionid: str, avatar_session: BaseAvatar):
        """同步添加静态或外部管理的会话（供非服务端入口调用）"""
        self.sessions[sessionid] = avatar_session
        
    def update_active(self, sessionid: str):
        """更新会话活跃时间/状态"""
        if sessionid in self.sessions and self.sessions[sessionid] is not None:
            pass
            
    def active_count(self) -> int:
        return sum(1 for s in self.sessions.values() if s is not None)

    def all_sessions_info(self) -> list:
        result = []
        for sid in list(self.sessions.keys()):
            avatar = self.sessions[sid]
            if avatar is not None:
                s_opt = getattr(avatar, 'opt', None)
                entry = {
                    "sessionid": sid,
                    "speaking": avatar.is_speaking() if hasattr(avatar, 'is_speaking') else False,
                    "recording": getattr(avatar, 'recording', False),
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
            # todo: 还可以主动调 avatar_session 释放
            self.sessions.pop(sessionid, None)

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
