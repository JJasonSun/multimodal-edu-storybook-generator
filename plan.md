# 面向低幼通识教育的多模态教学资源自动生成与数据管理系统 — 实施计划

## 项目目标
基于 Streamlit + SQLite + ECNU API，构建一个一键生成"故事剧本 + 配图 + 配音"的3页有声科普绘本系统，并实现多模态数据的语义检索、标签管理与数据分析能力。

## 交付物
1. `app.py` — 完整的 Streamlit 主程序
2. `README.md` — 系统运行说明文档
3. `Plan.md` — 本计划文件
4. `AGENTS.md` — Agent 工作指南
5. `paper/论文大纲.md` — Demo 论文结构与内容规划

## 技术架构

### API 调用方式
全部使用 `requests` 库直接调用 ECNU HTTP API（不依赖 openai SDK）：

| 功能 | Endpoint | Model | 关键约束 |
|---|---|---|---|
| 剧本生成 | `POST /chat/completions` | `ecnu-plus` | 使用 `response_format.json_schema` 结构化输出 |
| 插画生成 | `POST /images/generations` | `ecnu-image` | prompt ≤ 1024 字符；返回 URL 24h 过期 |
| 语音合成 | `POST /audio/speech` | `ecnu-tts` | input ≤ 4096 字符；返回二进制音频 |
| 文本嵌入 | `POST /embeddings` | `ecnu-embedding-small` | 1024 维向量，用于语义检索 |

Base URL: `https://chat.ecnu.edu.cn/open/api/v1`

### 数据库设计 (SQLite)
- 文件: `education.db`（项目根目录）
- 表 `storybooks`: id(PK), title, concept, tags(JSON), created_at
- 表 `storybook_pages`: id(PK), book_id(FK→storybooks ON DELETE CASCADE), page_number, page_text, image_path, audio_path
- 表 `storybook_embeddings`: id(PK), book_id(FK→storybooks ON DELETE CASCADE, UNIQUE), embedding(BLOB), created_at

### 文件存储
- 图片: `./static/images/{book_id}_page{N}.png`
- 音频: `./static/audio/{book_id}_page{N}.mp3`

## 核心业务流水线

用户输入概念 → 点击生成：

1. **剧本生成**：调用 ecnu-plus，prompt 要求返回严格 JSON（title + 3页 page_text/image_prompt + tags 标签数组）。使用 `response_format` 结构化输出保障 JSON 合法性。
2. **插画生成**：遍历3页，用 image_prompt 调用 ecnu-image，下载图片保存到本地。
3. **语音合成**：遍历3页，用 page_text 调用 ecnu-tts，保存 mp3 到本地。
4. **向量嵌入**：拼接3页 page_text，调用 ecnu-embedding-small 生成 1024 维向量。
5. **持久化存储**：事务写入 SQLite 三张表（storybooks + storybook_pages + storybook_embeddings）。

每步之间显示 `st.spinner` + 进度提示。

## 前端界面 (st.tabs)

### Tab 1: 🎨 智能绘本创作中心
- 文本输入框 (st.text_input)
- 生成按钮 (st.button)
- 生成中: st.spinner + st.status 显示进度
- 生成后: 3列 st.columns，每列展示图片(st.image) + 文本 + 音频(st.audio)
- 展示自动生成的标签（st.badge）

### Tab 2: 📚 数字多模态绘本馆
- **语义搜索框**：输入自然语言查询（如"关于动物的故事"），调用 embedding API 计算相似度，返回 Top-K 结果
- **标签筛选器**：st.multiselect 按标签过滤绘本
- 从 DB 读取 storybooks 列表，用 st.selectbox 或侧边栏展示
- 选中后加载对应3页数据，展示图片/文本/音频
- 删除按钮: 删除 DB 记录 + 本地文件

