# Playwright 参考：会话、eval、超星作业

## 会话与 Profile

| 项 | 值 |
|----|-----|
| 会话名 | `aries`（环境变量 `ARIES_PLAYWRIGHT_SESSION` 可改） |
| Profile | `~/.Aries/browser_profile/` |
| 行为 | 首次 `open --persistent --profile`；之后同会话内 `goto` 或跳过导航 |

### 页面被刷新的原因（已修复）

旧行为：每次工具调用都 `goto url` → 作业页重载、已选答案丢失。  
现行为：URL 相同或省略 url → **不导航**，在当前页 `click` / `eval` / `snapshot`。

### 会话被占用

若 profile 已被其他 playwright-cli 会话占用，skill 会自动复用同 profile 的已开浏览器。

---

## eval 语法

`playwright-cli eval` 要求 **表达式** 或 **`() => {}`**：

| 写法 | 结果 |
|------|------|
| `document.title` | ✅ |
| `document.querySelector('[class*=TiMu]') ? 'ok' : 'no'` | ✅ |
| `(() => { return document.body.innerText.slice(0,500); })()` | ✅ |
| `var t = document.querySelector('div'); t.outerHTML` | ❌ SyntaxError（工具会尝试包 IIFE，仍可能无 return） |

---

## 超星学习通 mooc-ans 作业页

### URL 模式

```
https://mooc1.chaoxing.com/mooc-ans/mooc2/work/dowork?courseId=…&classId=…&workId=…&answerId=…&enc=…
```

### 登录检测

- 标题含 **「用户登录」** → profile 未登录，提示用户 `headless:false` 打开一次手动登录
- 标题含 **「作业作答」** → 可继续

### Snapshot 结构（单选题）

```yaml
- option "题目 1." [ref=e23]:
  - option [ref=e24]: 1. (单选题) 题干…
  - generic [ref=e25]:
    - radio "A 选项文字…选择" [ref=e26]:
    - radio "B …" [ref=e30]:
```

- **`[checked]`** 表示已选中
- **`randomOptions=true`**：页面上 A/B/C/D 标签与真实答案字母不一致，**必须读选项正文**，不能读前面的 A/B/C/D

### 点选方式

优先：`click` + `target: "e26"`（来自**当前** snapshot）  
备选：`eval` + `document.querySelector('…').click()`（仅当 click ref 失败时）

### 保存与提交

- 只点选答案后调用 **`暂时保存`** 需用户操作或后续 click 对应 ref
- **不要自动点「提交」**，除非用户明确要求

---

## 常见错误

| 现象 | 原因 | 处理 |
|------|------|------|
| 每次操作页面闪一下 | 每步都传了 `url` 或 `navigate:true` | 后续步骤省略 url |
| click 超时 | ref 过期（页面变过） | 重新 snapshot 再 click |
| eval SyntaxError | 用了 `var` 语句 | 改成表达式或 IIFE |
| 看到登录页 | profile 无 cookie | headless:false 手动登录一次 |
| `browser_evaluate` / `modal state` | 页面有 alert/confirm 或弹层阻塞 | 先 `dismiss_dialog`，或 click 关弹层；eval **不要带 url** |

---

## 已验证的单选题示例（习近平新时代概论）

以下为一次真实 snapshot 中的 ref 映射（**每次打开 ref 会变，不可硬编码**）：

| 题 | 答案要点 | 当时 ref 示例 |
|----|----------|---------------|
| 1 | 旗帜鲜明坚持以马克思主义为指导… | e26 |
| 2 | 立德树人 | e45 |
| 3 | 增进民生福祉 | e76 |
| 4 | 粮食安全 | e83 |
| 5 | 生态环境保护 | e102 |

流程：snapshot 找 ref → click → snapshot 看 `[checked]`。
