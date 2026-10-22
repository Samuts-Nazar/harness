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

from .game import Busy, Ended, Game, Refused, explain

STATIC = Path(__file__).parent / "static"
KEEPALIVE = 15.0


def create_app(game: Game) -> Starlette:
    async def index(_: Request) -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    # the views take the game's lock (never held across a model call, but it may wait on a
    # database read): they run in the thread pool, so the event loop and the stream never wait
    async def state(_: Request) -> JSONResponse:
        return JSONResponse(await run_in_threadpool(game.state))

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
            await run_in_threadpool(game.reset)
        except Busy:
            return JSONResponse({"error": "Хід триває."}, status_code=409)
        return JSONResponse(await run_in_threadpool(game.state))

    PACKAGE_BYTES = 400_000  # a request body bigger than this is refused before parsing

    async def package_text(request: Request) -> str:
        raw = await request.body()
        if len(raw) > PACKAGE_BYTES:
            return "x" * (PACKAGE_BYTES)  # parse() refuses it as too big, with a readable issue
        try:
            body = json.loads(raw)
        except ValueError:
            return ""
        return str(body.get("text", "")) if isinstance(body, dict) else ""

    def parse_package(text: str):  # type: ignore[no-untyped-def]
        """(package, None) or (None, issues as JSON); any failure becomes a «файл» issue."""
        from . import newgame
        try:
            return newgame.parse(text), None
        except newgame.PackageError as e:
            return None, [i.to_json() for i in e.issues]
        except Exception:  # noqa: BLE001 - never a 500 for a bad file
            return None, [newgame.Issue(
                "файл", "Файл не вдалося прочитати.",
                "Перевірте, що це YAML за прикладом з інструкції, і спробуйте ще раз.").to_json()]

    async def package_check(request: Request) -> JSONResponse:
        """A game package (app/newgame.py): its summary card, or the problems to fix."""
        from .newgame import summary
        pkg, errors = parse_package(await package_text(request))
        if errors:
            return JSONResponse({"ok": False, "errors": errors})
        return JSONResponse({"ok": True, "summary": summary(pkg)})

    async def package_start(request: Request) -> JSONResponse:
        pkg, errors = parse_package(await package_text(request))
        if errors:
            return JSONResponse({"ok": False, "errors": errors}, status_code=400)
        if game.open_package is None:
            return JSONResponse({"error": "Нова гра з файлу тут недоступна."}, status_code=501)
        try:
            await run_in_threadpool(game.start_package, pkg)
        except Busy:
            return JSONResponse({"error": "Хід триває. Дочекайтеся кінця ходу."}, status_code=409)
        except Exception as e:  # noqa: BLE001 - shown to the player; the old campaign stays
            return JSONResponse({"error": explain(e)}, status_code=502)
        return JSONResponse(await run_in_threadpool(game.state))

    async def panel(_: Request) -> JSONResponse:
        return JSONResponse(await run_in_threadpool(game.panel))

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

    async def edit(request: Request, name: str) -> JSONResponse:
        """model_error / cut: the player's corrections of the last output."""
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
            ev = body.get("event")
            event = None if ev is None else int(ev)
            if name == "cut":
                if event is None:
                    raise ValueError
                args: tuple = (event, int(body["after_words"]))
            else:
                args = (event, str(body.get("explanation", "")))
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"error": "Недійсний запит."}, status_code=400)
        try:
            out = await run_in_threadpool(getattr(game, name), *args)
        except Busy:
            return JSONResponse({"error": "Хід триває."}, status_code=409)
        except Ended:
            return JSONResponse({"error": "Кампанію завершено.", "ended": True}, status_code=423)
        except Refused as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except (ValueError, KeyError):
            return JSONResponse({"error": "Цього не можна виправити."}, status_code=400)
        except Exception as e:  # noqa: BLE001 - shown to the player, nothing else changes
            return JSONResponse({"error": explain(e)}, status_code=502)
        return JSONResponse(out)

    async def model_error(request: Request) -> JSONResponse:
        return await edit(request, "model_error")

    async def cut(request: Request) -> JSONResponse:
        return await edit(request, "cut")

    async def places(_: Request) -> JSONResponse:
        return JSONResponse(await run_in_threadpool(game.places))

    async def knowledge(_: Request) -> JSONResponse:
        try:
            return JSONResponse(await run_in_threadpool(game.knowledge))
        except Busy:
            return JSONResponse({"error": "Хід триває."}, status_code=409)

    async def cast(_: Request) -> JSONResponse:
        return JSONResponse(await run_in_threadpool(game.cast))

    async def people(_: Request) -> JSONResponse:
        return JSONResponse(await run_in_threadpool(game.people))

    async def ink(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return JSONResponse({"error": "Недійсний запит."}, status_code=400)
        try:
            await run_in_threadpool(game.set_ink, str(body.get("tok", "")), body.get("ink"))
        except KeyError:
            return JSONResponse({"error": "Невідомий персонаж."}, status_code=404)
        except ValueError:
            return JSONResponse({"error": "Недійсний колір."}, status_code=400)
        except Exception:  # noqa: BLE001 - e.g. the disk: the player gets a message, not a 500 page
            return JSONResponse({"error": "Не вдалося зберегти колір."}, status_code=500)
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
                batch = game.events_after(after)  # its own short lock, never the game's
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
        Route("/api/package/check", package_check, methods=["POST"]),
        Route("/api/package/start", package_start, methods=["POST"]),
        Route("/api/panel", panel),
        Route("/api/debug", debug),
        Route("/api/challenge", challenge, methods=["POST"]),
        Route("/api/model_error", model_error, methods=["POST"]),
        Route("/api/cut", cut, methods=["POST"]),
        Route("/api/places", places),
        Route("/api/knowledge", knowledge),
        Route("/api/cast", cast),
        Route("/api/people", people),
        Route("/api/ink", ink, methods=["POST"]),
        Route("/api/suggestions", suggestions),
        Route("/api/events", events),
        Mount("/static", StaticFiles(directory=STATIC), name="static"),
    ])
