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
import struct
import time
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
import streamlit as st

# ============================================================
# 配置常量
# ============================================================
API_BASE_URL = "https://chat.ecnu.edu.cn/open/api/v1"
DEFAULT_API_KEY = os.environ.get("ECNU_API_KEY", "")

MODEL_TEXT = "ecnu-plus"                # 文本生成模型
MODEL_IMAGE = "ecnu-image"             # 图像生成模型
MODEL_TTS = "ecnu-tts"                 # 文本转语音模型
MODEL_EMBEDDING = "ecnu-embedding-small"  # 文本嵌入模型

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
                tags TEXT,
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

            CREATE TABLE IF NOT EXISTS storybook_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL UNIQUE,
                embedding BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES storybooks(id) ON DELETE CASCADE
            );
        """)
        conn.commit()

        # 兼容旧数据库：为 storybooks 表添加 tags 列（如果不存在）
        try:
            conn.execute("ALTER TABLE storybooks ADD COLUMN tags TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # 列已存在

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
6. 提供3-5个中文标签（tags），用于分类，如"自然科学"、"动物"、"植物"、"物理"、"天文"等

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
  ],
  "tags": ["标签1", "标签2", "标签3"]
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
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["title", "pages", "tags"]
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


def generate_embedding(api_key, text):
    """
    调用 ecnu-embedding-small 生成文本向量
    返回: numpy array (1024,)
    """
    url = f"{API_BASE_URL}/embeddings"

    payload = {
        "model": MODEL_EMBEDDING,
        "input": text,
    }

    response = requests.post(url, headers=get_headers(api_key), json=payload, timeout=60)
    response.raise_for_status()

    embedding_list = response.json()["data"][0]["embedding"]
    return np.array(embedding_list, dtype=np.float32)


def embedding_to_blob(embedding):
    """将 numpy 向量转为 BLOB 二进制"""
    return struct.pack(f'{len(embedding)}f', *embedding.tolist())


def blob_to_embedding(blob):
    """将 BLOB 二进制还原为 numpy 向量"""
    count = len(blob) // 4
    return np.array(struct.unpack(f'{count}f', blob), dtype=np.float32)


# ============================================================
# 业务逻辑模块
# ============================================================

def save_book(concept, title, pages_data, tags=None, embedding=None):
    """
    将绘本数据持久化到数据库和本地文件
    pages_data: [{"page_text": str, "image_path": str, "audio_path": str}, ...]
    tags: list[str] 标签列表
    embedding: numpy array 向量
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
        cursor = conn.execute(
            "INSERT INTO storybooks (title, concept, tags) VALUES (?, ?, ?)",
            (title, concept, tags_json)
        )
        book_id = cursor.lastrowid

        for i, page in enumerate(pages_data):
            conn.execute(
                "INSERT INTO storybook_pages (book_id, page_number, page_text, image_path, audio_path) VALUES (?, ?, ?, ?, ?)",
                (book_id, i + 1, page["page_text"], page.get("image_path"), page.get("audio_path"))
            )

        if embedding is not None:
            blob = embedding_to_blob(embedding)
            conn.execute(
                "INSERT INTO storybook_embeddings (book_id, embedding) VALUES (?, ?)",
                (book_id, blob)
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

    # 再删除数据库记录（CASCADE 会自动删除 pages 和 embeddings）
    conn = get_connection()
    try:
        conn.execute("DELETE FROM storybooks WHERE id = ?", (book_id,))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise RuntimeError(f"数据库删除失败: {e}")
    finally:
        conn.close()


def search_books_by_vector(api_key, query, top_k=5):
    """向量语义检索：返回与 query 最相似的 top_k 本绘本"""
    query_embedding = generate_embedding(api_key, query)

    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT se.book_id, se.embedding
            FROM storybook_embeddings se
        """).fetchall()

        if not rows:
            return []

        results = []
        for row in rows:
            book_id = row["book_id"]
            stored_embedding = blob_to_embedding(row["embedding"])
            # 余弦相似度
            dot = np.dot(query_embedding, stored_embedding)
            norm = np.linalg.norm(query_embedding) * np.linalg.norm(stored_embedding)
            similarity = dot / norm if norm > 0 else 0.0
            results.append((book_id, float(similarity)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    finally:
        conn.close()


def get_all_tags():
    """获取所有已使用的标签（去重）"""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT tags FROM storybooks WHERE tags IS NOT NULL").fetchall()
        all_tags = set()
        for row in rows:
            try:
                tags = json.loads(row["tags"])
                all_tags.update(tags)
            except (json.JSONDecodeError, TypeError):
                pass
        return sorted(all_tags)
    finally:
        conn.close()


def search_books_by_tag(tag):
    """按标签筛选绘本"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, concept, tags, created_at FROM storybooks WHERE tags IS NOT NULL"
        ).fetchall()
        results = []
        for row in rows:
            try:
                tags = json.loads(row["tags"])
                if tag in tags:
                    results.append(dict(row))
            except (json.JSONDecodeError, TypeError):
                pass
        return results
    finally:
        conn.close()


