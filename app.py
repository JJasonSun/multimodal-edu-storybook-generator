"""
面向低幼通识教育的多模态教学资源自动生成与数据管理系统
=====================================================
基于 Streamlit + SQLite + ECNU API
功能：一键生成包含故事剧本、AI插画、AI配音的3页有声科普绘本
"""

import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

# ============================================================
# 配置常量
# ============================================================
API_BASE_URL = "https://chat.ecnu.edu.cn/open/api/v1"
DEFAULT_API_KEY = "sk-3a6d410e57ff48ff8b010d891a95ecc1"

MODEL_TEXT = "ecnu-plus"       # 文本生成模型
MODEL_IMAGE = "ecnu-image"     # 图像生成模型
MODEL_TTS = "ecnu-tts"         # 文本转语音模型

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "education.db")
IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "images")
AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "audio")

# 确保资源目录存在
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# ============================================================
# 数据库模块
# ============================================================

def get_connection():
    """获取 SQLite 数据库连接，启用外键约束"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """初始化数据库表结构（幂等操作）"""
    conn = get_connection()
    try:
        conn.executescript("""
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
        """)
        conn.commit()
    except sqlite3.Error as e:
        st.error(f"数据库初始化失败: {e}")
    finally:
        conn.close()


# ============================================================
# API 调用模块
# ============================================================

def get_headers(api_key):
    """构建请求头"""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def generate_story(api_key, concept):
    """
    调用 ecnu-plus 生成绘本剧本
    返回: {"title": str, "pages": [{"page_text": str, "image_prompt": str}, ...]}
    """
    url = f"{API_BASE_URL}/chat/completions"

    system_prompt = """你是一位专业的儿童科普绘本作家。请根据用户提供的科学概念，创作一个3页的童话故事绘本。

要求：
1. 故事语言要简单、生动、适合3-8岁儿童
2. 每页约100字左右
3. 要融入科学知识，但用童话的方式表达
4. 每页需提供一个英文画面描述（image_prompt），用于AI绘图
5. image_prompt 必须是英文，描述画面细节，风格为 cute cartoon illustration for children

请严格按照以下JSON格式返回，不要返回其他内容：
{
  "title": "绘本标题",
  "pages": [
    {
      "page_text": "第1页的故事文本",
      "image_prompt": "English prompt for page 1 illustration, describe scene in detail, cute cartoon style for children"
    },
    {
      "page_text": "第2页的故事文本",
      "image_prompt": "English prompt for page 2 illustration"
    },
    {
      "page_text": "第3页的故事文本",
      "image_prompt": "English prompt for page 3 illustration"
    }
  ]
}"""

    # 结构化输出的 JSON Schema
    json_schema = {
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
    }

    payload = {
        "model": MODEL_TEXT,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请为通识科学概念「{concept}」创作一本3页的儿童科普绘本。"}
        ],
        "response_format": json_schema,
        "max_tokens": 2048,
    }

    response = requests.post(url, headers=get_headers(api_key), json=payload, timeout=120)
    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]

    # 尝试解析 JSON
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: 用正则提取 JSON 块
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError("无法从模型响应中解析出有效的 JSON 数据")

    # 验证结构
    if "title" not in data or "pages" not in data:
        raise ValueError("返回数据缺少 title 或 pages 字段")
    if len(data["pages"]) < 3:
        raise ValueError(f"期望3页内容，实际得到{len(data['pages'])}页")

    return data


def generate_image(api_key, prompt, save_path):
    """
    调用 ecnu-image 生成插画并保存到本地
    返回: 保存路径
    """
    url = f"{API_BASE_URL}/images/generations"

    # 截断超长 prompt
    if len(prompt) > 1024:
        prompt = prompt[:1024]

    payload = {
        "model": MODEL_IMAGE,
        "prompt": prompt,
        "size": "512x512",
        "response_format": "url",
    }

    response = requests.post(url, headers=get_headers(api_key), json=payload, timeout=120)
    response.raise_for_status()

    image_url = response.json()["data"][0]["url"]

    # 下载图片
    img_response = requests.get(image_url, timeout=60)
    img_response.raise_for_status()

    with open(save_path, "wb") as f:
        f.write(img_response.content)

    return save_path


def generate_audio(api_key, text, save_path):
    """
    调用 ecnu-tts 生成语音并保存到本地
    返回: 保存路径
    """
    url = f"{API_BASE_URL}/audio/speech"

    # 截断超长文本
    if len(text) > 4096:
        text = text[:4096]

    payload = {
        "model": MODEL_TTS,
        "input": text,
        "voice": "liwa",
        "response_format": "mp3",
        "speed": 0.9,
    }

    response = requests.post(url, headers=get_headers(api_key), json=payload, timeout=120)
    response.raise_for_status()

    with open(save_path, "wb") as f:
        f.write(response.content)

    return save_path


# ============================================================
# 业务逻辑模块
# ============================================================

def save_book(concept, title, pages_data):
    """
    将绘本数据持久化到数据库和本地文件
    pages_data: [{"page_text": str, "image_path": str, "audio_path": str}, ...]
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        cursor = conn.execute(
            "INSERT INTO storybooks (title, concept) VALUES (?, ?)",
            (title, concept)
        )
        book_id = cursor.lastrowid

        for i, page in enumerate(pages_data):
            conn.execute(
                "INSERT INTO storybook_pages (book_id, page_number, page_text, image_path, audio_path) VALUES (?, ?, ?, ?, ?)",
                (book_id, i + 1, page["page_text"], page.get("image_path"), page.get("audio_path"))
            )

        conn.commit()
        return book_id
    except sqlite3.Error as e:
        conn.rollback()
        raise RuntimeError(f"数据库写入失败: {e}")
    finally:
        conn.close()


