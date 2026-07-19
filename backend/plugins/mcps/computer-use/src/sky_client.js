// sky_client.js
// Direct JSON-RPC client for OpenAI `codex-computer-use.exe` (the @oai/sky Windows backend).
//
// Protocol (reverse-engineered + verified against the binary; matches the proven
// Python reference in this skill's scripts/sky_client.py):
//   - Spawn the exe with `--parent-pid <pid>`.
//   - Each request is a single-line JSON object terminated by "\n":
//       { "id": <number>, "method": "<method>", "params": { ... },
//         "meta": { "x-oai-cua-approved-app": "<app variant>" } }
//   - Each response is a single-line JSON object:
//       { "id": <number>, "ok": true,  "result": <any> }
//       { "id": <number>, "ok": false, "error": "<string>" }
//       { "id": <number>, "ok": false, "approvalRequest": { "app": "...", "displayName": "...", "riskLevel": "low"|"high" } }
//   - Approval is NOT a separate response. When a request returns an
//     `approvalRequest`, the client RE-SENDS the same request with a
//     `meta.x-oai-cua-approved-app` header set to a candidate app identifier
//     (e.g. "process:C:\\path\\App.exe", "App" / the .exe stem, or the raw id).
//     The exe accepts the request once the approved-app matches.
//   - `close` shuts the helper down.
//
// The exe is shipped inside this skill at scripts/codex-computer-use.exe. Any
// MCP-capable, vision-capable agent can now drive the Windows GUI through this client.

import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import { existsSync } from "node:fs";
import os from "node:os";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Location of the bundled computer-use helper executable.
// 按优先级搜索多个候选位置，兼容不同的安装布局：
//   1) COMPUTER_USE_EXE 环境变量（显式覆盖）
//   2) ../codex-computer-use.exe        -- 插件自包含布局（src/ 上一级，即插件根目录）
//   3) ../../codex-computer-use.exe     -- 原始开发布局（src/ 上两级，即 resources/）
//   4) ~/.Aries/plugins/mcps/computer-use/codex-computer-use.exe -- Aries 用户目录布局
function _resolveExePath() {
  if (process.env.COMPUTER_USE_EXE) return process.env.COMPUTER_USE_EXE;
  const candidates = [
    path.join(__dirname, "..", "codex-computer-use.exe"),
    path.join(__dirname, "..", "..", "codex-computer-use.exe"),
    path.join(os.homedir(), ".Aries", "plugins", "mcps", "computer-use", "codex-computer-use.exe"),
  ];
  for (const c of candidates) {
    try {
      if (existsSync(c)) return c;
    } catch {
      /* ignore */
    }
  }
  // 全部找不到时回退到原始默认（保留原行为，便于上层报错信息一致）
  return path.join(__dirname, "..", "..", "codex-computer-use.exe");
}

const DEFAULT_EXE = _resolveExePath();

const REQUEST_TIMEOUT_MS = 60000;

// 空闲多久后自动关闭 codex-computer-use.exe（撤掉屏幕控制层）。
// Cursor 等 MCP 宿主会常驻本 server，若不主动 close，控制样式会一直挂着。
// 默认 120s：截图经 MCP→模型往返常超过 15s，过短会在 click 前把会话 release 掉。
const IDLE_MS = Math.max(
  1000,
  Number(process.env.COMPUTER_USE_IDLE_MS || 120000),
);

/**
 * 归一化 app / process 路径。
 * Agent 常从 JSON 文本里抄出 `D:\\foo`（字面双反斜杠），而 exe 登记的是 `D:\foo`，
 * 会导致 "window id no longer belongs to process:..."。
 */
