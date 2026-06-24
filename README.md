# 面向低幼通识教育的多模态教学资源自动生成与数据管理系统

基于 Streamlit + SQLite + ECNU API 的一键有声科普绘本生成系统。用户输入一个通识科学概念，系统自动调用大语言模型的多模态能力（文本生成、文生图、文本转语音），生成包含故事剧本、AI插画、AI配音的3页有声科普绘本，并持久化存储到本地数据库。

## 系统架构

```
用户输入概念 → ecnu-plus 剧本生成 → ecnu-image 插画生成 ×3 → ecnu-tts 配音生成 ×3 → SQLite 持久化
```

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
git clone <repository-url>
cd CS_edu
uv sync
```

`uv sync` 会自动创建 `.venv` 虚拟环境并安装 `pyproject.toml` 中声明的所有依赖。

### 4. 配置 API Key

系统内置了默认 API Key，可直接使用。如需更换，在启动后的左侧边栏中修改。

API Key 获取方式：登录 [ChatECNU](https://chat.ecnu.edu.cn)，点击头像 → 我的令牌。

### 5. 启动系统

```bash
uv run streamlit run app.py
```

启动后浏览器会自动打开 `http://localhost:8501`。

## 功能说明

### Tab 1: 智能绘本创作中心

1. 在输入框中输入科学概念（如"光合作用"、"彩虹是怎么形成的"）
2. 点击「一键启动多模态生成」按钮
3. 系统按顺序执行：剧本生成 → 插画绘制 → 配音合成 → 数据保存
4. 完成后以卡片布局展示3页绘本（图片 + 文本 + 音频播放器）

### Tab 2: 数字多模态绘本馆

1. 从下拉菜单选择历史绘本
2. 查看绘本的3页完整内容（图片、文本、音频）
3. 可删除不需要的绘本（同时清除数据库记录和本地文件）

## 目录结构

```
CS_edu/
├── app.py              # 主程序
├── pyproject.toml      # uv 项目配置与依赖声明
├── uv.lock             # 依赖锁定文件
├── .venv/              # Python 虚拟环境（uv 自动创建）
├── .gitignore          # Git 忽略规则
├── README.md           # 本文件
├── plan.md             # 项目计划
├── agent.md            # 架构文档
├── education.db        # SQLite 数据库（自动生成，已 gitignore）
└── static/
    ├── images/         # AI 生成的插画（已 gitignore）
    └── audio/          # AI 生成的配音（已 gitignore）
```

## 技术栈

| 组件 | 技术 |
|---|---|
| 前端/后端 | Streamlit |
| 数据库 | SQLite (sqlite3) |
| AI 接口 | requests + ECNU API |
| 文本生成 | ecnu-plus (Qwen3.6-27B) |
| 图像生成 | ecnu-image (Z-Image-Turbo) |
| 语音合成 | ecnu-tts (CosyVoice2-0.5B) |

## 数据库设计

### storybooks 表（绘本元数据）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增主键 |
| title | TEXT | 绘本标题（AI 生成） |
| concept | TEXT | 用户输入的科学概念 |
| created_at | TIMESTAMP | 创建时间 |

### storybook_pages 表（页面详情）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增主键 |
| book_id | INTEGER FK | 关联 storybooks(id)，级联删除 |
| page_number | INTEGER | 页码 (1, 2, 3) |
| page_text | TEXT | 故事文本 |
| image_path | TEXT | 插画本地路径 |
| audio_path | TEXT | 配音本地路径 |

## API 用量参考

| 步骤 | 模型 | 预估消耗 |
|---|---|---|
| 剧本生成 | ecnu-plus | ~0.4 credits |
| 插画 ×3 | ecnu-image | 90 credits |
| 配音 ×3 | ecnu-tts | 15 credits |
| **合计** | | **~105 credits / 次** |

默认配额（5000 credits/天）下约可生成 47 本绘本/天。

## 常见问题

**Q: 生成过程中报错怎么办？**
系统会在每一步展示进度，若某步失败会显示具体错误信息，已完成的步骤不受影响。

**Q: 图片/音频文件存在哪里？**
分别保存在 `static/images/` 和 `static/audio/` 目录下，文件名包含时间戳以避免冲突。

**Q: 如何更换 API Key？**
在启动系统后，通过左侧边栏的「系统配置」区域修改。
