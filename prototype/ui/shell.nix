# Тестове оточення Playwright, прив'язане до тієї ж ревізії nixpkgs, що й flake.lock.
{ pkgs ? import (builtins.fetchTarball {
    url = "https://releases.nixos.org/nixpkgs/nixpkgs-26.11pre1093421.f20cd90e28fe/nixexprs.tar.zst";
    sha256 = "sha256-MTJCMrhDFb+GRbLxBPTp8kB4dDlO+egmQ5qsJgYuaWw=";
  }) { } }:
pkgs.mkShell {
  packages = [
    (pkgs.python3.withPackages (ps: [ ps.playwright ]))
    pkgs.playwright-driver.browsers
  ];
  PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
  PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = "true";
}
