###############################################################################
#  服务器路由 — 统一异常处理的 API 路由
###############################################################################

import json
import asyncio
from aiohttp import web

from utils.logger import logger


# ─── 路由工具函数 ──────────────────────────────────────────────────────────

def json_ok(data=None):
    """返回成功 JSON 响应"""
    body = {"code": 0, "msg": "ok"}
    if data is not None:
        body["data"] = data
    return web.Response(
        content_type="application/json",
        text=json.dumps(body),
    )


def json_error(msg: str, code: int = -1):
    """返回错误 JSON 响应"""
    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": code, "msg": str(msg)}),
    )


from server.session_manager import session_manager, ADMIN_PASSWORD
from server.avatar_routes import setup_avatar_routes

def get_session(request, sessionid: str):
    """从 app 中获取 session 实例"""
    return session_manager.get_session(sessionid)


# ─── 路由处理函数 ──────────────────────────────────────────────────────────

async def human(request):
    """文本输入（echo/chat 模式），支持 voice/emotion 参数"""
    try:
        params: dict = await request.json()

        sessionid: str = params.get('sessionid', '')
        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")
        session_manager.update_active(sessionid)

        if params.get('interrupt'):
            avatar_session.flush_talk()

        datainfo = {}
        if params.get('tts'):  # tts 参数透传（voice, emotion 等）
            datainfo['tts'] = params.get('tts')

        if params['type'] == 'echo':
            avatar_session.put_msg_txt(params['text'], datainfo)
        elif params['type'] == 'chat':
            llm_response = request.app.get("llm_response")
            if llm_response:
                asyncio.get_event_loop().run_in_executor(
                    None, llm_response, params['text'], avatar_session, datainfo
                )

        return json_ok()
    except Exception as e:
        logger.exception('human route exception:')
        return json_error(str(e))


async def interrupt_talk(request):
    """打断当前说话"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', '')
        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")
        session_manager.update_active(sessionid)
        avatar_session.flush_talk()
        return json_ok()
    except Exception as e:
        logger.exception('interrupt_talk exception:')
        return json_error(str(e))


async def humanaudio(request):
    """上传音频文件"""
    try:
        form = await request.post()
        sessionid = str(form.get('sessionid', ''))
        fileobj = form["file"]
        filebytes = fileobj.file.read()

        datainfo = {}

        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")
        session_manager.update_active(sessionid)
        avatar_session.put_audio_file(filebytes, datainfo)
        return json_ok()
    except Exception as e:
        logger.exception('humanaudio exception:')
        return json_error(str(e))


async def set_audiotype(request):
    """设置自定义状态（动作编排）"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', '')
        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")
        session_manager.update_active(sessionid)
        avatar_session.set_custom_state(params['audiotype'])
        return json_ok()
    except Exception as e:
        logger.exception('set_audiotype exception:')
        return json_error(str(e))


