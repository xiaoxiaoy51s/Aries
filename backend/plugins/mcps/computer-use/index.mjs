// index.mjs — MCP server exposing the OpenAI @oai/sky (codex-computer-use) Windows
// GUI-automation backend as a set of tools. Any MCP-capable, vision-capable agent
// can drive the local Windows GUI through this server.
//
// The heavy lifting lives in src/sky_client.js, which spawns the bundled
// codex-computer-use.exe and speaks its newline-delimited JSON-RPC protocol,
// transparently handling the x-oai-cua-approved-app approval handshake.
//
// Screenshots returned by get_window_state / screenshots are emitted as MCP image
// content blocks (base64 PNG) so a vision model can see the screen.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { getClient, releaseClient, forceKillClient, touchClientActivity, normalizeAppId } from "./src/sky_client.js";

// 懒代理：首次访问工具方法时才启动 codex-computer-use.exe；
// 每次调用会刷新空闲计时，超时后自动 close 撤掉控制层。
const client = new Proxy(
  {},
  {
    get(_target, prop) {
      const c = getClient();
      const v = c[prop];
      return typeof v === "function" ? v.bind(c) : v;
    },
  },
);

// Coerce number-or-string to number. Some MCP clients serialize numeric args
// as JSON strings, so we accept both at the zod layer and convert here.
const Num = z
  .union([z.number(), z.string()])
  .transform((v, ctx) => {
    const n = Number(v);
    if (!Number.isFinite(n)) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "expected a number" });
      return z.NEVER;
    }
    return n;
  });
const Int = Num.transform((n) => Math.trunc(n));

/** Agent 从 JSON 文本抄路径时常带双反斜杠；统一折叠。 */
const AppId = z.string().transform((s) => normalizeAppId(s));

function winArgs(app, id) {
  return { app: normalizeAppId(app), id };
}

// Wrap a promise so tool errors surface as MCP error text instead of crashing
// the server. 工具结束后再启动空闲计时（截图等长操作不会中途被 release）。
async function guard(fn) {
  try {
    const result = await fn();
    touchClientActivity();
    return result;
  } catch (e) {
    touchClientActivity();
    return { content: [{ type: "text", text: `Error: ${e.message}` }] };
  }
}

const server = new McpServer({
  name: "computer-use-sky",
  version: "1.0.0",
});

const WORKFLOW_HINT =
  " Workflow: list_windows → get_window_state(includeScreenshot=true) → interact. " +
  "Prefer elementIndex from the tree; for x/y clicks pass the screenshotId returned by get_window_state. " +
  "If you see 'get_window_state before…', the server will auto-retry once; still prefer a fresh state after big UI changes. " +
  "Pass app exactly as list_windows returns it (single backslashes in the path are fine).";

// ── App / window discovery ────────────────────────────────────────────────

server.tool(
  "list_apps",
  "List all installed applications (running state + their windows). Use this to discover what is available before targeting a window.",
  {},
  async () => {
    return guard(async () => {
      const apps = await client.listApps();
      return { content: [{ type: "text", text: JSON.stringify(apps, null, 2) }] };
    });
  },
);

server.tool(
  "list_windows",
  "List all currently open, operable windows with their app + id. Copy {app, id} into later tools." + WORKFLOW_HINT,
  {},
  async () => {
    return guard(async () => {
      const windows = await client.listWindows();
      return {
        content: [{ type: "text", text: JSON.stringify(windows, null, 2) }],
      };
    });
  },
);

server.tool(
  "get_window",
  "Rehydrate a window object from its id (and optional app). Useful when a window handle is stale.",
  { id: Num, app: AppId.optional() },
  async ({ id, app }) => {
    return guard(async () => {
      const win = await client.getWindow({ app, id });
      return { content: [{ type: "text", text: JSON.stringify(win, null, 2) }] };
    });
  },
);

server.tool(
  "launch_app",
  "Launch an application by its app id (from list_apps) or an absolute .exe path. A common app id also works.",
  { appId: AppId },
  async ({ appId }) => {
    return guard(async () => {
      await client.launchApp(appId);
      return { content: [{ type: "text", text: "Launched." }] };
    });
  },
);