### Tab 3: 📊 数据分析中心
- **指标卡片** (st.metric)：绘本总数、页面总数、图片/音频资源数
- **分类分布**：按 concept 分组的柱状图
- **时间线**：按日期统计的绘本生成趋势折线图
- **资源占用**：static/images 和 static/audio 目录大小

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
├── 数据库模块
│   ├── init_database()              — 建表（IF NOT EXISTS），含 FTS5 虚拟表和索引
│   └── get_connection()             — 获取连接，启用外键
├── API 调用模块
│   ├── generate_story(concept)      — 调用 ecnu-plus，返回 JSON（含 tags）
│   ├── generate_image(prompt)       — 调用 ecnu-image，返回图片 bytes
│   ├── generate_audio(text)         — 调用 ecnu-tts，返回音频 bytes
│   └── generate_embedding(text)     — 调用 ecnu-embedding-small，返回 1024 维向量
├── 业务逻辑模块
│   ├── save_book(concept, title, pages, tags, embedding) — 事务写入 3 张表 + FTS5
│   ├── update_book_text(book_id, page_number, new_text)  — 教师修正文本 + 联动 TTS
│   ├── get_all_books()              — 查询所有绘本
│   ├── get_book_pages(book_id)      — 查询指定绘本的页面
│   ├── delete_book(book_id)         — 删除 DB 记录 + 本地文件
│   ├── search_books_by_vector(query, top_k) — 向量语义检索
│   ├── search_books_by_fts(query)   — FTS5 全文关键字检索
│   ├── search_books_by_tag(tag)     — 标签筛选
│   ├── get_recommendations(book_id, top_k) — 自适应拓展推荐
│   ├── get_analytics_data()         — 统计分析数据
│   ├── export_books_json()          — JSON 元数据导出
│   ├── export_books_csv()           — CSV 元数据导出
│   └── export_book_zip(book_id)     — 标准化课件资产包导出
├── 前端模块
│   ├── render_page_card()           — 渲染单页绘本卡片（含教师修正模式）
│   ├── tab_creation_center()        — Tab 1: 创作中心
│   ├── tab_library()                — Tab 2: 绘本馆（混合搜索+推荐+修正）
│   └── tab_analytics()              — Tab 3: 数据分析中心（含数据导出）
└── main()                           — 入口，侧边栏 + tabs
```

## 实施步骤

### Phase 1: 基础系统（已完成）
1. ✅ 创建项目目录结构（`static/images/`, `static/audio/`）
2. ✅ 编写 `app.py`（基础生成 + 绘本馆）
3. ✅ 编写 `README.md`
4. ✅ uv 环境管理 + git 版本控制

### Phase 2: 功能增强（已完成）
1. ✅ 新增 `generate_embedding()` 函数，调用 ecnu-embedding-small
2. ✅ 新增 `storybook_embeddings` 表，更新 `init_database()`
3. ✅ 剧本生成 prompt 增加 tags 输出要求，更新 JSON schema
4. ✅ 更新 `save_book()` 写入 tags 和 embedding
5. ✅ 实现 `search_books_by_vector()` 向量语义检索（余弦相似度）
6. ✅ 实现 `search_books_by_tag()` 标签筛选
7. ✅ 实现 `get_analytics_data()` 统计分析
8. ✅ 新增 Tab 3 数据分析面板
9. ✅ 更新 Tab 2 绘本馆，增加搜索框和标签筛选
10. ✅ 更新 `pyproject.toml` 新增 `numpy` 依赖
11. ✅ 更新 `README.md` 文档

### Phase 3: 系统功能与学术深度优化（实施中）

> 每个优化点实现前更新本文件，实现后单独提交。

#### 3.1 查询优化与混合检索（已完成）
- ✅ **B-Tree 索引**：为 `concept`、`created_at`、`book_id+page_number` 添加索引
- ✅ **FTS5 全文检索**：创建 `storybook_fts` 虚拟表，支持关键字精准检索
- ✅ **混合检索**：搜索框支持"语义检索"与"关键字检索"切换
- ✅ **FTS5 同步**：`save_book()` 和 `delete_book()` 自动维护 FTS 索引
- 论文覆盖：查询处理与查询优化、信息检索系统、半结构化数据管理

#### 3.2 人在环路数据治理
- **教师修正模式**：Tab 2 浏览绘本时增加开关，文本框变为可编辑
- **联动重构**：保存修改后自动重新调用 ecnu-tts 刷新该页音频
- 论文覆盖：人在环路数据管理（Human-in-the-loop）

#### 3.3 自适应拓展推荐
- **向量相似度推荐**：基于 1024 维向量余弦相似度，推荐相关绘本
- **前端包装**：展示为"拓展学习推荐（Extended Learning Navigation）"
- 论文覆盖：推荐系统、数据驱动的AI系统、自适应学习路径规划

#### 3.4 数据要素合规导出
- **标准化资产包**：zip 打包（JSON 描述符 + 图片 PNG + 音频 MP3）
- **纯元数据导出**：支持 JSON/CSV 格式的绘本元数据导出
- 论文覆盖：数据要素支撑技术、教学资源资产化与可移植性

## 验证方式

1. `uv run python -c "import py_compile; py_compile.compile('app.py', doraise=True)"` — 语法检查
2. `uv run streamlit run app.py` — 启动系统，在浏览器中测试完整流程
3. 测试生成绘本 → 验证标签和向量写入 → 测试语义搜索 → 查看分析面板
