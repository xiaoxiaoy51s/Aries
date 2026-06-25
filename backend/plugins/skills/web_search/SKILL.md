---
name: web_search
description: 联网搜索网页信息、新闻、事实、资料、图片、视频。使用 SearXNG 搜索引擎并返回结构化结果。
---

# 联网搜索技能

这个技能允许 AI 助手进行联网搜索，获取实时信息、新闻、事实、资料、图片和视频。

## 使用策略

### 1. 搜索前检查
- **先检查系统消息中是否已有搜索结果**，可覆盖时直接用，禁止重复搜索
- 已有明确信息时不要为了"确认"而重复搜索

### 2. 实时数据获取策略（重要）
针对中文 AI 厂商定价、价格、数量等实时数据，采用**搜索 + Playwright 结合**的策略：

**步骤 1：广度搜索定位**
- 先用 `web_search` 搜索关键词 + "官网" 或 "定价"
- 从搜索结果中找到官方开发者文档地址（如 platform.bigmodel.cn、api-docs.deepseek.com）
- 优先使用 `site:` 限定官网域名

**步骤 2：精准爬取**
- 使用 `playwright` 直接访问官网定价页面获取准确数据
- 不要依赖搜索结果中的价格信息（可能过时或不准确）

### 3. 精准搜索技巧
查询具体信息时，使用 `site:` 限定官网域名，例如：
```
https://searxng.ayuandoubao.icu/search?q=模型价格 site:api-docs.deepseek.com&format=json
https://searxng.ayuandoubao.icu/search?q=API定价 site:platform.openai.com&format=json
```

### 4. 搜索次数限制
- **单次任务中 web_search 最多调用 3 次**
- 超过 3 次则停止搜索，基于已有信息回答用户

### 5. 避免盲目搜索
- 简单事实性问题（如"1+1=?")不需要搜索
- 常识性问题不需要搜索
- 用户已提供的信息不需要搜索验证

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索关键词 |
| `category` | string | 否 | 搜索分类：general（默认）、images、videos、news、it |
| `engines` | string | 否 | 自定义引擎，多个用逗号分隔 |
| `limit` | int | 否 | 返回数量，默认 6（images/videos 默认 4） |

### category 说明

- `general` - 网页搜索（引擎：sogou, bing）
- `images` - 图片搜索（引擎：bing images, sogou images）
- `videos` - 视频搜索（引擎：360search videos, bilibili, sogou videos）
- `news` - 新闻搜索（引擎：sogou wechat）
- `it` - IT技术（引擎：github）

### engines 可选值

- `bing`, `sogou`
- `bing images`, `sogou images`
- `360search videos`, `bilibili`, `sogou videos`
- `sogou wechat`
- `github`

## 返回结果

### 普通结果
```json
{
  "title": "标题",
  "url": "链接",
  "content": "摘要",
  "engine": "搜索引擎",
  "category": "分类"
}
```

### 图片结果（额外字段）
```json
{
  "img_src": "图片直接链接",
  "thumbnail": "缩略图链接"
}
```

### 视频结果（额外字段）
```json
{
  "thumbnail": "视频缩略图",
  "duration": "视频时长"
}
```

## 输出格式建议

### 普通搜索结果
使用列表或段落形式展示，包含标题、URL、摘要。

### 图片搜索结果
**推荐以 Markdown 表格形式输出**，例如：

```markdown
| 图片 | 标题 | 来源 |
|------|------|------|
| ![](img_src链接) | 图片标题 | 来源网站 |
```

**字段使用优先级**：
1. 优先使用 `img_src` 作为图片链接
2. 如果 `img_src` 为空，使用 `thumbnail`
3. 图片标题使用 `title` 字段

### 视频搜索结果
**推荐以 Markdown 表格形式输出**，例如：

```markdown
| 缩略图 | 标题 | 时长 | 来源 |
|--------|------|------|------|
| ![](thumbnail链接) | 视频标题 | 时长 | 来源网站 |
```

**字段说明**：
- `thumbnail` - 视频缩略图链接（必需）
- `title` - 视频标题
- `duration` - 视频时长（如果有）
- `url` - 视频页面链接

## 注意事项

1. **图片/视频搜索默认返回 4 条**，其他搜索默认 6 条
2. **图片链接字段**：`img_src`（原图）或 `thumbnail`（缩略图）
3. **视频缩略图字段**：`thumbnail`
4. 前端会自动检测 Markdown 中的图片链接并渲染
5. 视频搜索返回的 `url` 点击后会跳转到原始视频页面

## 示例

**普通搜索**：
```
query: "北京天气"
```

**图片搜索**（输出表格格式）：
```
query: "可爱猫咪"
category: "images"
limit: 4
```
输出：
```markdown
| 图片 | 标题 | 来源 |
|------|------|------|
| ![](img_src) | 猫咪标题 | bing images |
```

**视频搜索**（输出表格格式）：
```
query: "Python教程"
category: "videos"
limit: 4
```
输出：
```markdown
| 缩略图 | 标题 | 来源 |
|--------|------|------|
| ![](thumbnail) | Python教程标题 | sogou videos |
```

**精准搜索**：
```
query: "API定价 site:platform.openai.com"
```
