#!/usr/bin/env python
"""Locate the Okami HD install directory.

Resolution order:
  1. OKAMI_DIR environment variable
  2. every Steam library listed in <Steam>\\steamapps\\libraryfolders.vdf
     (Steam root from the registry, falling back to the default install path)

Import `GAME` from this module in the analysis tools, or call find_game_dir().
"""
import os
import re
import sys

APP_ID = "587620"
GAME_SUBDIR = os.path.join("steamapps", "common", "Okami")


def _steam_root():
    try:
        import winreg

        for hive, key in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    name = "SteamPath" if hive == winreg.HKEY_CURRENT_USER else "InstallPath"
                    path, _ = winreg.QueryValueEx(k, name)
                    if path and os.path.isdir(path):
                        return os.path.normpath(path)
            except OSError:
                continue
    except ImportError:
        pass
    for cand in (
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Steam"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Steam"),
    ):
        if os.path.isdir(cand):
            return cand
    return None


def _library_paths(steam_root):
    yield steam_root
    vdf = os.path.join(steam_root, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        yield m.group(1).replace("\\\\", "\\")


def find_game_dir():
    env = os.environ.get("OKAMI_DIR")
    if env:
        return os.path.normpath(env)
    root = _steam_root()
    if root:
        for lib in _library_paths(root):
            cand = os.path.join(lib, GAME_SUBDIR)
            if os.path.isfile(os.path.join(cand, "okami.exe")):
                return os.path.normpath(cand)
    return None


GAME = find_game_dir()


if __name__ == "__main__":
    if GAME:
        print(GAME)
        sys.exit(0)
    print("Okami HD not found; set OKAMI_DIR", file=sys.stderr)
    sys.exit(1)
