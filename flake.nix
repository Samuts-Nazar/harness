{
  description = "harness dev environment";
  inputs.nixpkgs.url = "nixpkgs";
  outputs = { self, nixpkgs }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;
    in {
      devShells.x86_64-linux.default = pkgs.mkShell {
        packages = [
          (pkgs.python3.withPackages (ps: [ ps.python-dotenv ps.httpx ps.pytest ]))
          pkgs.uv
        ];
      };
    };
}
