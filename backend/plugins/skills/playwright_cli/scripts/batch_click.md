# 批量点击

传入 ref 列表，自动逐个点击。无需写 bat 文件。

## 用法

```bash
# 空格分隔
python scripts/batch_click.py e26 e45 e76 e83 e102

# 逗号分隔
python scripts/batch_click.py e26,e45,e76,e83,e102

# 自定义间隔（默认 300ms）
python scripts/batch_click.py e26 e45 e76 --delay 500
```

## 工作流

```bash
# 1. 获取快照，找到 ref
python scripts/playwright.py snapshot

# 2. 批量点击
python scripts/batch_click.py e26 e45 e76 e83 e102

# 3. 验证
python scripts/playwright.py snapshot
```

## 输出示例

```
[1/5] 点击 e26... OK
[2/5] 点击 e45... OK
[3/5] 点击 e76... OK
[4/5] 点击 e83... OK
[5/5] 点击 e102... OK

完成: 5/5 成功
```

失败的 ref 会在末尾列出，可用 `python scripts/playwright.py click <ref>` 单独补点。