export function normalizeAppId(app) {
  if (app == null || typeof app !== "string") return app;
  let s = app.trim();
  // 反复折叠反斜杠，直到稳定（处理 \\\\ → \\ → \）
  for (let i = 0; i < 8; i++) {
    const next = s.replace(/\\\\/g, "\\");
    if (next === s) break;
    s = next;
  }
  // process: 前缀后的盘符路径统一为正斜杠再转回反斜杠，避免混用
  if (/^process:[a-zA-Z]:/i.test(s)) {
    const body = s.slice("process:".length).replace(/\//g, "\\");
    s = "process:" + body;
  } else if (/^[a-zA-Z]:[\\/]/.test(s)) {
    s = s.replace(/\//g, "\\");
  }
  return s;
}

export function normalizeWindow(window) {
  if (!window || typeof window !== "object") return window;
  const out = { ...window };
  if (out.app) out.app = normalizeAppId(out.app);
  return out;
}

function windowKey(window) {
  if (!window) return "";
  return `${normalizeAppId(window.app) || ""}#${window.id}`;
}

function isStaleWindowError(err) {
  const m = String(err?.message || err || "");
  return (
    /get_window_state before/i.test(m) ||
    /no longer belongs to process/i.test(m) ||
    /no longer exists/i.test(m)
  );
}

export class SkyClient {
  constructor({ exePath = DEFAULT_EXE, autoApprove = true } = {}) {
    this.exePath = exePath;
    this.autoApprove = autoApprove;
    this.child = null;
    this.nextId = 1;
    this.pending = new Map();
    this.buffer = "";
    this.closed = false;
    /** @type {Map<string, string>} windowKey -> last screenshotId from get_window_state */
    this._lastScreenshotId = new Map();
  }

  isAlive() {
    return Boolean(this.child && this.child.exitCode == null && !this.closed);
  }

  start() {
    if (this.isAlive()) return;
    this.child = null;
    this.closed = false;
    this.buffer = "";
    this.child = spawn(this.exePath, ["--parent-pid", String(process.pid)], {
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });

    this.child.stdout.setEncoding("utf8");
    this.child.stdout.on("data", (chunk) => this._onData(chunk));
    this.child.stderr.on("data", (d) =>
      process.stderr.write(`[computer-use] ${d}`),
    );
    this.child.on("exit", (code, signal) => {
      this.closed = true;
      this.child = null;
      const err = new Error(
        `codex-computer-use.exe exited (code=${code}, signal=${signal})`,
      );
      for (const [, p] of this.pending) {
        clearTimeout(p.timer);
        p.reject(err);
      }
      this.pending.clear();
    });
    this.child.on("error", (err) => {
      process.stderr.write(`[computer-use] spawn error: ${err.message}\n`);
    });
    process.stderr.write(
      `[computer-use] started codex-computer-use.exe (idle release=${IDLE_MS}ms)\n`,
    );
  }

  _onData(chunk) {
    this.buffer += chunk;
    let idx;
    while ((idx = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, idx).trim();
      this.buffer = this.buffer.slice(idx + 1);
      if (!line) continue;
      let msg;
      try {
        msg = JSON.parse(line);
      } catch {
        continue; // ignore non-JSON frames
      }
      const p = this.pending.get(msg.id);
      if (!p) continue;
      clearTimeout(p.timer);
      this.pending.delete(msg.id);
      // ok=true → result; ok=false with error → reject; ok=false with
      // approvalRequest → resolve so the caller can retry with approval meta.
      if (msg.ok) p.resolve(msg.result);
      else if (msg.error != null) p.reject(new Error(msg.error));
      else p.resolve(msg); // approvalRequest (no error, no ok)
    }
  }

  _write(obj) {
    if (!this.child) throw new Error("computer-use client not started");
    this.child.stdin.write(JSON.stringify(obj) + "\n");
  }

  // Build plausible x-oai-cua-approved-app values from an app identifier.
  _approvalCandidates(raw) {
    const seen = new Set();
    const out = [];
    const add = (v) => {
      const t = (v || "").trim();
      if (t && !seen.has(t)) {
        seen.add(t);
        out.push(t);
      }
    };
    if (!raw) return out;
    add(raw);
    const lower = raw.toLowerCase();
    if (lower.endsWith(".exe")) {
      if (!lower.startsWith("process:")) add("process:" + raw);
      const stem = raw.replace(/^[a-z]:\\/i, "").split(/[\\/]/).pop();
      add(stem.replace(/\.exe$/i, ""));
    } else if (lower.startsWith("process:")) {
      add(raw.slice("process:".length));
      const inner = raw.slice("process:".length);
      if (/\.exe$/i.test(inner)) add(inner.replace(/\.exe$/i, ""));
    }
    return out;
  }

  _appOf(params) {
    const w = params && params.window;
    if (w && w.app) return normalizeAppId(w.app);
    if (params && params.app) return normalizeAppId(params.app);
    return "";
  }

  // Send one request with an optional approval-app header.
  _callOnce(method, params, approveApp) {
    if (!this.isAlive()) {
      if (method === "close") return Promise.resolve(null);
      this.start();
    }
    const id = this.nextId++;
    const obj = { id, method, params };
    if (approveApp) obj.meta = { "x-oai-cua-approved-app": approveApp };
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`computer-use request timed out: ${method}`));
        }
      }, REQUEST_TIMEOUT_MS);
      this.pending.set(id, { resolve, reject, timer });
      this._write(obj);
    });
  }

  // Send a request, transparently retrying with approval headers until the
  // exe accepts it (or we run out of candidate app identifiers).
  async call(method, params = {}) {
    if (!this.autoApprove) {
      return this._callOnce(method, params, "");
    }
    const candidates = this._approvalCandidates(this._appOf(params));
    // If there is nothing to pre-approve with, still send the request once
    // (no approval header); the exe may not require approval at all.
    if (candidates.length === 0) candidates.push("");
    let last;
    for (const cand of candidates) {
      last = await this._callOnce(method, params, cand);
      if (!(last && last.approvalRequest)) return last;
      // Augment candidate list with variants from the approvalRequest itself.
      const a = last.approvalRequest;
      for (const v of this._approvalCandidates(
        a.app || a.displayName || a.processPath,
      )) {
        if (!candidates.includes(v)) candidates.push(v);
      }
    }
    // Last response was still an approvalRequest with no accepted variant.
    if (last && last.approvalRequest) {
      const a = last.approvalRequest;
      throw new Error(
        `Computer-use approval denied for app "${a.app || a.displayName || "?"}". ` +
          `Try passing an explicit .exe path or app id for this window.`,
      );
    }
    return last;
  }

  async close() {
    if (!this.child || this.closed) {
      this.child = null;
      this.closed = false;
      return;
    }
    const proc = this.child;
    try {
      // 先发 close RPC，给 exe 时间撤掉控制层，再 kill
      await Promise.race([
        this._callOnce("close", {}, ""),
        new Promise((r) => setTimeout(r, 2000)),
      ]);
    } catch {
      // ignore
    }
    try {
      proc.kill();
    } catch {
      // ignore
    }
    // 等进程真正退出，避免残留控制层
    try {
      await Promise.race([
        new Promise((resolve) => {
          if (proc.exitCode != null) resolve();
          else proc.once("exit", resolve);
        }),
        new Promise((r) => setTimeout(r, 3000)),
      ]);
    } catch {
      // ignore
    }
    this.child = null;
    this.closed = false; // 允许下次 getClient() 重新 start
    this.buffer = "";
    process.stderr.write("[computer-use] released codex-computer-use.exe\n");
  }

  // ── High-level helpers mirroring @oai/sky Window2 API ──

  async listWindows() {
    const windows = await this.call("list_windows", {});
    if (!Array.isArray(windows)) return windows;
    return windows.map((w) =>
      w && w.app ? { ...w, app: normalizeAppId(w.app) } : w,
    );
  }

  async listApps() {
    const apps = await this.call("list_apps", {});
    if (!Array.isArray(apps)) return [];
    return apps
      .map((app) => {
        if (!app || typeof app.id !== "string" || !app.id.trim()) return null;
        const win = Array.isArray(app.windows)
          ? app.windows.map((w) => ({
              app: normalizeAppId(
                w.app && w.app.trim() ? w.app : app.id,
              ),
              id: w.id,
              ...(w.title !== undefined ? { title: w.title } : {}),
            }))
          : [];
        return {
          id: normalizeAppId(app.id),
          ...(app.displayName !== undefined
            ? { displayName: app.displayName }
            : {}),
          ...(typeof app.isRunning === "boolean"
            ? { isRunning: app.isRunning }
            : {}),
          ...(app.lastUsedDate !== undefined
            ? { lastUsedDate: app.lastUsedDate }
            : {}),
          ...(typeof app.useCount === "number"
            ? { useCount: app.useCount }
            : {}),
          windows: win,
        };
      })
      .filter(Boolean);
  }

  async launchApp(appId) {
    await this.call("launch_app", { app: normalizeAppId(appId) });
  }

  async activateWindow(window) {
    await this.call("activate_window", { window: normalizeWindow(window) });
  }

  async getWindow({ app, id }) {
    const params = { id };
    if (app) params.app = normalizeAppId(app);
    const win = await this.call("get_window", params);
    if (win && win.app) win.app = normalizeAppId(win.app);
    return win;
  }

  _rememberScreenshots(window, st) {
    const shots =
      st?.screenshots && Array.isArray(st.screenshots)
        ? st.screenshots
        : st?.screenshot
          ? [st.screenshot]
          : [];
    const sid = shots[0]?.id || shots[0]?.screenshotId || null;
    if (sid) this._lastScreenshotId.set(windowKey(window), String(sid));
    return shots.map((s, i) => ({
      id: s.id || s.screenshotId || (i === 0 ? "screenshot-0" : `screenshot-${i}`),
      raw: s,
    }));
  }

  resolveScreenshotId(window, screenshotId) {
    if (screenshotId) return screenshotId;
    return this._lastScreenshotId.get(windowKey(window)) || "screenshot-0";
  }

  async getWindowState(
    window,
    { includeScreenshot = true, includeText = true } = {},
  ) {
    if (!includeScreenshot && !includeText) {
      throw new Error(
        "get_window_state requires at least one of includeScreenshot/includeText",
      );
    }
    window = normalizeWindow(window);
    const params = { window, include_screenshot: includeScreenshot };
    if (includeText) params.include_text = true;
    const st = await this.call("get_window_state", params);
    this._rememberScreenshots(window, st);
    return st;
  }

  async _ensureWindowReady(window) {
    window = normalizeWindow(window);
    await this.getWindowState(window, {
      includeScreenshot: true,
      includeText: false,
    });
    return window;
  }

  async click(window, opts = {}) {
    window = normalizeWindow(window);
    const run = async (o) => {
      const params = { window };
      if (o.elementIndex !== undefined && o.elementIndex !== null) {
        params.element_index = o.elementIndex;
        params.click_count = o.clickCount ?? 1;
        params.mouse_button = o.mouseButton || "left";
        await this.call("click_element", params);
        return;
      }
      if (o.x === undefined || o.y === undefined) {
        throw new Error("click requires elementIndex or x+y coordinates");
      }
      params.x = Math.round(o.x);
      params.y = Math.round(o.y);
      params.click_count = o.clickCount ?? 1;
      params.mouse_button = o.mouseButton || "left";
      params.screenshotId = this.resolveScreenshotId(window, o.screenshotId);
      await this.call("click", params);
    };
    try {
      await run(opts);
    } catch (e) {
      if (!isStaleWindowError(e)) throw e;
      process.stderr.write(
        `[computer-use] click stale (${e.message}); re-get_window_state and retry\n`,
      );
      await this._ensureWindowReady(window);
      await run({ ...opts, screenshotId: undefined });
    }
  }

  async typeText(window, text) {
    window = normalizeWindow(window);
    try {
      await this.call("type_text", { window, text });
    } catch (e) {
      if (!isStaleWindowError(e)) throw e;
      await this._ensureWindowReady(window);
      await this.call("type_text", { window, text });
    }
  }

  async pressKey(window, key) {
    window = normalizeWindow(window);
    try {
      await this.call("press_key", { window, key });
    } catch (e) {
      if (!isStaleWindowError(e)) throw e;
      await this._ensureWindowReady(window);
      await this.call("press_key", { window, key });
    }
  }

  async scroll(window, { x, y, scrollX, scrollY, screenshotId }) {
    window = normalizeWindow(window);
    const run = async (sid) => {
      const params = {
        window,
        x: Math.round(x),
        y: Math.round(y),
        scrollX: Math.round(scrollX ?? 0),
        scrollY: Math.round(scrollY ?? 0),
        screenshotId: this.resolveScreenshotId(window, sid),
      };
      await this.call("scroll", params);
    };
    try {
      await run(screenshotId);
    } catch (e) {
      if (!isStaleWindowError(e)) throw e;
      await this._ensureWindowReady(window);
      await run(undefined);
    }
  }

  async setValue(window, elementIndex, value) {
    window = normalizeWindow(window);
    try {
      await this.call("set_value", {
        window,
        element_index: elementIndex,
        value,
      });
    } catch (e) {
      if (!isStaleWindowError(e)) throw e;
      await this._ensureWindowReady(window);
      await this.call("set_value", {
        window,
        element_index: elementIndex,
        value,
      });
    }
  }

  async drag(window, { fromX, fromY, toX, toY, screenshotId }) {
    window = normalizeWindow(window);
    const run = async (sid) => {
      const params = {
        window,
        from_x: Math.round(fromX),
        from_y: Math.round(fromY),
        to_x: Math.round(toX),
        to_y: Math.round(toY),
        screenshotId: this.resolveScreenshotId(window, sid),
      };
      await this.call("drag", params);
    };
    try {
      await run(screenshotId);
    } catch (e) {
      if (!isStaleWindowError(e)) throw e;
      await this._ensureWindowReady(window);
      await run(undefined);
    }
  }

  async performSecondaryAction(window, action, elementIndex) {
    window = normalizeWindow(window);
    try {
      await this.call("perform_secondary_action", {
        window,
        action,
        element_index: elementIndex,
      });
    } catch (e) {
      if (!isStaleWindowError(e)) throw e;
      await this._ensureWindowReady(window);
      await this.call("perform_secondary_action", {
        window,
        action,
        element_index: elementIndex,
      });
    }
  }
}

