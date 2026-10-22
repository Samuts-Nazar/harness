"""HTTP layer (Starlette): static page, JSON actions, and one Server-Sent Events stream.

Stream = SSE (server to client, auto-reconnect with Last-Event-ID, so a phone returning from the
background resumes where it left off); interrupt and everything else = plain POSTs.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .game import Busy, Ended, Game, explain

STATIC = Path(__file__).parent / "static"
KEEPALIVE = 15.0


def create_app(game: Game) -> Starlette:
    async def index(_: Request) -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    async def state(_: Request) -> JSONResponse:
        return JSONResponse(game.state())

    async def turn(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            # typing during a turn cuts in: this waits for the running turn to stop, then starts
            await run_in_threadpool(game.start_turn, str(body.get("text", "")))
        except Busy:
            return JSONResponse({"error": "Хід ще триває."}, status_code=409)
        except Ended:
            return JSONResponse({"error": "Персонаж загинув. Кампанію завершено.",
                                 "ended": True}, status_code=423)
        except ValueError:
            return JSONResponse({"error": "Порожній хід."}, status_code=400)
        return JSONResponse({"ok": True}, status_code=202)

    async def interrupt(_: Request) -> JSONResponse:
        return JSONResponse({"interrupted": game.interrupt()})

    async def skip(_: Request) -> JSONResponse:
        return JSONResponse({"skipped": game.skip()})

    async def presence(request: Request) -> JSONResponse:
        body = await request.json()
        game.set_visible(bool(body.get("visible", True)))
        return JSONResponse({"ok": True})

    async def new_campaign(_: Request) -> JSONResponse:
        try:
            game.reset()
        except Busy:
            return JSONResponse({"error": "Хід триває."}, status_code=409)
        return JSONResponse(game.state())

    async def panel(_: Request) -> JSONResponse:
        return JSONResponse(game.panel())

    async def debug(_: Request) -> JSONResponse:
        return JSONResponse(game.debug)

    async def challenge(request: Request) -> JSONResponse:
        body = await request.json()
        try:
            event = int(body["event"])
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "Не вказано репліку."}, status_code=400)
        try:
            out = await run_in_threadpool(game.challenge, event, str(body.get("explanation", "")))
        except Busy:
            return JSONResponse({"error": "Хід триває."}, status_code=409)
        except (ValueError, KeyError):
            return JSONResponse({"error": "Цю репліку не можна оскаржити."}, status_code=400)
        except Exception as e:  # noqa: BLE001 - shown to the player, nothing changes
            return JSONResponse({"error": explain(e)}, status_code=502)
        return JSONResponse(out)

    async def knowledge(_: Request) -> JSONResponse:
        try:
            return JSONResponse(await run_in_threadpool(game.knowledge))
        except Busy:
            return JSONResponse({"error": "Хід триває."}, status_code=409)

    async def cast(_: Request) -> JSONResponse:
        return JSONResponse(game.cast())

    async def people(_: Request) -> JSONResponse:
        return JSONResponse(game.people())

    async def ink(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return JSONResponse({"error": "Недійсний запит."}, status_code=400)
        try:
            game.set_ink(str(body.get("tok", "")), body.get("ink"))
        except KeyError:
            return JSONResponse({"error": "Невідомий персонаж."}, status_code=404)
        except ValueError:
            return JSONResponse({"error": "Недійсний колір."}, status_code=400)
        return JSONResponse({"ok": True})

    async def suggestions(request: Request) -> JSONResponse:
        more = request.query_params.get("more") == "1"
        try:
            return JSONResponse(await run_in_threadpool(game.suggestions, more))
        except Exception as e:  # noqa: BLE001 - shown to the player, nothing changes
            return JSONResponse({"error": explain(e)}, status_code=502)

    async def events(request: Request) -> StreamingResponse:
        after = int(request.headers.get("last-event-id") or request.query_params.get("after") or 0)
        until_idle = request.query_params.get("until_idle") == "1"  # curl/tests: end when quiet

        async def gen():  # type: ignore[no-untyped-def]
            nonlocal after
            quiet = 0.0
            yield "retry: 1000\n\n"
            while not await request.is_disconnected():
                batch = game.events_after(after)
                for ev in batch:
                    after = ev["seq"]
                    yield f"id: {ev['seq']}\nevent: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if batch:
                    quiet = 0.0
                    continue
                if until_idle and not game.running:
                    return
                await asyncio.sleep(0.03)
                quiet += 0.03
                if quiet >= KEEPALIVE:
                    quiet = 0.0
                    yield ": keepalive\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return Starlette(routes=[
        Route("/", index),
        Route("/api/state", state),
        Route("/api/turn", turn, methods=["POST"]),
        Route("/api/interrupt", interrupt, methods=["POST"]),
        Route("/api/skip", skip, methods=["POST"]),
        Route("/api/presence", presence, methods=["POST"]),
        Route("/api/campaign/new", new_campaign, methods=["POST"]),
        Route("/api/panel", panel),
        Route("/api/debug", debug),
        Route("/api/challenge", challenge, methods=["POST"]),
        Route("/api/knowledge", knowledge),
        Route("/api/cast", cast),
        Route("/api/people", people),
        Route("/api/ink", ink, methods=["POST"]),
        Route("/api/suggestions", suggestions),
        Route("/api/events", events),
        Mount("/static", StaticFiles(directory=STATIC), name="static"),
    ])
