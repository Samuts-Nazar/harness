{
  description = "harness dev environment";
  inputs.nixpkgs.url = "nixpkgs";
  outputs = { self, nixpkgs }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
    in {
      devShells.x86_64-linux.default = pkgs.mkShell {
        packages = [
          (pkgs.python3.withPackages (ps: [
            ps.python-dotenv ps.httpx ps.pytest
            # game packages (app/newgame.py, task 5): YAML from an external AI chat
            ps.pyyaml
            # phone app (app/): ASGI toolkit + server; playwright for the phone-size UI check
            ps.starlette ps.uvicorn ps.playwright
          ]))
          pkgs.uv
          pkgs.playwright-driver.browsers
        ];
        PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
        PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
      };
    };
}