// Singleton accessor：按需启动；空闲超时后 close，下次工具调用再拉起。
let _client = null;
let _idleTimer = null;

export function getClient() {
  if (!_client) _client = new SkyClient();
  if (!_client.isAlive()) _client.start();
  // 调用期间先取消空闲计时，避免长耗时工具（截图）中途被 release
  cancelIdleTimer();
  return _client;
}

/** 关闭 exe 并撤掉屏幕控制层。幂等。 */
export async function releaseClient() {
  cancelIdleTimer();
  if (!_client) return;
  await _client.close();
}

/** 进程退出钩子用：同步强杀，不发 RPC。 */
export function forceKillClient() {
  cancelIdleTimer();
  if (!_client || !_client.child) return;
  try {
    _client.child.kill();
  } catch {
    // ignore
  }
  _client.child = null;
  _client.closed = false;
  _client.buffer = "";
}

export function cancelIdleTimer() {
  if (_idleTimer) {
    clearTimeout(_idleTimer);
    _idleTimer = null;
  }
}

/** 每次工具调用后重置空闲计时；超时则自动 release。 */
export function touchClientActivity() {
  cancelIdleTimer();
  _idleTimer = setTimeout(() => {
    process.stderr.write(
      `[computer-use] idle ${IDLE_MS}ms — releasing control overlay\n`,
    );
    releaseClient().catch((e) => {
      process.stderr.write(
        `[computer-use] idle release failed: ${e?.message || e}\n`,
      );
    });
  }, IDLE_MS);
}
