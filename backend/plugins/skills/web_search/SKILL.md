---
name: web_search
description: "联网搜索网页信息、新闻、事实、资料、图片、视频。当用户需要实时信息、外部资料、新闻动态、事实核查、或任何无法从已有知识中回答的问题时，必须使用此技能。即使用户没有明确要求搜索，只要回答需要外部最新信息，就应该触发。"
---

# 联网搜索技能

通过运行脚本命令进行联网搜索，获取实时信息、新闻、事实、资料、图片和视频。

## 调用方式

使用 RunCommand 工具运行以下命令：

```bash
python <skill_dir>/scripts/search.py "<query>"
```

其中 `<skill_dir>` 是本技能目录的绝对路径，`<query>` 是搜索关键词。

### 参数

| 参数 | 格式 | 必需 | 说明 |
|------|------|------|------|
| 第一个位置参数 | 字符串 | 是 | 搜索关键词 |
| `--category` | general/images/videos/news/it | 否 | 搜索分类，默认 general |
| `--engines` | 逗号分隔 | 否 | 自定义引擎 |
| `--limit` | 整数 | 否 | 返回数量，默认 6 |
| `--format` | json/text | 否 | 输出格式，默认 json |
| `--server` | URL | 否 | 自定义 SearXNG 服务器地址 |

### 基本示例

```bash
# 普通搜索
python <skill_dir>/scripts/search.py "北京天气"

# 图片搜索，返回 4 条
python <skill_dir>/scripts/search.py "可爱猫咪" --category images --limit 4

# 视频搜索
python <skill_dir>/scripts/search.py "Python教程" --category videos

# 指定引擎
python <skill_dir>/scripts/search.py "机器学习论文" --engines github

# 只输出文本（适合直接展示给用户）
python <skill_dir>/scripts/search.py "最新AI新闻" --format text

# 精准搜索，限定域名
python <skill_dir>/scripts/search.py "API定价 site:platform.openai.com"
```

### 输出格式

默认 `--format json` 输出完整 JSON：

```json
{
  "query": "搜索词",
  "assistant_text": "格式化的文本结果，可直接展示",
  "results": [
    {
      "title": "标题",
      "url": "链接",
      "content": "摘要",
      "engine": "搜索引擎",
      "img_src": "图片链接（图片搜索时）",
      "thumbnail": "缩略图（图片/视频搜索时）",
      "duration": "时长（视频搜索时）"
    }
  ],
  "limit": 6,
  "total_fetched": 100,
  "total_after_cleaning": 6
}
```

`--format text` 只输出 `assistant_text` 文本，适合直接展示。

## 搜索策略

### 搜索前检查

- **先检查上下文中是否已有搜索结果**，已有时直接使用，禁止重复搜索
- 已有明确信息时不要为了"确认"而重复搜索

### 实时数据获取策略

针对 AI 厂商定价、价格、数量等实时数据：

**步骤 1：广度搜索定位**
- 搜索关键词 + "官网" 或 "定价"
- 从结果中找到官方开发者文档地址
- 使用 `site:` 限定官网域名

**步骤 2：精准爬取**
- 如有需要，使用其他工具直接访问官网页面获取准确数据
- 不要依赖搜索结果中的价格信息（可能过时）

### 搜索次数限制

- **单次任务中最多搜索 3 次**
- 超过 3 次则停止搜索，基于已有信息回答用户

### 避免盲目搜索

- 简单事实性问题（如"1+1=?"）不需要搜索
- 常识性问题不需要搜索
- 用户已提供的信息不需要搜索验证

## category 说明

| 分类 | 引擎 | 用途 |
|------|------|------|
| general（默认） | sogou, bing | 综合网页搜索 |
| images | bing images, sogou images | 图片搜索 |
| videos | 360search videos, bilibili, sogou videos | 视频搜索 |
| news | sogou wechat | 微信公众号新闻 |
| it | github | 技术/代码搜索 |

## 输出展示建议

### 普通搜索结果

用列表或段落展示，包含标题、URL、摘要。

### 图片搜索结果

用 Markdown 表格展示：

```markdown
| 图片 | 标题 | 来源 |
|------|------|------|
| ![](img_src链接) | 图片标题 | 来源网站 |
```

字段优先级：`img_src` > `thumbnail`。

### 视频搜索结果

用 Markdown 表格展示：

```markdown
| 缩略图 | 标题 | 时长 | 来源 |
|--------|------|------|------|
| ![](thumbnail链接) | 视频标题 | 时长 | 来源网站 |
```

## 环境变量

- `SEARXNG_URL` — 覆盖默认 SearXNG 服务器地址