server.tool(
  "activate_window",
  "Bring a window to the foreground (focus it).",
  { app: AppId, id: Num },
  async ({ app, id }) => {
    return guard(async () => {
      await client.activateWindow(winArgs(app, id));
      return { content: [{ type: "text", text: "Activated." }] };
    });
  },
);

// ── Window state / vision ─────────────────────────────────────────────────

server.tool(
  "get_window_state",
  "Core perception tool: returns screenshot image block(s) + accessibility tree. " +
    "ALWAYS call this before click/scroll/drag (or after navigation). " +
    "Response text starts with screenshotId=… — pass that id to coordinate click/scroll/drag. " +
    "includeScreenshot=false returns only the tree (faster, but coordinate tools need a prior screenshot)." +
    WORKFLOW_HINT,
  {
    app: AppId,
    id: Num,
    includeScreenshot: z.boolean().default(true),
    includeText: z.boolean().default(true),
  },
  async ({ app, id, includeScreenshot, includeText }) => {
    return guard(async () => {
      const window = winArgs(app, id);
      const st = await client.getWindowState(window, {
        includeScreenshot,
        includeText,
      });
      const content = [];
      const shots =
        st.screenshots && Array.isArray(st.screenshots)
          ? st.screenshots
          : st.screenshot
            ? [st.screenshot]
            : [];
      const ids = [];
      for (let i = 0; i < shots.length; i++) {
        const s = shots[i];
        const sid = s.id || s.screenshotId || `screenshot-${i}`;
        ids.push(sid);
        // The exe returns screenshots as data: URLs (data:image/jpeg;base64,...).
        // Extract the base64 payload so the SDK can emit a valid image block.
        let data = s.base64 || s.data || null;
        let mimeType = s.mimeType || "image/png";
        if (!data && typeof s.url === "string") {
          const m = /^data:([^;]+);base64,(.*)$/i.exec(s.url);
          if (m) {
            mimeType = m[1] || mimeType;
            data = m[2];
          }
        }
        if (data) {
          content.push({ type: "image", data, mimeType });
        }
      }
      if (ids.length) {
        content.unshift({
          type: "text",
          text:
            `screenshotId=${ids[0]}` +
            (ids.length > 1 ? ` (also: ${ids.slice(1).join(", ")})` : "") +
            `\nUse this screenshotId for coordinate click/scroll/drag on this window.`,
        });
      }
      const tree =
        st.accessibility && st.accessibility.tree
          ? st.accessibility.tree
          : st.accessibility_tree || null;
      if (tree) {
        content.push({ type: "text", text: tree });
      }
      if (content.length === 0) {
        content.push({
          type: "text",
          text: JSON.stringify(st).slice(0, 4000),
        });
      }
      return { content };
    });
  },
);

// ── Interaction ───────────────────────────────────────────────────────────

server.tool(
  "click",
  "Click inside a window. Prefer elementIndex from the latest accessibility tree. " +
    "For x/y (window-local pixels, origin=top-left), pass screenshotId from the latest get_window_state " +
    "(server also remembers the last id and will fill it in if omitted). " +
    "On stale-session errors the server auto re-snapshots and retries once." +
    WORKFLOW_HINT,
  {
    app: AppId,
    id: Num,
    elementIndex: Int.optional(),
    x: Num.optional(),
    y: Num.optional(),
    clickCount: Int.default(1),
    mouseButton: z.enum(["left", "right", "middle"]).default("left"),
    screenshotId: z.string().optional(),
  },
  async ({
    app,
    id,
    elementIndex,
    x,
    y,
    clickCount,
    mouseButton,
    screenshotId,
  }) => {
    return guard(async () => {
      await client.click(winArgs(app, id), {
        elementIndex,
        x,
        y,
        clickCount,
        mouseButton,
        screenshotId,
      });
      return { content: [{ type: "text", text: "Clicked." }] };
    });
  },
);

server.tool(
  "type_text",
  "Type Unicode text into the focused element of a window (supports Chinese, etc.). Focus the target first with click if needed.",
  { app: AppId, id: Num, text: z.string() },
  async ({ app, id, text }) => {
    return guard(async () => {
      await client.typeText(winArgs(app, id), text);
      return { content: [{ type: "text", text: "Typed." }] };
    });
  },
);

