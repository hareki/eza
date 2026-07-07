-- Oracle for the eza icon/theme generator.
--
-- Adapted from lazygit's iconsgen_ext/oracle.lua. Run by
-- `nvim --headless -l oracle.lua`. It loads mini.icons, applies the user's
-- personal mini.icons override (mirrored from the neovim config), then resolves
-- each requested name and reports mini.icons' effective glyph + highlight group.
-- Highlight groups are mapped to catppuccin colors by the Python driver, so
-- catppuccin itself need not be loaded here.
--
-- Environment:
--   MINI_ICONS_PATH  path to the mini.icons plugin root (added to runtimepath)
--   ICONS_LUA_PATH   path to config/icons.lua (returns a table with .file_icons)
--   QUERIES_PATH     input file; each line is "<id>\t<category>\t<name>"
--                    where <category> is "file" or "directory"
--   RESULTS_PATH     output file; each line is "<id>\t<glyph>\t<hl>\t<is_default>"

local function env(name)
  local v = os.getenv(name)
  assert(v ~= nil and v ~= '', name .. ' is not set')
  return v
end

local mini_path = env('MINI_ICONS_PATH')
local icons_lua = env('ICONS_LUA_PATH')
local queries_path = env('QUERIES_PATH')
local results_path = env('RESULTS_PATH')

vim.opt.runtimepath:append(mini_path)
local MiniIcons = require('mini.icons')

-- Glyphs come from the real config so the oracle stays in sync with neovim.
local cfg = assert(dofile(icons_lua), 'failed to load ' .. icons_lua)
local fi = assert(cfg.file_icons, 'icons.lua has no file_icons table')

-- Mirror ~/.config/nvim/lua/core/mini-icons.lua exactly (icon tables only; the
-- MiniIconsAzure -> teal recolor is handled by the Python driver's hl mapping).
MiniIcons.setup({
  extension = {
    dbml = { glyph = fi.SQL, hl = 'MiniIconsAzure' },
    ico = { glyph = fi.ICO, hl = 'MiniIconsGreen' },
    scm = { glyph = fi.SCHEME, hl = 'MiniIconsGrey' },
    mdx = { glyph = fi.MARKDOWN, hl = 'MiniIconsYellow' },
  },
  file = {
    ['.keep'] = { glyph = fi.KEEP, hl = 'MiniIconsGrey' },
    ['devcontainer.json'] = { glyph = fi.DEVCONTAINER, hl = 'MiniIconsAzure' },
    ['.eslintrc.js'] = { glyph = fi.ESLINT, hl = 'MiniIconsYellow' },
    ['.node-version'] = { glyph = fi.NODE_VERSION, hl = 'MiniIconsGreen' },
    ['.prettierrc'] = { glyph = fi.PRETTIERRC, hl = 'MiniIconsPurple' },
    ['.yarnrc.yml'] = { glyph = fi.YARNRC, hl = 'MiniIconsBlue' },
    ['eslint.config.js'] = { glyph = fi.ESLINT_CONFIG, hl = 'MiniIconsYellow' },
    ['package.json'] = { glyph = fi.PACKAGE_JSON, hl = 'MiniIconsGreen' },
    ['tsconfig.json'] = { glyph = fi.TSCONFIG, hl = 'MiniIconsAzure' },
    ['tsconfig.build.json'] = { glyph = fi.TSCONFIG_BUILD, hl = 'MiniIconsAzure' },
    ['yarn.lock'] = { glyph = fi.YARN_LOCK, hl = 'MiniIconsBlue' },
  },
  filetype = {
    env = { glyph = fi.DOTENV, hl = 'MiniIconsYellow' },
    dotenv = { glyph = fi.DOTENV, hl = 'MiniIconsYellow' },
    sql = { glyph = fi.SQL, hl = 'MiniIconsYellow' },
    text = { glyph = fi.TEXT, hl = 'MiniIconsGrey' },
  },
})

local out = assert(io.open(results_path, 'w'))
for line in io.lines(queries_path) do
  if line ~= '' then
    local id, category, name = line:match('^(%d+)\t(%a+)\t(.*)$')
    assert(id ~= nil, 'malformed query line: ' .. line)
    -- 'file' runs mini.icons' filename -> file table -> extension ->
    -- vim.filetype.match fallback chain (how a real file renders); 'directory'
    -- resolves against the directory table.
    local icon, hl, is_default = MiniIcons.get(category, name)
    out:write(string.format('%s\t%s\t%s\t%s\n', id, icon or '', hl or '', tostring(is_default)))
  end
end
out:close()
