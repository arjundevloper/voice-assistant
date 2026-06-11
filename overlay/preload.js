const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // ── Inbound events ────────────────────────────────────────────────────────
  onExpression:   (cb) => ipcRenderer.on('expression',     (_e, v) => cb(v)),
  onSpeechBubble: (cb) => ipcRenderer.on('speech_bubble',  (_e, v) => cb(v)),
  onBlink:        (cb) => ipcRenderer.on('blink',           ()      => cb()),
  onInitSettings: (cb) => ipcRenderer.on('init-settings',  (_e, v) => cb(v)),
  onOverlayResized:(cb)=> ipcRenderer.on('overlay-resized',(_e, v) => cb(v)),
  onMiniMode:     (cb) => ipcRenderer.on('mini-mode',      (_e, v) => cb(v)),
  onGlobalHotkey: (cb) => ipcRenderer.on('global-hotkey',  ()      => cb()),
  onInitHitboxes: (cb) => ipcRenderer.on('init-hitboxes',  (_e, v) => cb(v)),

  // ── Mouse passthrough ─────────────────────────────────────────────────────
  setIgnoreMouse: (ignore) => ipcRenderer.send('set-ignore-mouse', ignore),

  // ── Overlay controls ──────────────────────────────────────────────────────
  resizeOverlay:    (preset, w, h) => ipcRenderer.send('resize-overlay', { preset, width: w, height: h }),
  moveOverlay:      (x, y)         => ipcRenderer.send('move-overlay', { x, y }),
  moveOverlaySide:  (side)         => ipcRenderer.send('move-overlay', { side }),
  setOpacity:       (v)            => ipcRenderer.send('set-opacity', v),
  setAlwaysOnTop:   (v)            => ipcRenderer.send('set-always-on-top', v),
  toggleMini:       ()             => ipcRenderer.send('toggle-mini'),

  // ── Settings ──────────────────────────────────────────────────────────────
  getSettings:      ()             => ipcRenderer.invoke('get-settings'),
  saveSettings:     (data)         => ipcRenderer.send('save-settings', data),
  getOverlayBounds: ()             => ipcRenderer.invoke('get-overlay-bounds'),
  getHitboxes:      ()             => ipcRenderer.invoke('get-hitboxes'),
  saveHitboxes:     (defs)         => ipcRenderer.send('save-hitboxes', defs),
});