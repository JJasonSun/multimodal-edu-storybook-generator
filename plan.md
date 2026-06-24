# 面向低幼通识教育的多模态教学资源自动生成与数据管理系统 — 实施计划

## 项目目标
基于 Streamlit + SQLite + ECNU API，构建一个一键生成"故事剧本 + 配图 + 配音"的3页有声科普绘本系统。

## 交付物
1. `app.py` — 完整的 Streamlit 主程序
2. `README.md` — 系统运行说明文档
3. `plan.md` — 本计划文件
4. `agent.md` — 架构与 API 调用规范

## 技术架构

### API 调用方式
全部使用 `requests` 库直接调用 ECNU HTTP API（不依赖 openai SDK）：

| 功能 | Endpoint | Model | 关键约束 |
|---|---|---|---|
| 剧本生成 | `POST /chat/completions` | `ecnu-plus` | 使用 `response_format.json_schema` 结构化输出 |
| 插画生成 | `POST /images/generations` | `ecnu-image` | prompt ≤ 1024 字符；返回 URL 24h 过期 |
| 语音合成 | `POST /audio/speech` | `ecnu-tts` | input ≤ 4096 字符；返回二进制音频 |

Base URL: `https://chat.ecnu.edu.cn/open/api/v1`

### 数据库设计 (SQLite)
- 文件: `education.db`（项目根目录）
- 表 `storybooks`: id(PK), title, concept, created_at
- 表 `storybook_pages`: id(PK), book_id(FK→storybooks ON DELETE CASCADE), page_number, page_text, image_path, audio_path

### 文件存储
- 图片: `./static/images/{book_id}_page{N}.png`
- 音频: `./static/audio/{book_id}_page{N}.mp3`

## 核心业务流水线

用户输入概念 → 点击生成：

1. **剧本生成**：调用 ecnu-plus，prompt 要求返回严格 JSON（title + 3页 page_text/image_prompt）。使用 `response_format` 结构化输出保障 JSON 合法性。
2. **插画生成**：遍历3页，用 image_prompt 调用 ecnu-image，下载图片保存到本地。
3. **语音合成**：遍历3页，用 page_text 调用 ecnu-tts，保存 mp3 到本地。
4. **持久化存储**：事务写入 SQLite 两张表。

每步之间显示 `st.spinner` + 进度提示。

## 前端界面 (st.tabs)

### Tab 1: 🎨 智能绘本创作中心
- 文本输入框 (st.text_input)
- 生成按钮 (st.button)
- 生成中: st.spinner + st.status 显示进度
- 生成后: 3列 st.columns，每列展示图片(st.image) + 文本 + 音频(st.audio)

### Tab 2: 📚 数字多模态绘本馆
- 从 DB 读取 storybooks 列表，用 st.selectbox 或侧边栏展示
- 选中后加载对应3页数据，展示图片/文本/音频
- 删除按钮: 删除 DB 记录 + 本地文件

## 异常处理策略

| 场景 | 处理方式 |
|---|---|
| API 调用失败（401/403/429/500） | 捕获 requests.HTTPError，解析 detail 字段，st.error 展示友好提示 |
| API 超时 | requests timeout=120，超时后提示重试 |
| JSON 解析失败（剧本生成） | 正则提取 JSON 块作为 fallback；仍失败则提示重试 |
| 图片下载失败 | 跳过该页，st.warning 提示，继续后续流程 |
| 数据库操作失败 | try/except 包裹，conn.rollback() 回滚 |
| 文件删除失败 | os.path.exists 检查，静默处理已不存在的文件 |
| 输入为空 | st.warning 提示用户输入概念 |

## 代码结构 (app.py 单文件)

```
app.py
├── 配置常量 (API_BASE_URL, API_KEY, 模型名, 目录路径)
├── init_database()          — 建表（IF NOT EXISTS）
├── generate_story(concept)  — 调用 ecnu-plus 生成剧本 JSON
├── generate_image(prompt)   — 调用 ecnu-image，返回图片 bytes
├── generate_audio(text)     — 调用 ecnu-tts，返回音频 bytes
├── save_book(concept, title, pages) — 事务写入 DB + 保存文件
├── get_all_books()          — 查询所有绘本
├── get_book_pages(book_id)  — 查询指定绘本的页面
├── delete_book(book_id)     — 删除 DB 记录 + 本地文件
├── main()
│   ├── 侧边栏配置 API Key
│   ├── Tab 1: 创作中心
│   └── Tab 2: 绘本馆
└── if __name__ == "__main__"
```

## 实施步骤

1. 创建项目目录结构（`static/images/`, `static/audio/`）
2. 编写 `app.py`（全部逻辑在单文件中）
3. 编写 `README.md`
4. 语法检查 + 运行验证

## 验证方式

1. `python -c "import py_compile; py_compile.compile('app.py', doraise=True)"` — 语法检查
2. `pip install streamlit requests` — 确认依赖可安装
3. `streamlit run app.py` — 启动系统，在浏览器中测试完整流程
