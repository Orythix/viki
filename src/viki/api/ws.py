"""WebSocket streaming chat endpoint for the VIKI dashboard.

Provides a real-time alternative to the REST ``/api/chat`` endpoint using
aiohttp WebSockets.  Each user message streams back ``partial`` chunks as
they arrive from the LLM, along with status and thought events.

Usage::

    from viki.api.ws import setup_ws_chat
    setup_ws_chat(app, controller)

Registered route:

    GET /api/ws/chat  — WebSocket upgrade endpoint
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import WSMsgType, web

from viki.api import CONTROLLER_KEY
from viki.config.logger import viki_logger


async def _chat_ws_handler(request: web.Request) -> web.StreamResponse:
    controller = request.app.get(CONTROLLER_KEY)
    if controller is None:
        return web.json_response({"error": "controller not available"}, status=503)

    ws = web.WebSocketResponse(max_msg_size=0)
    await ws.prepare(request)

    async def send_event(event_type: str, data: Any) -> None:
        if ws.closed:
            return
        try:
            await ws.send_json({"type": event_type, "data": data})
        except ConnectionResetError:
            pass

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                if msg.data == "__ping__":
                    await ws.send_json({"type": "pong"})
                    continue

                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    await send_event("error", "invalid JSON")
                    continue

                text = (payload.get("text") or "").strip()
                if not text:
                    await send_event("error", "missing 'text'")
                    continue

                session_id = payload.get("session_id", "dashboard")
                full_reply: list[str] = []

                def on_event(evt_type: str, evt_data: Any, _reply=full_reply) -> None:
                    if evt_type == "partial":
                        _reply.append(str(evt_data))
                    try:
                        asyncio.ensure_future(
                            send_event(
                                evt_type,
                                str(evt_data)
                                if not isinstance(evt_data, (dict, list))
                                else evt_data,
                            )
                        )
                    except Exception:
                        pass

                try:
                    reply = await controller.process_request(
                        text, on_event=on_event, session_id=session_id
                    )
                except Exception as exc:
                    viki_logger.error("WebSocket chat error: %s", exc)
                    await send_event("error", str(exc))
                    continue

                if not full_reply:
                    full_reply.append(reply)

                await send_event(
                    "done",
                    {
                        "reply": "".join(full_reply) if full_reply else reply,
                        "session_id": session_id,
                    },
                )

            elif msg.type == WSMsgType.CLOSE:
                break
            elif msg.type == WSMsgType.ERROR:
                viki_logger.error("WebSocket error: %s", ws.exception())

    except Exception as exc:
        viki_logger.error("WebSocket handler error: %s", exc)
    finally:
        if not ws.closed:
            await ws.close()

    return ws


def setup_ws_chat(app: web.Application, controller: Any) -> None:
    """Register the ``/api/ws/chat`` WebSocket endpoint on *app*."""
    app[CONTROLLER_KEY] = controller
    app.router.add_get("/api/ws/chat", _chat_ws_handler)
    viki_logger.info("WebSocket streaming chat at /api/ws/chat")
