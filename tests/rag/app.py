"""
Trợ lý hỏi-đáp Luật Đất đai Việt Nam (RAG demo)
================================================

Cách hoạt động (không cần biết kỹ thuật, chỉ cần dùng):
1. Tải lên các file PDF (nghị định, thông tư, luật...) ở thanh bên trái.
2. App tự động đọc nội dung, chia nhỏ thành từng đoạn, và lưu vào Pinecone
   (một cơ sở dữ liệu vector) trong index tên "luat-dat-dai-vn". Việc "biến chữ
   thành vector" (embedding) được Pinecone tự làm luôn (integrated embedding),
   nên không cần thêm dịch vụ embedding riêng.
3. Gõ câu hỏi ở khung chính. App tìm những đoạn văn bản liên quan nhất trong
   Pinecone (có sắp xếp lại độ liên quan bằng rerank), rồi gửi cho Groq AI để
   Groq soạn câu trả lời dựa trên đúng nội dung tìm được.

Chạy thử:
    pip install -r requirements.txt
    streamlit run app.py
"""

import io
import re

import streamlit as st
from dotenv import load_dotenv, find_dotenv
from pinecone import Pinecone
from groq import Groq
from pypdf import PdfReader

# Tự tìm file .env gần nhất (trong thư mục này hoặc thư mục gốc dự án) để lấy API key
load_dotenv(find_dotenv(usecwd=True))

# ==============================================================================
# CẤU HÌNH
# ==============================================================================
INDEX_NAME = "luat-dat-dai-vn"
NAMESPACE = "van-ban-luat"

# Model embedding do Pinecone lưu trữ sẵn — hỗ trợ đa ngôn ngữ (kể cả tiếng Việt),
# không cần tự chạy hay trả tiền cho một dịch vụ embedding riêng.
EMBED_MODEL = "llama-text-embed-v2"
RERANK_MODEL = "bge-reranker-v2-m3"
CLOUD = "aws"
REGION = "us-east-1"

GROQ_MODEL = "openai/gpt-oss-120b"

CHUNK_SIZE = 1200      # số ký tự mỗi đoạn
CHUNK_OVERLAP = 200    # số ký tự lặp lại giữa 2 đoạn liền kề, để không mất ngữ cảnh
UPSERT_BATCH_SIZE = 90 # số đoạn gửi lên Pinecone mỗi lần

st.set_page_config(
    page_title="Trợ lý Luật Đất đai (RAG)",
    page_icon="⚖️",
    layout="wide",
)


# ==============================================================================
# KẾT NỐI DỊCH VỤ (Pinecone / Groq)
# ==============================================================================
@st.cache_resource(show_spinner=False)
def get_clients():
    import os

    pinecone_key = os.getenv("PINECONE_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")

    missing = [
        name for name, val in [("PINECONE_API_KEY", pinecone_key), ("GROQ_API_KEY", groq_key)]
        if not val
    ]
    if missing:
        st.error(
            "Thiếu cấu hình: " + ", ".join(missing) +
            ". Hãy đặt các biến này trong file .env (xem .env.example) rồi chạy lại app."
        )
        st.stop()

    pc = Pinecone(api_key=pinecone_key)
    groq_client = Groq(api_key=groq_key)
    return pc, groq_client


@st.cache_resource(show_spinner=False)
def get_index(_pc: Pinecone):
    """Tạo index Pinecone (nếu chưa có) rồi trả về đối tượng để đọc/ghi dữ liệu."""
    if not _pc.has_index(INDEX_NAME):
        _pc.create_index_for_model(
            name=INDEX_NAME,
            cloud=CLOUD,
            region=REGION,
            embed={
                "model": EMBED_MODEL,
                "field_map": {"text": "text"},
            },
        )
    return _pc.Index(INDEX_NAME)


