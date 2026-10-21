"""Run the app:  nix develop --command python -m app [--live] [--host 0.0.0.0] [--port 8765]"""
from __future__ import annotations

import argparse

import uvicorn

from . import campaigns
from .campaigns import CAMPAIGNS, open_campaign
from .game import Game
from .server import create_app
from .stacks import fake_stack, live_stack


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app", description=__doc__)
    ap.add_argument("--live", action="store_true", help="real cheap models over OpenRouter (costs money)")
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

    campaigns.DIALOGUE = a.dialogue  # read when a campaign is opened
    stack = live_stack(a.budget) if a.live else fake_stack()
    root = a.campaigns or CAMPAIGNS
    if a.campaign == "vizima":
        from .vizima import open_vizima
        opener = lambda new: open_vizima(stack, root=root, new=new, canon_db=a.canon)  # noqa: E731
    else:
        opener = lambda new: open_campaign(stack, root=root, new=new)  # noqa: E731
    game = Game(opener, pace=a.pace)
    print(f"[mode: {'LIVE (spends money, cap $%.2f)' % a.budget if a.live else 'offline fake'}]")
    print(f"open http://{'<IP-ноутбука>' if a.host == '0.0.0.0' else a.host}:{a.port}/")
    uvicorn.run(create_app(game), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