server.tool(
  "set_value",
  "Set the value of an editable element via UI Automation ValuePattern (form fields). " +
    "Not all editors support this (e.g. some Notepad/document controls) — fall back to type_text.",
  { app: AppId, id: Num, elementIndex: Int, value: z.string() },
  async ({ app, id, elementIndex, value }) => {
    return guard(async () => {
      await client.setValue(winArgs(app, id), elementIndex, value);
      return { content: [{ type: "text", text: "Value set." }] };
    });
  },
);

server.tool(
  "press_key",
  "Press a key or key combination. Use + to separate combo keys, e.g. 'Return', 'Tab', 'Control_L+a', 'Control_L+Shift_L+period'.",
  { app: AppId, id: Num, key: z.string() },
  async ({ app, id, key }) => {
    return guard(async () => {
      await client.pressKey(winArgs(app, id), key);
      return { content: [{ type: "text", text: "Key pressed." }] };
    });
  },
);

server.tool(
  "scroll",
  "Scroll from a point inside a window. scrollY positive=down, negative=up; scrollX positive=right. " +
    "Requires a prior get_window_state screenshot; pass screenshotId (or rely on server memory)." +
    WORKFLOW_HINT,
  {
    app: AppId,
    id: Num,
    x: Num,
    y: Num,
    scrollX: Num.default(0),
    scrollY: Num.default(0),
    screenshotId: z.string().optional(),
  },
  async ({ app, id, x, y, scrollX, scrollY, screenshotId }) => {
    return guard(async () => {
      await client.scroll(winArgs(app, id), {
        x,
        y,
        scrollX,
        scrollY,
        screenshotId,
      });
      return { content: [{ type: "text", text: "Scrolled." }] };
    });
  },
);

server.tool(
  "drag",
  "Drag from (fromX,fromY) to (toX,toY) in window-local pixels. Pass screenshotId from get_window_state." +
    WORKFLOW_HINT,
  {
    app: AppId,
    id: Num,
    fromX: Num,
    fromY: Num,
    toX: Num,
    toY: Num,
    screenshotId: z.string().optional(),
  },
  async ({ app, id, fromX, fromY, toX, toY, screenshotId }) => {
    return guard(async () => {
      await client.drag(winArgs(app, id), {
        fromX,
        fromY,
        toX,
        toY,
        screenshotId,
      });
      return { content: [{ type: "text", text: "Dragged." }] };
    });
  },
);

server.tool(
  "perform_secondary_action",
  "Perform an accessibility secondary action on an element, e.g. 'Scroll Up', 'Scroll Down', 'Expand', 'Collapse', 'Raise' (case-insensitive).",
  { app: AppId, id: Num, action: z.string(), elementIndex: Int },
  async ({ app, id, action, elementIndex }) => {
    return guard(async () => {
      await client.performSecondaryAction(winArgs(app, id), action, elementIndex);
      return { content: [{ type: "text", text: "Action performed." }] };
    });
  },
);

server.tool(
  "release",
  "Shut down codex-computer-use.exe and dismiss the on-screen control overlay. Call when done. " +
    "Helper restarts on the next tool call. Idle auto-release also runs after COMPUTER_USE_IDLE_MS (default 120000).",
  {},
  async () => {
    return guard(async () => {
      await releaseClient();
      return {
        content: [
          {
            type: "text",
            text: "Released. Control overlay dismissed; helper will restart on next use.",
          },
        ],
      };
    });
  },
);

// ── Lifecycle ─────────────────────────────────────────────────────────────

async function shutdown(reason) {
  process.stderr.write(`[computer-use] shutting down (${reason})\n`);
  try {
    await releaseClient();
  } catch {}
}

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);

  // Cursor 等宿主断开 stdio / 杀进程时，务必关掉 exe，否则控制层残留
  process.on("SIGINT", () => {
    shutdown("SIGINT").finally(() => process.exit(0));
  });
  process.on("SIGTERM", () => {
    shutdown("SIGTERM").finally(() => process.exit(0));
  });
  process.on("exit", () => {
    forceKillClient();
  });

  if (process.stdin) {
    process.stdin.on("end", () => {
      shutdown("stdin-end").finally(() => process.exit(0));
    });
    process.stdin.on("close", () => {
      shutdown("stdin-close").finally(() => process.exit(0));
    });
  }
}

main().catch((e) => {
  process.stderr.write(`[computer-use] server error: ${e.stack || e}\n`);
  process.exit(1);
});