# ==============================================================================
# ĐỌC & CHIA NHỎ FILE PDF
# ==============================================================================
def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Chia văn bản dài thành từng đoạn nhỏ, có phần lặp lại (overlap) giữa các đoạn
    để không bị mất ngữ cảnh ở ranh giới đoạn."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    chunks = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # cố gắng cắt tại khoảng trắng gần cuối đoạn cho đỡ cụt câu
        if end < len(text):
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def safe_id_prefix(filename: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", filename)


# ==============================================================================
# LƯU VÀO PINECONE
# ==============================================================================
def process_and_upsert(index, uploaded_files):
    all_records = []
    file_summaries = []

    for f in uploaded_files:
        text = extract_pdf_text(f.getvalue())
        chunks = chunk_text(text)
        prefix = safe_id_prefix(f.name)
        for i, chunk in enumerate(chunks):
            all_records.append({
                "_id": f"{prefix}-{i}",
                "text": chunk,
                "source": f.name,
            })
        file_summaries.append((f.name, len(chunks)))

    if not all_records:
        return file_summaries, 0

    progress = st.progress(0.0, text="Đang lưu vào Pinecone...")
    total = len(all_records)
    for start in range(0, total, UPSERT_BATCH_SIZE):
        batch = all_records[start:start + UPSERT_BATCH_SIZE]
        index.upsert_records(namespace=NAMESPACE, records=batch)
        progress.progress(min((start + len(batch)) / total, 1.0), text="Đang lưu vào Pinecone...")
    progress.empty()

    return file_summaries, total


# ==============================================================================
# TÌM KIẾM + TRẢ LỜI
# ==============================================================================
def search(index, query: str, top_k: int = 5):
    results = index.search(
        namespace=NAMESPACE,
        query={"top_k": top_k, "inputs": {"text": query}},
        rerank={
            "model": RERANK_MODEL,
            "top_n": min(top_k, 4),
            "rank_fields": ["text"],
        },
    )
    return results["result"]["hits"]


def build_context(hits) -> str:
    blocks = []
    for hit in hits:
        source = hit["fields"].get("source", "không rõ nguồn")
        text = hit["fields"].get("text", "")
        blocks.append(f"[Nguồn: {source}]\n{text}")
    return "\n\n---\n\n".join(blocks)


def ask_groq(groq_client, query: str, context: str) -> str:
    system_prompt = (
        "Bạn là trợ lý pháp lý, chuyên trả lời câu hỏi về luật đất đai Việt Nam. "
        "Chỉ trả lời dựa trên nội dung được cung cấp trong phần NGỮ CẢNH bên dưới. "
        "Nếu ngữ cảnh không đủ thông tin để trả lời, hãy nói rõ là tài liệu hiện có "
        "chưa đề cập, đừng tự bịa ra thông tin. Trả lời ngắn gọn, rõ ràng, bằng tiếng Việt, "
        "và trích dẫn tên nguồn tài liệu liên quan khi có thể."
    )
    user_prompt = f"NGỮ CẢNH:\n{context}\n\nCÂU HỎI: {query}"

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content


# ==============================================================================
# GIAO DIỆN
# ==============================================================================
pc, groq_client = get_clients()
index = get_index(pc)

st.title("⚖️ Trợ lý hỏi-đáp Luật Đất đai Việt Nam")
st.caption("Tải văn bản PDF lên, sau đó đặt câu hỏi — hệ thống sẽ trả lời dựa trên đúng nội dung tài liệu.")

with st.sidebar:
    st.header("1. Tải văn bản PDF")
    uploaded_files = st.file_uploader(
        "Chọn một hoặc nhiều file PDF",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if st.button("📥 Xử lý & lưu vào Pinecone", disabled=not uploaded_files):
        with st.spinner("Đang đọc nội dung PDF..."):
            summaries, total_chunks = process_and_upsert(index, uploaded_files)
        if total_chunks == 0:
            st.warning("Không đọc được nội dung văn bản nào từ các file đã chọn.")
        else:
            st.success(f"Đã lưu {total_chunks} đoạn văn bản từ {len(summaries)} file.")
            for name, n in summaries:
                st.caption(f"• {name}: {n} đoạn")

    st.divider()
    try:
        stats = index.describe_index_stats()
        ns_stats = stats.get("namespaces", {}).get(NAMESPACE, {})
        st.metric("Số đoạn văn bản đã lưu", ns_stats.get("vector_count", 0))
    except Exception:
        pass

    with st.expander("⚠️ Xóa toàn bộ dữ liệu đã lưu"):
        confirm = st.checkbox("Tôi chắc chắn muốn xóa hết")
        if st.button("Xóa dữ liệu", disabled=not confirm):
            index.delete(namespace=NAMESPACE, delete_all=True)
            st.success("Đã xóa toàn bộ dữ liệu trong index.")

st.header("2. Đặt câu hỏi")
query = st.text_input("Câu hỏi của bạn", placeholder="Ví dụ: Điều kiện để được cấp sổ đỏ là gì?")
ask_clicked = st.button("🔍 Tìm câu trả lời", type="primary", disabled=not query)

if ask_clicked:
    with st.spinner("Đang tìm nội dung liên quan..."):
        hits = search(index, query)

    if not hits:
        st.warning("Chưa tìm thấy nội dung liên quan. Hãy tải văn bản PDF lên trước.")
    else:
        context = build_context(hits)
        with st.spinner("Đang soạn câu trả lời..."):
            answer = ask_groq(groq_client, query, context)

        st.markdown("### Trả lời")
        st.markdown(answer)

        with st.expander("📄 Nguồn tham khảo"):
            for hit in hits:
                fields = hit["fields"]
                st.markdown(f"**{fields.get('source', 'không rõ')}** — điểm liên quan: {hit['score']:.3f}")
                st.caption(fields.get("text", "")[:500] + "...")