def get_analytics_data():
    """获取数据分析所需的统计信息"""
    conn = get_connection()
    try:
        stats = {}
        stats["total_books"] = conn.execute("SELECT COUNT(*) FROM storybooks").fetchone()[0]
        stats["total_pages"] = conn.execute("SELECT COUNT(*) FROM storybook_pages").fetchone()[0]

        # 图片和音频资源数
        stats["total_images"] = conn.execute(
            "SELECT COUNT(*) FROM storybook_pages WHERE image_path IS NOT NULL"
        ).fetchone()[0]
        stats["total_audios"] = conn.execute(
            "SELECT COUNT(*) FROM storybook_pages WHERE audio_path IS NOT NULL"
        ).fetchone()[0]

        # 按概念分组统计
        concept_rows = conn.execute(
            "SELECT concept, COUNT(*) as cnt FROM storybooks GROUP BY concept ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        stats["concept_distribution"] = {row["concept"]: row["cnt"] for row in concept_rows}

        # 按日期统计生成趋势
        date_rows = conn.execute(
            "SELECT DATE(created_at) as dt, COUNT(*) as cnt FROM storybooks GROUP BY DATE(created_at) ORDER BY dt"
        ).fetchall()
        stats["daily_trend"] = {row["dt"]: row["cnt"] for row in date_rows}

        # 标签频率
        tag_rows = conn.execute("SELECT tags FROM storybooks WHERE tags IS NOT NULL").fetchall()
        tag_counter = {}
        for row in tag_rows:
            try:
                tags = json.loads(row["tags"])
                for t in tags:
                    tag_counter[t] = tag_counter.get(t, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
        stats["tag_frequency"] = dict(sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)[:15])

        # 资源目录大小
        image_size = sum(
            os.path.getsize(os.path.join(IMAGE_DIR, f))
            for f in os.listdir(IMAGE_DIR)
            if os.path.isfile(os.path.join(IMAGE_DIR, f)) and f != ".gitkeep"
        )
        audio_size = sum(
            os.path.getsize(os.path.join(AUDIO_DIR, f))
            for f in os.listdir(AUDIO_DIR)
            if os.path.isfile(os.path.join(AUDIO_DIR, f)) and f != ".gitkeep"
        )
        stats["image_size_mb"] = round(image_size / (1024 * 1024), 2)
        stats["audio_size_mb"] = round(audio_size / (1024 * 1024), 2)

        return stats
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

            # ---- Step 5: 持久化存储 ----
            st.write("💾 正在保存到数据库...")
            try:
                book_id = save_book(concept.strip(), title, pages_data, tags=tags, embedding=embedding)
                st.write(f"✅ 保存完成（绘本 ID: {book_id}）")
            except Exception as e:
                status.update(label="保存失败", state="error")
                st.error(f"数据保存失败: {e}")
                return

            status.update(label="生成完成！", state="complete")

            # ---- Step 4: 向量嵌入 ----
            st.write("🧮 正在生成文本向量...")
            all_text = " ".join(p["page_text"] for p in pages)
            embedding = None
            try:
                embedding = generate_embedding(api_key, all_text)
                st.write("✅ 向量嵌入完成")
            except Exception as e:
                st.warning(f"向量嵌入失败（不影响绘本生成）: {e}")

        # ---- 展示生成的绘本 ----
        st.markdown("---")
        st.markdown(f"## 🎉 {title}")

        # 展示标签
        tags = story.get("tags", [])
        if tags:
            tag_str = " ".join(f"`{t}`" for t in tags)
            st.markdown(f"**标签：** {tag_str}")

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

    # ---- 搜索与筛选区 ----
    col_search, col_tag = st.columns([2, 1])

    with col_search:
        search_query = st.text_input(
            "🔍 语义搜索",
            placeholder="输入自然语言描述，如：关于太阳系的故事",
            label_visibility="collapsed",
        )

    with col_tag:
        all_tags = get_all_tags()
        selected_tag = st.selectbox(
            "🏷️ 按标签筛选",
            options=["全部标签"] + all_tags,
            label_visibility="collapsed",
        ) if all_tags else "全部标签"

    # ---- 搜索逻辑 ----
    filtered_books = None
    if search_query.strip() and api_key:
        with st.spinner("正在语义检索..."):
            try:
                results = search_books_by_vector(api_key, search_query.strip())
                if results:
                    book_ids = [r[0] for r in results]
                    filtered_books = []
                    for bid in book_ids:
                        info = get_book_info(bid)
                        if info:
                            filtered_books.append(info)
                    st.caption(f"找到 {len(filtered_books)} 本相关绘本")
                else:
                    st.info("未找到相关绘本")
                    filtered_books = []
            except Exception as e:
                st.warning(f"语义检索失败: {e}，回退到列表模式")

    elif selected_tag != "全部标签":
        filtered_books = search_books_by_tag(selected_tag)
        st.caption(f"标签「{selected_tag}」下有 {len(filtered_books)} 本绘本")

    # 确定展示列表
    display_books = filtered_books if filtered_books is not None else books

    if not display_books:
        st.info("📭 没有匹配的绘本")
        return

    # 绘本选择
    book_options = {f"{b['title']}（{b['concept']}）— {b['created_at']}": b['id'] for b in display_books}
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
    tags_str = ""
    if book_info.get("tags"):
        try:
            tags = json.loads(book_info["tags"])
            tags_str = "　".join(f"`{t}`" for t in tags)
        except (json.JSONDecodeError, TypeError):
            pass
    st.caption(f"科学概念：{book_info['concept']}　|　创建时间：{book_info['created_at']}")
    if tags_str:
        st.markdown(f"**标签：** {tags_str}")

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


def tab_analytics():
    """Tab 3: 数据分析中心"""
    stats = get_analytics_data()

    if stats["total_books"] == 0:
        st.info("📭 暂无数据，请先生成一些绘本！")
        return

    # 核心指标
    st.markdown("#### 📊 系统概览")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("绘本总数", stats["total_books"])
    col2.metric("页面总数", stats["total_pages"])
    col3.metric("插画资源", stats["total_images"])
    col4.metric("音频资源", stats["total_audios"])

    st.markdown("---")

    # 资源占用
    col_res1, col_res2 = st.columns(2)
    with col_res1:
        st.metric("插画存储", f"{stats['image_size_mb']} MB")
    with col_res2:
        st.metric("音频存储", f"{stats['audio_size_mb']} MB")

    st.markdown("---")

    # 概念分布
    if stats["concept_distribution"]:
        st.markdown("#### 📚 概念分类分布")
        st.bar_chart(stats["concept_distribution"])

    # 生成趋势
    if stats["daily_trend"]:
        st.markdown("#### 📈 生成趋势")
        st.line_chart(stats["daily_trend"])

    # 标签频率
    if stats["tag_frequency"]:
        st.markdown("#### 🏷️ 标签频率 Top 15")
        st.bar_chart(stats["tag_frequency"])


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
        # 优先级：环境变量 > Streamlit secrets > 用户手动输入
        default_key = DEFAULT_API_KEY or st.secrets.get("ECNU_API_KEY", "")
        api_key = st.text_input(
            "ECNU API Key",
            value=default_key,
            type="password",
            help="在 chat.ecnu.edu.cn 获取 API Key，或设置环境变量 ECNU_API_KEY"
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
    tab1, tab2, tab3 = st.tabs(["🎨 智能绘本创作中心", "📚 数字多模态绘本馆", "📊 数据分析中心"])

    with tab1:
        tab_creation_center(api_key)

    with tab2:
        tab_library(api_key)

    with tab3:
        tab_analytics()


if __name__ == "__main__":
    main()
