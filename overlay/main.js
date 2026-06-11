/**
 * overlay/main.js — Emi OS v6 Electron main process
 * New in v6:
 *   - Global hotkey (Ctrl+Shift+E) to focus/wake Emi
 *   - System tray icon with context menu
 *   - Mini mode (140×140 compact bubble)
 *   - Auto-saves window position on move
 *   - IPC: resize, move, opacity, mini-mode, send-command
 */

const { app, BrowserWindow, ipcMain, screen, globalShortcut, Tray, Menu, nativeImage } = require('electron');
const path = require('path');
const fs   = require('fs');

const SETTINGS_PATH = path.join(__dirname, '..', 'data', 'settings.json');
const HITBOXES_PATH = path.join(__dirname, '..', 'data', 'hitboxes.json');

function loadHitboxes() {
  try {
    const raw = JSON.parse(fs.readFileSync(HITBOXES_PATH, 'utf8'));
    return Array.isArray(raw) ? raw : (raw.default || []);
  } catch(e) { console.error('hitboxes load error:', e.message); return []; }
}
function saveHitboxes(defs) {
  try { fs.writeFileSync(HITBOXES_PATH, JSON.stringify({ default: defs }, null, 2), 'utf8'); }
  catch(e) { console.error('hitboxes save error:', e.message); }
}

const PRESETS = {
  tiny:   { w: 200, h: 325 },
  small:  { w: 240, h: 390 },
  medium: { w: 280, h: 455 },
  large:  { w: 320, h: 520 },
  xlarge: { w: 380, h: 620 },
};
const MINI = { w: 140, h: 140 };

let trayRebuild = null; // set by createTray so toggleMini can call it

let tray;
let isMini = false;
let normalBounds = null;

// ── Settings helpers ──────────────────────────────────────────────────────────
function loadSettings() {
  try { return JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf8')); }
  catch { return {}; }
}
function saveSettings(patch) {
  try {
    const cur = loadSettings();
    const merged = deepMerge(cur, patch);
    fs.writeFileSync(SETTINGS_PATH, JSON.stringify(merged, null, 2), 'utf8');
  } catch(e) { console.error('settings save error:', e.message); }
}
function deepMerge(base, over) {
  const r = Object.assign({}, base);
  for (const k of Object.keys(over)) {
    if (over[k] && typeof over[k] === 'object' && !Array.isArray(over[k]) &&
        r[k]   && typeof r[k]   === 'object') {
      r[k] = deepMerge(r[k], over[k]);
    } else {
      r[k] = over[k];
    }
  }
  return r;
}

// ── Window factory ────────────────────────────────────────────────────────────
function createWindow() {
  const settings = loadSettings();
  const ov  = settings.overlay || {};
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;

  const preset = (ov.size_preset || 'large').toLowerCase();
  const dim    = PRESETS[preset] || { w: ov.width || 320, h: ov.height || 520 };
  const W = dim.w, H = dim.h;
  const X = (ov.x >= 0) ? ov.x : sw - W - 20;
  const Y = (ov.y >= 0) ? ov.y : sh - H - 20;

  normalBounds = { x: X, y: Y, w: W, h: H };

  mainWindow = new BrowserWindow({
    width: W, height: H, x: X, y: Y,
    frame: false, transparent: true,
    alwaysOnTop: ov.always_on_top !== false,
    resizable: false, skipTaskbar: true,
    hasShadow: false, backgroundColor: '#00000000',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'overlay.html'));
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    // Tell renderer initial dimensions + settings
    mainWindow.webContents.send('init-settings', settings);
    // Send hitboxes from JSON file
    const hitboxes = loadHitboxes();
    if (hitboxes.length) mainWindow.webContents.send('init-hitboxes', hitboxes);
  });

  mainWindow.setIgnoreMouseEvents(true, { forward: true });

  // Save position on move
  mainWindow.on('moved', () => {
    if (isMini) return;
    const [x, y] = mainWindow.getPosition();
    saveSettings({ overlay: { x, y } });
  });
}

// ── System tray ───────────────────────────────────────────────────────────────
function createTray() {
  // Minimal 16×16 transparent PNG as fallback icon
  const icon = nativeImage.createEmpty();
  try {
    const iconPath = path.join(__dirname, '..', 'assets', 'icon.png');
    if (fs.existsSync(iconPath)) {
      tray = new Tray(iconPath);
    } else {
      tray = new Tray(icon);
    }
  } catch {
    tray = new Tray(icon);
  }

  const rebuildMenu = () => {
    const menu = Menu.buildFromTemplate([
      { label: 'Emi OS v6', enabled: false },
      { type: 'separator' },
      { label: isMini ? 'Expand' : 'Mini mode', click: () => toggleMini() },
      { label: 'Show / Hide', click: () => {
          if (mainWindow.isVisible()) mainWindow.hide();
          else mainWindow.show();
        }
      },
      { type: 'separator' },
      { label: 'Quit Emi', click: () => app.quit() },
    ]);
    tray.setContextMenu(menu);
    tray.setToolTip('Emi OS v6');
  };
  trayRebuild = rebuildMenu; // expose for toggleMini

  tray.on('click', () => {
    if (mainWindow.isVisible()) mainWindow.focus();
    else mainWindow.show();
  });
  rebuildMenu();
}

