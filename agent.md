# Agent.md — 系统架构与 API 调用规范

## 项目概述

**项目名称**：面向低幼通识教育的多模态教学资源自动生成与数据管理系统

**核心功能**：用户输入一个通识科学概念（如"光合作用"），系统自动调用 ECNU 大模型 API，生成包含3页的有声科普绘本（故事文本 + AI插画 + AI配音），并持久化存储到本地 SQLite 数据库。

## 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| 前端/后端 | Streamlit | Python Web 框架，单文件全栈 |
| 数据库 | SQLite (sqlite3) | 零安装，单文件嵌入式数据库 |
| AI 接口 | requests + ECNU API | 标准 HTTP 调用，不依赖 openai SDK |

## API 调用规范

### 1. 剧本生成 (Text-to-Text)

```
POST https://chat.ecnu.edu.cn/open/api/v1/chat/completions
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

**请求体**：
```json
{
  "model": "ecnu-plus",
  "messages": [
    {
      "role": "system",
      "content": "你是一位专业的儿童科普绘本作家。请根据用户提供的科学概念，创作一个3页的童话故事绘本。\n\n要求：\n1. 故事语言要简单、生动、适合3-8岁儿童\n2. 每页约100字左右\n3. 要融入科学知识，但用童话的方式表达\n4. 每页需提供一个英文画面描述（image_prompt），用于AI绘图\n\n请严格按照以下JSON格式返回，不要返回其他内容：\n{\n  \"title\": \"绘本标题\",\n  \"pages\": [\n    {\n      \"page_text\": \"第1页的故事文本\",\n      \"image_prompt\": \"English prompt for page 1 illustration, describe scene in detail, cute cartoon style for children\"\n    },\n    {\n      \"page_text\": \"第2页的故事文本\",\n      \"image_prompt\": \"English prompt for page 2 illustration\"\n    },\n    {\n      \"page_text\": \"第3页的故事文本\",\n      \"image_prompt\": \"English prompt for page 3 illustration\"\n    }\n  ]\n}"
    },
    {
      "role": "user",
      "content": "请为通识科学概念「{concept}」创作一本3页的儿童科普绘本。"
    }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "storybook",
      "schema": {
        "type": "object",
        "properties": {
          "title": {"type": "string"},
          "pages": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "page_text": {"type": "string"},
                "image_prompt": {"type": "string"}
              },
              "required": ["page_text", "image_prompt"]
            }
          }
        },
        "required": ["title", "pages"]
      }
    }
  },
  "max_tokens": 2048
}
```

**响应解析**：`response.json()["choices"][0]["message"]["content"]` → JSON 字符串 → `json.loads()`

**Fallback**：若结构化输出失败，用正则 `\{[\s\S]*\}` 从响应文本中提取 JSON 块。

### 2. 插画生成 (Text-to-Image)

```
POST https://chat.ecnu.edu.cn/open/api/v1/images/generations
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

**请求体**：
```json
{
  "model": "ecnu-image",
  "prompt": "<image_prompt from story, max 1024 chars>",
  "size": "512x512",
  "response_format": "url"
}
```

**响应解析**：`response.json()["data"][0]["url"]` → 图片 URL → `requests.get(url)` 下载二进制 → 保存到 `./static/images/{book_id}_page{N}.png`

**注意**：URL 24小时过期，需立即下载保存。

### 3. 语音合成 (Text-to-Speech)

```
POST https://chat.ecnu.edu.cn/open/api/v1/audio/speech
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

**请求体**：
```json
{
  "model": "ecnu-tts",
  "input": "<page_text, max 4096 chars>",
  "voice": "liwa",
  "response_format": "mp3",
  "speed": 0.9
}
```

**响应解析**：`response.content` 直接为二进制音频 → 保存到 `./static/audio/{book_id}_page{N}.mp3`

## 数据库 Schema

```sql
CREATE TABLE IF NOT EXISTS storybooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    concept TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS storybook_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    page_text TEXT NOT NULL,
    image_path TEXT,
    audio_path TEXT,
    FOREIGN KEY (book_id) REFERENCES storybooks(id) ON DELETE CASCADE
);
```

## 业务流水线时序

```
用户输入概念
    │
    ▼
[1] generate_story(concept) → {title, pages[3]}
    │  调用 ecnu-plus chat/completions
    │  使用 json_schema 结构化输出
    ▼
[2] 对每一页: generate_image(pages[i].image_prompt)
    │  调用 ecnu-image images/generations
    │  下载图片 URL → 保存本地文件
    ▼
[3] 对每一页: generate_audio(pages[i].page_text)
    │  调用 ecnu-tts audio/speech
    │  保存二进制音频 → 本地文件
    ▼
[4] save_book(concept, title, pages)
    │  BEGIN TRANSACTION
    │  INSERT INTO storybooks → 获得 book_id
    │  INSERT INTO storybook_pages × 3
    │  COMMIT
    ▼
前端展示 3 页绘本（图片 + 文本 + 音频播放器）
```

## 文件目录结构

```
CS_edu/
├── app.py              # Streamlit 主程序
├── README.md           # 运行说明
├── plan.md             # 本计划文件
├── agent.md            # 本架构文件
├── education.db        # SQLite 数据库（运行后自动生成）
└── static/
    ├── images/         # AI 生成的插画
    │   ├── 1_page1.png
    │   ├── 1_page2.png
    │   └── 1_page3.png
    └── audio/          # AI 生成的配音
        ├── 1_page1.mp3
        ├── 1_page2.mp3
        └── 1_page3.mp3
```

## 异常处理清单

| # | 异常场景 | 检测方式 | 恢复策略 |
|---|---|---|---|
| 1 | API Key 无效 (401) | HTTP status | st.error 提示检查 API Key |
| 2 | API 配额耗尽 (429) | HTTP status | st.error 提示稍后重试 |
| 3 | API 服务不可用 (500) | HTTP status | st.error 提示服务暂不可用 |
| 4 | API 超时 | requests.Timeout | st.error 提示网络超时 |
| 5 | 剧本 JSON 解析失败 | json.JSONDecodeError | 正则 fallback → st.error |
| 6 | 图片 URL 下载失败 | requests.HTTPError | st.warning 跳过该页 |
| 7 | 数据库写入失败 | sqlite3.Error | conn.rollback() + st.error |
| 8 | 本地文件删除失败 | OSError | 静默忽略 + 记录日志 |
| 9 | 用户输入为空 | len(concept)==0 | st.warning 提示输入 |
| 10 | image_prompt 超 1024 字符 | len() 检查 | 截断处理 |

## API 用量估算（单次生成）

| 步骤 | 模型 | 预估消耗 |
|---|---|---|
| 剧本生成 | ecnu-plus | ~500 input + ~800 output tokens ≈ 0.37 credits |
| 插画 ×3 | ecnu-image | 30 × 3 = 90 credits |
| 配音 ×3 | ecnu-tts | 5 × 3 = 15 credits |
| **合计** | | **~105 credits / 次** |

在默认配额（5000 credits/天）下，约可生成 47 本绘本/天。
