"""Run the app:  nix develop --command python -m app [--live] [--host 0.0.0.0] [--port 8765]"""
from __future__ import annotations

import argparse

import uvicorn

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
    ap.add_argument("--budget", type=float, default=1.0, help="USD cap for a live session")
    a = ap.parse_args(argv)

    stack = live_stack(a.budget) if a.live else fake_stack()
    root = a.campaigns or CAMPAIGNS
    game = Game(lambda new: open_campaign(stack, root=root, new=new), pace=a.pace)
    print(f"[mode: {'LIVE (spends money, cap $%.2f)' % a.budget if a.live else 'offline fake'}]")
    print(f"open http://{'<IP-ноутбука>' if a.host == '0.0.0.0' else a.host}:{a.port}/")
    uvicorn.run(create_app(game), host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
