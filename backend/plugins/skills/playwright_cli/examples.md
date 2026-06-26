# Playwright 脚本调用示例

## 示例 A：超星作业 — 答前 5 题（推荐序列）

### 1. 打开作业（仅此一步带 URL）

```bash
python scripts/playwright.py open "https://mooc1.chaoxing.com/mooc-ans/mooc2/work/dowork?courseId=…&classId=…&workId=…&answerId=…&enc=…"
```

等待加载后获取快照：

```bash
python scripts/playwright.py snapshot
```

检查：输出含 `作业作答`、`radio`、`题目 1.`，不含 `用户登录`。

### 2. 读题目结构（无 URL）

```bash
python scripts/playwright.py snapshot
```

从输出中记录每题正确选项的 `[ref=eXX]`（按**选项文字**选题，不按打乱后的 A/B/C/D）。

### 3. 逐题点击（每题一次，均无 URL）

```bash
python scripts/playwright.py click e26
python scripts/playwright.py click e45
python scripts/playwright.py click e76
python scripts/playwright.py click e83
python scripts/playwright.py click e102
```

### 4. 验证（无 URL）

```bash
python scripts/playwright.py snapshot
```

期望：前 5 题对应 radio 行含 `[checked]`。

### 5. 回复用户

告知已完成点选，请用户在浏览器中确认并点击「暂时保存」或「提交」。

---

## 示例 B：继续答第 6–10 题

**不要重新 open。** 若浏览器仍开着：

```bash
python scripts/playwright.py snapshot
```

滚动页面（如需要）：

```bash
python scripts/playwright.py eval "window.scrollBy(0, 800)"
```

再 snapshot → 找新 ref → click。

---

## 示例 C：提取题干文本

```bash
python scripts/playwright.py eval "Array.from(document.querySelectorAll('[class*=TiMu]')).slice(0,5).map((el,i)=> (i+1)+'. '+el.innerText.slice(0,120)).join('\n---\n')"
```

---

## 反例（禁止）

```bash
# ❌ 用 var
python scripts/playwright.py eval "var t=document.body; t.innerText"

# ❌ 未 snapshot 就猜 ref
python scripts/playwright.py click e26
```

---

## 示例 D：modal state 错误

```bash
python scripts/playwright.py dismiss-dialog
python scripts/playwright.py eval "document.title"
```

错误信息含 `browser_evaluate` / `modal state` 即属此类。

---

## 示例 E：截图与 PDF

```bash
python scripts/playwright.py screenshot
python scripts/playwright.py pdf
```

---

## 示例 F：查看会话状态

```bash
python scripts/playwright.py status
```

输出当前所有 playwright-cli 会话及其状态、profile 路径。

---

## 关闭浏览器

```bash
python scripts/playwright.py close
```

Profile 内登录态保留；下次 `open` 仍登录。
