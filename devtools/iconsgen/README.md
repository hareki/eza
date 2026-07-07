# iconsgen

Generates the `extensions:` / `filenames:` icon+color overrides in eza's
`theme.yml` so eza's file icons and their colors match what neovim renders via
**mini.icons** (the source of truth) — the same approach used for lazygit
(`.../lazygit/pkg/gui/presentation/icons/iconsgen_ext/`).

**No eza source is modified.** eza stores glyphs only in
`src/output/icons.rs`, and an icon's *color* is normally borrowed from the
filename's color. But a user `theme.yml` can override **both** the icon glyph and
the icon color per extension / filename (and per named directory), so unifying
with neovim is done entirely through a generated `theme.yml`.

## How it works

`nvim --headless` runs [`oracle.lua`](./oracle.lua), which loads mini.icons,
applies this user's personal override, and reports the effective glyph +
highlight group for each key. The Python driver
([`generate.py`](./generate.py)) then:

- reads the keys eza already knows from `src/output/icons.rs` (the three
  `phf_map!` blocks: `DIRECTORY_ICONS`, `FILENAME_ICONS`, `EXTENSION_ICONS`),
- adds the few keys defined only in the personal mini.icons override,
- asks the oracle for each one's glyph + color,
- **skips** keys mini.icons has only its generic default for (leaving eza's
  built-in icon), except the personal-override keys,
- maps mini.icons highlight groups to catppuccin-mocha hex, with the personal
  `MiniIconsAzure → teal` override (so Azure and Cyan both become teal),
- writes `extensions:` (file extensions) and `filenames:` (filenames **and**
  directory names) into `theme.yml`.

Glyphs are written by Python's own UTF-8 file I/O, so no editor glyph
sanitization occurs.

### Preserves the rest of your theme

Only the `extensions:` / `filenames:` blocks are regenerated. Every other
section (`filekinds`, `perms`, `git`, …) is spliced back verbatim, and your
manual entries for keys mini.icons doesn't cover are kept.

### Directories never inherit an extension icon (source fix)

eza's `File::ext` counts dotfiles (`.git`→`git`, `cron.d`→`d`) and its
`style_override` used to consult the `extensions` map by `file.ext` for
directories too, so an `extensions:` entry could leak onto a directory whose
name ends in that extension (e.g. `build.d`, systemd `foo.service.d`). This is
fixed in eza source ([`src/theme/mod.rs`](../../src/theme/mod.rs)
`style_override`): the extension branch is skipped when
`file.points_to_directory()`. Directories are therefore styled only by an
explicit `filenames` entry (mini.icons' real directory icons) or eza's built-in
folder icon — never by extension. No shadowing guards are emitted.

> Re-apply that one-line guard after an upstream merge that rewrites
> `style_override`.

## Sources of truth (read, never modified)

- mini.icons plugin — default icon tables + resolver.
- `.../nvim/lua/core/mini-icons.lua` — personal override. **If you change this
  file's icon tables or the Azure→teal recolor, mirror it in `oracle.lua` /
  `HL_TO_HEX` before regenerating.**
- `.../nvim/lua/config/icons.lua` — glyph values the override references (read
  directly by `oracle.lua`, so glyph edits there flow through automatically).

## Run

Requires `nvim` on `PATH` with mini.icons installed, and PyYAML
(`python3 -m pip install pyyaml`).

```sh
python3 devtools/iconsgen/generate.py
```

Writes to `$XDG_CONFIG_HOME/eza/theme.yml` (default `~/.config/eza/theme.yml`).
Overrides:

```sh
MINI_ICONS_PATH=/path/to/mini.icons \
ICONS_LUA_PATH=/path/to/nvim/lua/config/icons.lua \
EZA_THEME_OUT=/path/to/theme.yml \
  python3 devtools/iconsgen/generate.py
# or: --theme PATH / --icons-rs PATH
```

The generator is idempotent — re-running with an unchanged neovim config and a
stable existing theme produces no diff.

## Verify

```sh
# YAML validity
python3 -c "import yaml; yaml.safe_load(open('$HOME/.config/eza/theme.yml'))"

# behavioral: glyph + color actually applied (eza silently ignores a malformed
# theme, so observe the output, don't just check the exit code)
mkdir -p /tmp/izt && : > /tmp/izt/a.rs && : > /tmp/izt/a.ts && mkdir -p /tmp/izt/.git
eza --icons=always --color=always -a /tmp/izt
```

Cross-check a glyph against neovim directly:

```vim
:lua print(vim.inspect({ require('mini.icons').get('file', 'a.rs') }))
```