def get_all_books():
    """获取所有绘本列表"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, concept, created_at FROM storybooks ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_book_pages(book_id):
    """获取指定绘本的所有页面"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT page_number, page_text, image_path, audio_path FROM storybook_pages WHERE book_id = ? ORDER BY page_number",
            (book_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_book_info(book_id):
    """获取绘本基本信息"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, title, concept, created_at FROM storybooks WHERE id = ?",
            (book_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_book(book_id):
    """删除绘本（数据库记录 + 本地文件）"""
    # 先删除本地文件
    pages = get_book_pages(book_id)
    for page in pages:
        for path_key in ("image_path", "audio_path"):
            file_path = page.get(path_key)
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass  # 文件删除失败，静默处理

    # 再删除数据库记录（CASCADE 会自动删除 pages）
    conn = get_connection()
    try:
        conn.execute("DELETE FROM storybooks WHERE id = ?", (book_id,))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise RuntimeError(f"数据库删除失败: {e}")
    finally:
        conn.close()


# ============================================================
# Streamlit 前端
# ============================================================

def render_page_card(page, index):
    """渲染单页绘本卡片"""
    with st.container():
        st.markdown(f"### 📖 第 {index} 页")

        # 显示插画
        image_path = page.get("image_path")
        if image_path and os.path.exists(image_path):
            st.image(image_path, use_container_width=True)
        else:
            st.warning("插画暂未生成")

        # 显示故事文本
        st.markdown(f"> {page['page_text']}")

        # 显示音频播放器
        audio_path = page.get("audio_path")
        if audio_path and os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                st.audio(f.read(), format="audio/mp3")
        else:
            st.warning("配音暂未生成")

        st.divider()


def tab_creation_center(api_key):
    """Tab 1: 智能绘本创作中心"""
    st.markdown("#### 输入一个科学概念，AI 将为你自动生成一本3页有声科普绘本")
    st.markdown("")

    concept = st.text_input(
        "科学概念",
        placeholder="例如：光合作用、彩虹是怎么形成的、为什么天空是蓝色的...",
        label_visibility="collapsed",
    )

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        generate_clicked = st.button("🚀 一键启动多模态生成", type="primary", use_container_width=True)

    if generate_clicked:
        if not concept.strip():
            st.warning("请先输入一个科学概念！")
            return

        if not api_key:
            st.error("请在左侧边栏配置 API Key")
            return

        pages_data = []

        # ---- Step 1: 剧本生成 ----
        with st.status("🎨 正在创作中...", expanded=True) as status:
            st.write("📝 正在构思剧本...")
            try:
                story = generate_story(api_key, concept.strip())
            except requests.exceptions.Timeout:
                status.update(label="生成失败", state="error")
                st.error("剧本生成超时，请稍后重试")
                return
            except requests.exceptions.HTTPError as e:
                status.update(label="生成失败", state="error")
                error_detail = _parse_api_error(e)
                st.error(f"剧本生成 API 调用失败: {error_detail}")
                return
            except (json.JSONDecodeError, ValueError) as e:
                status.update(label="生成失败", state="error")
                st.error(f"剧本数据解析失败: {e}")
                return
            except Exception as e:
                status.update(label="生成失败", state="error")
                st.error(f"剧本生成异常: {e}")
                return

            title = story["title"]
            pages = story["pages"]
            st.write(f"✅ 剧本完成：**{title}**")

            # ---- Step 2: 插画生成 ----
            for i in range(3):
                st.write(f"🖼️ 正在绘制第 {i+1} 页插画...")
                image_prompt = pages[i].get("image_prompt", "")
                if not image_prompt:
                    st.warning(f"第 {i+1} 页缺少画面描述，跳过插画生成")
                    pages_data.append({
                        "page_text": pages[i]["page_text"],
                        "image_path": None,
                        "audio_path": None,
                    })
                    continue

                # 用时间戳+随机数生成唯一文件名
                unique_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
                image_path = os.path.join(IMAGE_DIR, f"{unique_id}_page{i+1}.png")

                try:
                    generate_image(api_key, image_prompt, image_path)
                    st.write(f"✅ 第 {i+1} 页插画完成")
                except Exception as e:
                    st.warning(f"第 {i+1} 页插画生成失败: {e}")
                    image_path = None

                pages_data.append({
                    "page_text": pages[i]["page_text"],
                    "image_path": image_path,
                    "audio_path": None,
                })

            # ---- Step 3: 语音合成 ----
            for i in range(3):
                st.write(f"🔊 正在生成第 {i+1} 页配音...")
                page_text = pages[i]["page_text"]
                unique_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
                audio_path = os.path.join(AUDIO_DIR, f"{unique_id}_page{i+1}.mp3")

                try:
                    generate_audio(api_key, page_text, audio_path)
                    st.write(f"✅ 第 {i+1} 页配音完成")
                except Exception as e:
                    st.warning(f"第 {i+1} 页配音生成失败: {e}")
                    audio_path = None

                pages_data[i]["audio_path"] = audio_path

            # ---- Step 4: 持久化存储 ----
            st.write("💾 正在保存到数据库...")
            try:
                book_id = save_book(concept.strip(), title, pages_data)
                st.write(f"✅ 保存完成（绘本 ID: {book_id}）")
            except Exception as e:
                status.update(label="保存失败", state="error")
                st.error(f"数据保存失败: {e}")
                return

            status.update(label="生成完成！", state="complete")

        # ---- 展示生成的绘本 ----
        st.markdown("---")
        st.markdown(f"## 🎉 {title}")

        cols = st.columns(3)
        for i in range(3):
            with cols[i]:
                render_page_card(pages_data[i], i + 1)


def tab_library(api_key):
    """Tab 2: 数字多模态绘本馆"""
    books = get_all_books()

    if not books:
        st.info("📭 绘本馆暂无藏书，请先在「智能绘本创作中心」生成第一本绘本！")
        return

    # 绘本选择
    book_options = {f"{b['title']}（{b['concept']}）— {b['created_at']}": b['id'] for b in books}
    selected_label = st.selectbox("选择一本绘本", options=list(book_options.keys()))

    if not selected_label:
        return

    book_id = book_options[selected_label]
    book_info = get_book_info(book_id)
    pages = get_book_pages(book_id)

    if not pages:
        st.warning("该绘本暂无页面数据")
        return

    # 绘本信息
    st.markdown(f"## 📖 {book_info['title']}")
    st.caption(f"科学概念：{book_info['concept']}　|　创建时间：{book_info['created_at']}")

    st.markdown("---")

    # 展示3页内容
    cols = st.columns(3)
    for i, page in enumerate(pages):
        with cols[i]:
            render_page_card(page, page["page_number"])

    # 删除按钮
    st.markdown("---")
    col_del, _ = st.columns([1, 3])
    with col_del:
        if st.button("🗑️ 删除这本绘本", type="secondary", use_container_width=True):
            try:
                delete_book(book_id)
                st.success("绘本已删除")
                st.rerun()
            except Exception as e:
                st.error(f"删除失败: {e}")


def _parse_api_error(error):
    """解析 API 错误信息"""
    try:
        resp = error.response
        detail = resp.json().get("detail", "")
        if isinstance(detail, list):
            return "; ".join(d.get("msg", str(d)) for d in detail)
        return detail or resp.text
    except Exception:
        return str(error)


# ============================================================
# 主程序入口
# ============================================================

def main():
    st.set_page_config(
        page_title="多模态教学资源自动生成系统",
        page_icon="📚",
        layout="wide",
    )

    st.title("📚 面向低幼通识教育的多模态教学资源自动生成与数据管理系统")
    st.caption("利用大语言模型的多模态能力，一键生成包含故事剧本、AI插画、AI配音的3页有声科普绘本")

    # 初始化数据库
    init_database()

    # 侧边栏配置
    with st.sidebar:
        st.header("⚙️ 系统配置")
        api_key = st.text_input(
            "ECNU API Key",
            value=DEFAULT_API_KEY,
            type="password",
            help="在 chat.ecnu.edu.cn 获取 API Key"
        )
        st.markdown("---")
        st.markdown("### 📊 系统信息")
        st.markdown(f"数据库路径: `{DB_PATH}`")
        st.markdown(f"图片目录: `{IMAGE_DIR}`")
        st.markdown(f"音频目录: `{AUDIO_DIR}`")

        # 显示绘本总数
        try:
            books = get_all_books()
            st.markdown(f"已生成绘本: **{len(books)}** 本")
        except Exception:
            pass

    # 主界面标签页
    tab1, tab2 = st.tabs(["🎨 智能绘本创作中心", "📚 数字多模态绘本馆"])

    with tab1:
        tab_creation_center(api_key)

    with tab2:
        tab_library(api_key)


if __name__ == "__main__":
    main()