async def record(request):
    """录制控制"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', '')
        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")
        session_manager.update_active(sessionid)
        if params['type'] == 'start_record':
            avatar_session.start_recording()
        elif params['type'] == 'end_record':
            avatar_session.stop_recording()
        return json_ok()
    except Exception as e:
        logger.exception('record exception:')
        return json_error(str(e))


async def is_speaking(request):
    """查询是否正在说话"""
    params = await request.json()
    sessionid = params.get('sessionid', '')
    avatar_session = get_session(request, sessionid)
    if avatar_session is None:
        return json_error("session not found")
    return json_ok(data=avatar_session.is_speaking())


async def admin_config(request):
    """Admin: 获取全局配置参数"""
    try:
        opt = request.app.get("opt")
        if opt:
            return json_ok(data={"config": vars(opt)})
        return json_error("Config not found")
    except Exception as e:
        logger.exception('admin_config exception:')
        return json_error(str(e))


async def admin_sessions(request):
    """Admin: 获取活跃的会话信息"""
    try:
        sessions_info = session_manager.all_sessions_info()
        return json_ok(data={
            "sessions": sessions_info,
            "active_count": session_manager.active_count(),
        })
    except Exception as e:
        logger.exception('admin_sessions exception:')
        return json_error(str(e))


async def admin_session_kill(request):
    """Admin: 强制关闭指定会话"""
    try:
        params = await request.json()
        if params.get("password") != ADMIN_PASSWORD:
            return json_error("wrong password")
        sessionid = params.get("sessionid", "")
        if not session_manager.has_session(sessionid):
            return json_error("session not found")
        session_manager.remove_session(sessionid)
        return json_ok(data={"removed": sessionid})
    except Exception as e:
        logger.exception('admin_session_kill exception:')
        return json_error(str(e))


async def admin_block_ip(request):
    """Admin: 封禁 IP"""
    try:
        params = await request.json()
        if params.get("password") != ADMIN_PASSWORD:
            return json_error("wrong password")
        ip = params.get("ip", "").strip()
        if not ip:
            return json_error("ip required")
        session_manager.block_ip(ip)
        return json_ok(data={"blocked": ip})
    except Exception as e:
        logger.exception('admin_block_ip exception:')
        return json_error(str(e))


async def admin_unblock_ip(request):
    """Admin: 解封 IP"""
    try:
        params = await request.json()
        if params.get("password") != ADMIN_PASSWORD:
            return json_error("wrong password")
        ip = params.get("ip", "").strip()
        if not ip:
            return json_error("ip required")
        session_manager.unblock_ip(ip)
        return json_ok(data={"unblocked": ip})
    except Exception as e:
        logger.exception('admin_unblock_ip exception:')
        return json_error(str(e))


async def admin_blocked_ips(request):
    """Admin: 获取被封禁的 IP 列表"""
    return json_ok(data={"blocked_ips": session_manager.get_blocked_ips()})


# ─── 路由注册 ──────────────────────────────────────────────────────────────

async def humanaudiochat(request):
    """上传音频并进行 STT + LLM 对话"""
    try:
        form = await request.post()
        sessionid = str(form.get('sessionid', ''))
        fileobj = form["file"]
        filebytes = fileobj.file.read()

        avatar_session = get_session(request, sessionid)
        if avatar_session is None:
            return json_error("session not found")

        session_manager.update_active(sessionid)

        # 保存临时文件用于 STT
        temp_audio = f"data/tmp/stt_{sessionid}_{int(time.time())}.wav"
        os.makedirs(os.path.dirname(temp_audio), exist_ok=True)
        with open(temp_audio, "wb") as f:
            f.write(filebytes)

        # 调用 STT
        from llm import stt_response, llm_response
        stt_error = None
        try:
            text = stt_response(temp_audio)
        except Exception as e:
            stt_error = str(e)
            logger.exception('STT exception: %s', stt_error)
            text = None
        finally:
            try:
                os.remove(temp_audio)
            except:
                pass

        if not text:
            return json_error(stt_error or "STT failed")

        logger.info(f"STT Result: {text}")

        # 调用 LLM
        datainfo = {}
        asyncio.get_event_loop().run_in_executor(
            None, llm_response, text, avatar_session, datainfo
        )

        return json_ok(data={"text": text})
    except Exception as e:
        logger.exception('humanaudiochat exception:')
        return json_error(str(e))

import time
import os

def setup_routes(app):
    """注册所有路由到 aiohttp app"""
    app.router.add_post("/human", human)
    app.router.add_post("/humanaudio", humanaudio)
    app.router.add_post("/humanaudiochat", humanaudiochat)
    app.router.add_post("/set_audiotype", set_audiotype)
    app.router.add_post("/record", record)
    app.router.add_post("/interrupt_talk", interrupt_talk)
    app.router.add_post("/is_speaking", is_speaking)
    app.router.add_get("/api/admin/config", admin_config)
    app.router.add_get("/api/admin/sessions", admin_sessions)
    app.router.add_post("/api/admin/session/kill", admin_session_kill)
    app.router.add_post("/api/admin/block_ip", admin_block_ip)
    app.router.add_post("/api/admin/unblock_ip", admin_unblock_ip)
    app.router.add_get("/api/admin/blocked_ips", admin_blocked_ips)

    # 注册 avatar 生成相关的路由
    setup_avatar_routes(app)

    app.router.add_static('/', path='web')
