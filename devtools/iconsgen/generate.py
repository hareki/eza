#!/usr/bin/env python3
"""Generate eza's theme.yml icon/color overrides from neovim's mini.icons.

mini.icons (as configured in the user's neovim, including the personal override)
is the source of truth. This script asks it, via `nvim --headless` running
oracle.lua, for the effective glyph + highlight group of every file
extension / filename / directory that eza already knows about (parsed from
src/output/icons.rs), maps the highlight to a catppuccin-mocha color, and writes
`icon` (glyph + color) overrides into eza's theme.yml.

No eza source is modified. The two icon maps (`extensions:` / `filenames:`) are
regenerated; every other section of an existing theme.yml is preserved verbatim,
as are the user's manual entries for keys mini.icons has no specific icon for.

Glyphs are written by this script's own UTF-8 file I/O, so no editor glyph
sanitization occurs.

Usage:
    python3 devtools/iconsgen/generate.py [--theme PATH] [--icons-rs PATH]

Environment overrides:
    MINI_ICONS_PATH  mini.icons plugin root (default: ~/.local/share/nvim/lazy/mini.icons)
    ICONS_LUA_PATH   personal icons.lua (default: ~/.../nvim/lua/config/icons.lua)
    EZA_THEME_OUT    output theme.yml (default: $XDG_CONFIG_HOME/eza/theme.yml)

Requires: nvim on PATH with mini.icons installed, and PyYAML.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

# --- Configuration ----------------------------------------------------------

# Neutral filename color applied to *file* overrides (matches the user's
# established theme.yml convention: colored icon, neutral filename). Set to None
# to leave eza's own filetype-based filename coloring untouched. Directories
# never get a filename override (their name stays directory-blue).
FILENAME_FG = "#cdd6f4"

# mini.icons highlight group -> catppuccin-mocha hex, using the effective colors
# of the user's neovim: catppuccin's mini integration with the personal
# `MiniIconsAzure -> teal` override applied (so Azure and Cyan both become teal).
# Mirrors lazygit's iconsgen_ext hlToConst.
HL_TO_HEX = {
    "MiniIconsAzure": "#94e2d5",  # overridden from sapphire to teal by the user
    "MiniIconsBlue": "#89b4fa",
    "MiniIconsCyan": "#94e2d5",  # teal
    "MiniIconsGreen": "#a6e3a1",
    "MiniIconsGrey": "#cdd6f4",  # text
    "MiniIconsOrange": "#fab387",  # peach
    "MiniIconsPurple": "#cba6f7",  # mauve
    "MiniIconsRed": "#f38ba8",
    "MiniIconsYellow": "#f9e2af",
}

# Keys defined only in the personal mini.icons override that eza may lack. They
# are always emitted (the override makes them non-default). Mirrors lazygit's
# newKeys. Keys that overlap eza's maps are picked up automatically.
OVERRIDE_EXT = {"dbml"}
OVERRIDE_FILE = {
    ".keep",
    "devcontainer.json",
    ".node-version",
    ".yarnrc.yml",
    "eslint.config.js",
    "tsconfig.build.json",
}

HOME = Path.home()
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent


def die(msg: str) -> "None":
    print(f"iconsgen: {msg}", file=sys.stderr)
    sys.exit(1)


# --- Parse eza's icons.rs for its key sets ----------------------------------

_MAP_RE = {
    "dir": "DIRECTORY_ICONS",
    "file": "FILENAME_ICONS",
    "ext": "EXTENSION_ICONS",
}
_KEY_RE = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*=>')


def parse_icons_rs(path: Path) -> dict[str, list[str]]:
    """Return {'dir': [...], 'file': [...], 'ext': [...]} of the quoted keys of
    each phf_map! block, preserving source order."""
    text = path.read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    for kind, const_name in _MAP_RE.items():
        m = re.search(rf"const\s+{const_name}\s*:.*?phf_map!\s*\{{", text, re.S)
        if not m:
            die(f"could not find {const_name} in {path}")
        start = m.end()
        depth = 1
        i = start
        while i < len(text) and depth:
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        block = text[start : i - 1]
        keys = [km.group(1) for line in block.splitlines() if (km := _KEY_RE.match(line))]
        out[kind] = keys
    return out


# --- Run the nvim oracle ----------------------------------------------------


def run_oracle(queries: list[tuple[int, str, str]]) -> dict[int, tuple[str, str, bool]]:
    """queries: list of (id, category, name). Returns id -> (glyph, hl, is_default)."""
    mini_path = os.environ.get("MINI_ICONS_PATH", str(HOME / ".local/share/nvim/lazy/mini.icons"))
    icons_lua = os.environ.get(
        "ICONS_LUA_PATH",
        str(HOME / "Repositories/personal/dotfiles/nvim/.config/nvim/lua/config/icons.lua"),
    )
    for p, what in ((mini_path, "mini.icons plugin (set MINI_ICONS_PATH)"),
                    (icons_lua, "personal icons.lua (set ICONS_LUA_PATH)")):
        if not Path(p).exists():
            die(f"{what} not found at {p}")

    with tempfile.TemporaryDirectory(prefix="iconsgen") as tmp:
        q_path = Path(tmp) / "queries.tsv"
        r_path = Path(tmp) / "results.tsv"
        with q_path.open("w", encoding="utf-8") as f:
            for qid, cat, name in queries:
                f.write(f"{qid}\t{cat}\t{name}\n")

        env = dict(os.environ)
        env.update(
            MINI_ICONS_PATH=mini_path,
            ICONS_LUA_PATH=icons_lua,
            QUERIES_PATH=str(q_path),
            RESULTS_PATH=str(r_path),
        )
        proc = subprocess.run(
            ["nvim", "--headless", "-l", str(SCRIPT_DIR / "oracle.lua")],
            env=env,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            die(f"nvim oracle failed:\n{proc.stderr}")
        if not r_path.exists():
            die(f"oracle produced no results:\n{proc.stderr}")

        results: dict[int, tuple[str, str, bool]] = {}
        for line in r_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 4:
                die(f"malformed oracle result line: {line!r}")
            qid, glyph, hl, is_default = parts
            results[int(qid)] = (glyph, hl, is_default == "true")
    if len(results) != len(queries):
        die(f"oracle returned {len(results)} results for {len(queries)} queries")
    return results


# --- Build override entries -------------------------------------------------


def hl_hex(hl: str, key: str) -> str:
    c = HL_TO_HEX.get(hl)
    if c is None:
        die(f"unmapped highlight group {hl!r} for {key!r}")
    return c


def single_glyph(glyph: str, key: str) -> str | None:
    """eza `glyph: Option<char>` needs exactly one Unicode scalar."""
    if len(glyph) != 1:
        print(f"iconsgen: warning: glyph {glyph!r} for {key!r} is not a single "
              f"char ({len(glyph)}); skipping", file=sys.stderr)
        return None
    return glyph


def file_entry(glyph: str, hl: str, key: str) -> dict:
    e: dict = {}
    if FILENAME_FG:
        e["filename"] = {"foreground": FILENAME_FG}
    e["icon"] = {"glyph": glyph, "style": {"foreground": hl_hex(hl, key)}}
    return e


def dir_entry(glyph: str, hl: str, key: str) -> dict:
    # No filename override: the directory name keeps eza's directory-blue.
    return {"icon": {"glyph": glyph, "style": {"foreground": hl_hex(hl, key)}}}


# --- Deterministic flow-style YAML rendering --------------------------------

_KEY_ORDER = {"filename": 0, "icon": 1, "glyph": 0, "style": 1, "foreground": 0, "background": 1}


def _needs_quote_key(k: str) -> bool:
    return not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*", k) or k in ("y", "n", "yes", "no", "true", "false", "null", "on", "off")


def q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def render_key(k: str) -> str:
    return q(k) if _needs_quote_key(k) else k


def render_value(v) -> str:
    if isinstance(v, dict):
        if not v:
            return "{}"
        items = sorted(v.items(), key=lambda kv: (_KEY_ORDER.get(kv[0], 99), kv[0]))
        inner = ", ".join(f"{render_key(k)}: {render_value(val)}" for k, val in items)
        return "{ " + inner + " }"
    if isinstance(v, bool):
        return "true" if v else "false"
    return q(str(v))


def render_block(name: str, entries: dict[str, dict], comment: str) -> str:
    lines = [f"{name}:", f"  # {comment}"]
    for key in sorted(entries):
        lines.append(f"  {render_key(key)}: {render_value(entries[key])}")
    return "\n".join(lines) + "\n"


# --- Splice into an existing theme.yml --------------------------------------

_TOPLEVEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")


def splice(existing_text: str, ext_block: str, name_block: str) -> str:
    """Replace the extensions:/filenames: sections with freshly rendered blocks,
    preserving every other top-level section verbatim and in order."""
    lines = existing_text.splitlines(keepends=True)
    tops = [i for i, l in enumerate(lines) if _TOPLEVEL_RE.match(l)]
    icon_block = ext_block + "\n" + name_block

    if not tops:
        base = existing_text
        if base and not base.endswith("\n"):
            base += "\n"
        return base + "\n" + icon_block

    parts: list[str] = []
    if tops[0] > 0:
        parts.append("".join(lines[: tops[0]]))
    placed = False
    for j, i in enumerate(tops):
        name = lines[i].split(":", 1)[0].strip()
        end = tops[j + 1] if j + 1 < len(tops) else len(lines)
        if name in ("extensions", "filenames"):
            if not placed:
                parts.append(icon_block)
                placed = True
            continue
        parts.append("".join(lines[i:end]))
    if not placed:
        # keep a blank line before the appended block
        if parts and not parts[-1].endswith("\n\n"):
            parts.append("\n")
        parts.append(icon_block)
    return "".join(parts)


# --- Main -------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    default_theme = os.environ.get("EZA_THEME_OUT") or str(
        Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "eza" / "theme.yml"
    )
    ap.add_argument("--theme", default=default_theme, help="output theme.yml path")
    ap.add_argument("--icons-rs", default=str(REPO_ROOT / "src" / "output" / "icons.rs"))
    args = ap.parse_args()

    icons_rs = Path(args.icons_rs)
    if not icons_rs.exists():
        die(f"icons.rs not found at {icons_rs}")
    keys = parse_icons_rs(icons_rs)

    dir_keys = list(dict.fromkeys(keys["dir"]))
    file_keys = list(dict.fromkeys(keys["file"] + sorted(OVERRIDE_FILE)))
    ext_keys = list(dict.fromkeys(keys["ext"] + sorted(OVERRIDE_EXT)))

    # File/dir name collisions can't be represented by the single `filenames`
    # map; skip them (eza's built-in icon_for_file already distinguishes them).
    collisions = sorted(set(dir_keys) & set(file_keys))

    # Assign query ids.
    queries: list[tuple[int, str, str]] = []
    meta: dict[int, tuple[str, str]] = {}  # id -> (kind, key)

    def add(kind: str, category: str, name: str, key: str) -> None:
        qid = len(queries)
        queries.append((qid, category, name))
        meta[qid] = (kind, key)

    for k in ext_keys:
        add("ext", "file", "x." + k, k)
    for k in file_keys:
        if k in collisions:
            continue
        add("file", "file", k, k)
    for k in dir_keys:
        if k in collisions:
            continue
        add("dir", "directory", k, k)

    results = run_oracle(queries)

    # Pass 1: extensions.
    ext_entries: dict[str, dict] = {}
    for qid, (glyph, hl, is_default) in results.items():
        kind, key = meta[qid]
        if kind != "ext":
            continue
        if is_default and key not in OVERRIDE_EXT:
            continue
        g = single_glyph(glyph, key)
        if g is None:
            continue
        ext_entries[key] = file_entry(g, hl, key)

    # Pass 2: filenames + directories (into one `filenames` map). Directories
    # never inherit an extension icon (eza's style_override skips the ext branch
    # for directories), so no shadowing guards are needed.
    name_entries: dict[str, dict] = {}
    for qid, (glyph, hl, is_default) in results.items():
        kind, key = meta[qid]
        if kind == "ext":
            continue
        override = key in OVERRIDE_FILE
        if is_default and not override:
            continue
        g = single_glyph(glyph, key)
        if g is None:
            continue
        name_entries[key] = dir_entry(g, hl, key) if kind == "dir" else file_entry(g, hl, key)

    # Merge with the existing theme.yml: preserve the user's manual entries for
    # keys we didn't (re)generate; generated entries win; guards never clobber.
    theme_path = Path(args.theme)
    old_ext: dict[str, dict] = {}
    old_names: dict[str, dict] = {}
    existing_text = ""
    if theme_path.exists():
        existing_text = theme_path.read_text(encoding="utf-8")
        data = yaml.safe_load(existing_text) or {}
        old_ext = data.get("extensions") or {}
        old_names = data.get("filenames") or {}

    final_ext = dict(old_ext)
    final_ext.update(ext_entries)

    final_names = dict(old_names)
    final_names.update(name_entries)

    ext_block = render_block(
        "extensions", final_ext,
        "GENERATED by devtools/iconsgen from neovim mini.icons - do not hand-edit "
        "generated rows",
    )
    name_block = render_block(
        "filenames", final_names,
        "GENERATED by devtools/iconsgen from neovim mini.icons: filenames + "
        "directory icons",
    )

    new_text = splice(existing_text, ext_block, name_block) if existing_text else (
        ext_block + "\n" + name_block
    )

    theme_path.parent.mkdir(parents=True, exist_ok=True)
    theme_path.write_text(new_text, encoding="utf-8")

    print(
        f"wrote {theme_path}\n"
        f"  extensions: {len(final_ext)} ({len(ext_entries)} generated, "
        f"{len(final_ext) - len(ext_entries)} preserved)\n"
        f"  filenames:  {len(final_names)} ({len(name_entries)} generated, "
        f"{len(final_names) - len(name_entries)} preserved)\n"
        f"  collisions skipped: {', '.join(collisions) or 'none'}"
    )


if __name__ == "__main__":
    main()