// ── Mini mode ─────────────────────────────────────────────────────────────────
function toggleMini() {
  if (!mainWindow) return;
  isMini = !isMini;

  if (isMini) {
    const [x, y] = mainWindow.getPosition();
    const [w, h] = mainWindow.getSize();
    normalBounds = { x, y, w, h };
    // Slide to bottom-right corner
    const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
    mainWindow.setSize(MINI.w, MINI.h);
    mainWindow.setPosition(sw - MINI.w - 10, sh - MINI.h - 10);
  } else {
    const { x, y, w, h } = normalBounds || {};
    if (w) mainWindow.setSize(w, h);
    if (x != null) mainWindow.setPosition(x, y);
  }

  mainWindow.webContents.send('mini-mode', isMini);
  // In mini mode the tiny circle must always be clickable (for dblclick expand)
  if (isMini) mainWindow.setIgnoreMouseEvents(false);
  saveSettings({ overlay: { mini_mode: isMini } });
  if (trayRebuild) trayRebuild(); // keep tray label in sync
}

// ── IPC handlers ──────────────────────────────────────────────────────────────
ipcMain.on('set-ignore-mouse', (_e, ignore) => {
  if (mainWindow) mainWindow.setIgnoreMouseEvents(ignore, { forward: true });
});

ipcMain.on('resize-overlay', (_e, { preset, width, height }) => {
  if (!mainWindow || isMini) return;
  let w, h;
  if (preset && PRESETS[preset]) { w = PRESETS[preset].w; h = PRESETS[preset].h; }
  else { w = Math.max(180, Math.min(width || 320, 600)); h = Math.max(220, Math.min(height || 520, 800)); }
  mainWindow.setSize(w, h);
  normalBounds = Object.assign(normalBounds || {}, { w, h });
  saveSettings({ overlay: { width: w, height: h, size_preset: preset || 'custom' } });
  mainWindow.webContents.send('overlay-resized', { width: w, height: h });
});

ipcMain.on('move-overlay', (_e, { x, y, side }) => {
  if (!mainWindow || isMini) return;
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  const [w, h] = mainWindow.getSize();
  let nx = x, ny = y;
  if (side === 'right')  { nx = sw - w - 10; ny = sh - h - 10; }
  if (side === 'left')   { nx = 10;           ny = sh - h - 10; }
  if (side === 'center') { nx = (sw - w) / 2; ny = (sh - h) / 2; }
  if (side === 'top-right')  { nx = sw - w - 10; ny = 10; }
  if (side === 'top-left')   { nx = 10;           ny = 10; }
  mainWindow.setPosition(Math.round(nx), Math.round(ny));
  saveSettings({ overlay: { x: Math.round(nx), y: Math.round(ny) } });
});

ipcMain.on('set-opacity', (_e, opacity) => {
  if (!mainWindow) return;
  const v = Math.max(0.15, Math.min(1.0, opacity));
  mainWindow.setOpacity(v);
  saveSettings({ overlay: { opacity: v } });
});

ipcMain.on('set-always-on-top', (_e, val) => {
  if (!mainWindow) return;
  mainWindow.setAlwaysOnTop(val);
  saveSettings({ overlay: { always_on_top: val } });
});

ipcMain.on('toggle-mini', () => toggleMini());

ipcMain.on('save-settings', (_e, patch) => saveSettings(patch));

ipcMain.handle('get-settings', () => loadSettings());
ipcMain.handle('get-hitboxes', () => loadHitboxes());
ipcMain.on('save-hitboxes', (_e, defs) => saveHitboxes(defs));
ipcMain.handle('get-overlay-bounds', () => {
  if (!mainWindow) return null;
  const [x, y] = mainWindow.getPosition();
  const [w, h] = mainWindow.getSize();
  return { x, y, width: w, height: h, opacity: mainWindow.getOpacity(), mini: isMini };
});

// ── Bootstrap ─────────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  createWindow();
  createTray();

  // Global hotkey — wake Emi / focus window
  const settings = loadSettings();
  const hotkey = settings.hotkey || 'CommandOrControl+Shift+E';
  try {
    globalShortcut.register(hotkey, () => {
      if (!mainWindow) return;
      // Always un-ignore mouse events so the renderer can receive focus
      mainWindow.setIgnoreMouseEvents(false);
      if (mainWindow.isVisible()) {
        mainWindow.focus();
        mainWindow.webContents.send('global-hotkey');
      } else {
        mainWindow.show();
        mainWindow.focus();
        mainWindow.webContents.send('global-hotkey');
      }
    });
  } catch(e) { console.error('Hotkey registration failed:', e.message); }
});

app.on('will-quit', () => globalShortcut.unregisterAll());

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});