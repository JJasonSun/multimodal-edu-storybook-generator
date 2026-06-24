# 面向低幼通识教育的多模态教学资源自动生成与数据管理系统

> **An Automatic Generation and Data Management System for Multi-modal Courseware in General Education**
>
> 本系统是"智慧教育"与"计算教育学"课程的期末项目，聚焦**多模态数据管理**在教育场景中的应用，探索大语言模型驱动的教学资源自动生成与结构化持久存储方案。

## 项目背景

在智慧教育与计算教育学的理论框架下，多模态教学资源（文本、图像、音频）的高效生成与管理是实现个性化教学的关键技术瓶颈。传统多模态课件制作依赖人工编辑，成本高、周期长、难以规模化。本系统借助华东师范大学大模型开放平台（ECNU API）的多模态能力，构建了一条**端到端的多模态数据流水线**：

```
用户输入科学概念
    ↓
[LLM] ecnu-plus 剧本生成（结构化 JSON 输出）
    ↓
[Text-to-Image] ecnu-image 插画生成 ×3
    ↓
[Text-to-Speech] ecnu-tts 配音生成 ×3
    ↓
[Embedding] ecnu-embedding-small 文本向量化
    ↓
[SQLite] 多模态元数据 + 向量嵌入 持久化存储
```

## 核心技术亮点

| 技术方向 | 本系统实现 |
|---|---|
| **多模态数据管理** | SQLite 嵌入式关系数据库存储文本、图片路径、音频路径、向量嵌入，实现多模态非结构化数据的结构化管理 |
| **向量数据库** | 调用 `ecnu-embedding-small` 生成 1024 维文本向量，支持余弦相似度语义检索 |
| **数据驱动的 AI 系统** | 通过 Prompt Engineering 与结构化输出（JSON Schema），约束 LLM 生成可直接入库的标准化数据 |
| **数据治理** | LLM 自动提取标签（tags），实现教学资源的自动分类与元数据管理 |
| **嵌入式数据库** | SQLite 零部署、单文件存储，适合教育场景的轻量化部署需求 |

## 功能模块

### Tab 1: 智能绘本创作中心
- 输入通识科学概念，一键触发多模态生成流水线
- 实时展示生成进度（剧本 → 插画 → 配音 → 向量化 → 入库）
- 生成完成后以卡片布局展示3页绘本（图片 + 文本 + 音频播放器 + 自动标签）

### Tab 2: 数字多模态绘本馆
- **语义检索**：输入自然语言查询（如"关于动物的故事"），通过向量余弦相似度返回最相关的绘本
- **标签筛选**：按 LLM 自动提取的标签过滤绘本
- 浏览历史绘本的完整多模态内容
- 支持删除操作（级联清除数据库记录与本地文件）

### Tab 3: 数据分析中心
- 绘本总数、页面总数、资源文件数等核心指标
- 按概念分类的资源分布统计
- 按时间维度的生成趋势可视化

## 快速开始

### 1. 环境要求

- Python 3.9+
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）
- 网络连接（需访问 ECNU API 服务）

### 2. 安装 uv

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. 克隆项目并安装依赖

```bash
git clone https://github.com/JJasonSun/multimodal-edu-storybook-generator.git
cd multimodal-edu-storybook-generator
uv sync
```

### 4. 配置 API Key

系统内置了默认 API Key，可直接使用。如需更换，在启动后的左侧边栏中修改。

API Key 获取方式：登录 [ChatECNU](https://chat.ecnu.edu.cn)，点击头像 → 我的令牌。

### 5. 启动系统

```bash
uv run streamlit run app.py
```

启动后浏览器会自动打开 `http://localhost:8501`。

## 技术栈

| 组件 | 技术 | 说明 |
|---|---|---|
| 前端/后端 | Streamlit | Python Web 框架，单文件全栈 |
| 数据库 | SQLite (sqlite3) | 嵌入式关系型数据库，零安装 |
| 文本生成 | ecnu-plus (Qwen3.6-27B) | 结构化 JSON 输出，保障数据一致性 |
| 图像生成 | ecnu-image (Z-Image-Turbo) | 文生图，512×512 卡通风格 |
| 语音合成 | ecnu-tts (CosyVoice2-0.5B) | 文本转语音，支持多种音色 |
| 文本嵌入 | ecnu-embedding-small (bge-m3) | 1024 维向量，用于语义检索 |
| 向量计算 | NumPy | 余弦相似度计算 |
| 包管理 | uv | 快速 Python 依赖管理 |
| 版本控制 | Git + GitHub | 代码版本管理 |

## 数据库设计

### storybooks 表（绘本元数据）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增主键 |
| title | TEXT | 绘本标题（AI 生成） |
| concept | TEXT | 用户输入的科学概念 |
| tags | TEXT | JSON 数组，LLM 自动提取的分类标签 |
| created_at | TIMESTAMP | 创建时间 |

### storybook_pages 表（多模态页面详情）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增主键 |
| book_id | INTEGER FK | 关联 storybooks(id)，级联删除 |
| page_number | INTEGER | 页码 (1, 2, 3) |
| page_text | TEXT | 故事文本内容 |
| image_path | TEXT | 插画本地存储路径（元数据指针） |
| audio_path | TEXT | 配音本地存储路径（元数据指针） |

### storybook_embeddings 表（向量嵌入）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增主键 |
| book_id | INTEGER FK | 关联 storybooks(id)，UNIQUE，级联删除 |
| embedding | BLOB | 1024 维 float 向量的二进制存储 |
| created_at | TIMESTAMP | 创建时间 |

## 目录结构

```
multimodal-edu-storybook-generator/
├── app.py              # Streamlit 主程序（含全部业务逻辑）
├── pyproject.toml      # uv 项目配置与依赖声明
├── uv.lock             # 依赖锁定文件
├── .venv/              # Python 虚拟环境（uv 自动创建）
├── .gitignore          # Git 忽略规则
├── README.md           # 本文件
├── plan.md             # 项目计划文档
├── agent.md            # 系统架构与 API 调用规范
├── education.db        # SQLite 数据库（运行后自动生成）
└── static/
    ├── images/         # AI 生成的插画
    └── audio/          # AI 生成的配音
```

## API 用量参考

| 步骤 | 模型 | 预估消耗 |
|---|---|---|
| 剧本生成 | ecnu-plus | ~0.4 credits |
| 插画 ×3 | ecnu-image | 90 credits |
| 配音 ×3 | ecnu-tts | 15 credits |
| 向量嵌入 | ecnu-embedding-small | 0.05 credits |
| **合计** | | **~105.5 credits / 次** |

默认配额（5000 credits/天）下约可生成 47 本绘本/天。语义检索每次额外消耗 0.05 credits。

## 常见问题

**Q: 生成过程中报错怎么办？**
系统会在每一步展示进度，若某步失败会显示具体错误信息，已完成的步骤不受影响。

**Q: 图片/音频文件存在哪里？**
分别保存在 `static/images/` 和 `static/audio/` 目录下，文件名包含时间戳以避免冲突。

**Q: 如何更换 API Key？**
在启动系统后，通过左侧边栏的「系统配置」区域修改。

**Q: 向量检索的原理是什么？**
系统调用 `ecnu-embedding-small` 将每本绘本的全文转换为 1024 维向量并存储在 SQLite 中。检索时将查询文本同样向量化，通过余弦相似度计算与所有绘本的语义距离，返回最相关的 Top-K 结果。
