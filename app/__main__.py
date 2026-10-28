"""Run the app:  nix develop --command python -m app [--live | --local] [--host 0.0.0.0] [--port 8765]

--local plays every role on a local llama.cpp server (start it first: docs/local-llm.md); no key,
no network, no cost:  python -m app --local [--local-url URL] [--local-model NAME]"""
from __future__ import annotations

import argparse

import uvicorn

from harness.providers import LOCAL_URL

from . import campaigns
from .campaigns import CAMPAIGNS, open_campaign
from .game import Game
from .server import create_app
from .stacks import LOCAL_MODEL, LOCAL_TIMEOUT_S, fake_stack, live_stack, local_stack


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m app", description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="real cheap models over OpenRouter (costs money)")
    mode.add_argument("--local", action="store_true",
                      help="every role on a local OpenAI-compatible server (docs/local-llm.md)")
    ap.add_argument("--local-url", default=LOCAL_URL, help=f"chat completions URL (default {LOCAL_URL})")
    ap.add_argument("--local-model", default=LOCAL_MODEL,
                    help=f"model name the server answers to (default {LOCAL_MODEL})")
    ap.add_argument("--local-timeout", type=float, default=None,
                    help=f"seconds to wait for one local answer (default {LOCAL_TIMEOUT_S:g})")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from the phone over the LAN")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--pace", type=float, default=0.25, help="seconds per streamed word")
    ap.add_argument("--campaigns", default=None, help="folder of saved campaigns (default: campaigns/)")
    ap.add_argument("--campaign", choices=("vizima", "inn"), default="vizima",
                    help="vizima: the book's Vizima, situation A, the demon without limits (default); "
                         "inn: the old inn scene with Ragnar")
    ap.add_argument("--canon", default=None, help="canon store for vizima (default: "
                    "$HARNESS_CANON_DB or campaigns/canon/pilot_v3.db; none: no canon)")
    ap.add_argument("--dialogue", choices=("living", "classic"), default="living",
                    help="living: multi-line NPC exchanges, optional narration (default); "
                         "classic: the old director (for A/B generation)")
    ap.add_argument("--budget", type=float, default=1.0, help="USD cap for a live session")
    a = ap.parse_args(argv)
    if not a.local and (a.local_url != LOCAL_URL or a.local_model != LOCAL_MODEL
                        or a.local_timeout is not None):
        ap.error("--local-url, --local-model and --local-timeout need --local")
    return a


def make_stack(a: argparse.Namespace) -> campaigns.Stack:
    if a.local:
        return local_stack(a.local_url, a.local_model, timeout=a.local_timeout or LOCAL_TIMEOUT_S)
    return live_stack(a.budget) if a.live else fake_stack()


def main(argv: list[str] | None = None) -> None:
    a = parse_args(argv)

    campaigns.DIALOGUE = a.dialogue  # read when a campaign is opened
    stack = make_stack(a)
    root = a.campaigns or CAMPAIGNS
    if a.campaign == "vizima":
        from .vizima import open_vizima
        opener = lambda new: open_vizima(stack, root=root, new=new, canon_db=a.canon)  # noqa: E731
    else:
        opener = lambda new: open_campaign(stack, root=root, new=new)  # noqa: E731
    from . import newgame
    # a campaign started from a game package ("Нова гра з файлу") continues as such after a restart
    game = Game(newgame.opener(stack, root=root, fallback=opener, canon_db=a.canon), pace=a.pace,
                open_package=lambda pkg: newgame.open_package(stack, pkg, root=root,
                                                              canon_db=a.canon))
    label = ("LIVE (spends money, cap $%.2f)" % a.budget if a.live else
             f"LOCAL ({a.local_model} at {a.local_url})" if a.local else "offline fake")
    print(f"[mode: {label}]")
    print(f"open http://{'<IP-ноутбука>' if a.host == '0.0.0.0' else a.host}:{a.port}/")
    uvicorn.run(create_app(game), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
