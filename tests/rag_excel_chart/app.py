"""
Ung dung Streamlit: Upload file Excel -> luu vao Pinecone -> hoi dap va ve bieu do.

Cach hoat dong (tom tat cho nguoi khong chuyen code):
1) Ban tai len 1 hoac nhieu file Excel. Moi dong du lieu trong file duoc luu thanh
   1 "ban ghi" trong Pinecone (index ten la "sales"). Pinecone tu tao vector embedding
   gium minh (khong can goi them API embedding rieng) nho tinh nang "integrated embedding".
2) Moi file da tai len se duoc ghi lai ten trong mot "so danh sach file" (cung luu trong
   Pinecone) de lan sau neu ban tai lai file trung ten, ung dung se bo qua, khong luu trung.
3) Khi ban go cau hoi, ung dung nho Groq AI (mo hinh Llama chay rat nhanh, mien phi) doc
   cau hoi va tu quyet dinh:
     - Neu ban hoi ve so lieu / thong ke / xu huong -> ung dung lay lai du lieu goc tu
       Pinecone, tinh toan bang pandas va ve bieu do (Plotly).
     - Neu ban hoi thong thuong -> ung dung tim cac dong du lieu lien quan nhat trong
       Pinecone (tim kiem ngu nghia) roi nho Groq AI doc va tra loi bang ngon ngu tu nhien.
"""

import io
import json
import os
import re
import unicodedata
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

# File .env cua du an (chua san PINECONE_API_KEY, GROQ_API_KEY) nam o thu muc goc
# python_fastapi_crm/.env, tuc la len 2 cap tu thu muc chua file nay.
ROOT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ROOT_ENV_PATH)
load_dotenv()  # cho phep .env rieng trong thu muc nay (neu co) ghi de

# ----------------------------------------------------------------------------
# Cau hinh chung
# ----------------------------------------------------------------------------
INDEX_NAME = "sales"
REGISTRY_NAMESPACE = "_files_registry"
EMBED_MODEL = "multilingual-e5-large"  # ho tro tieng Viet lan tieng Anh
UPSERT_BATCH_SIZE = 90
FETCH_BATCH_SIZE = 200
MAX_ROWS_PER_FILE = 20000  # gioi han an toan cho 1 file, tranh treo may

st.set_page_config(page_title="Tra cuu & Bieu do Excel (RAG + Pinecone + Groq)", layout="wide")


# ----------------------------------------------------------------------------
# Lay API key: uu tien .env, neu chua co thi cho nhap truc tiep trong sidebar
# ----------------------------------------------------------------------------
def get_api_keys():
    with st.sidebar:
        st.header("Cau hinh")
        pinecone_key = os.getenv("PINECONE_API_KEY") or st.session_state.get("pinecone_key", "")
        groq_key = os.getenv("GROQ_API_KEY") or st.session_state.get("groq_key", "")

        if not pinecone_key:
            pinecone_key = st.text_input("Pinecone API Key", type="password", key="pinecone_key_input")
            if pinecone_key:
                st.session_state["pinecone_key"] = pinecone_key
        if not groq_key:
            groq_key = st.text_input("Groq API Key", type="password", key="groq_key_input")
            if groq_key:
                st.session_state["groq_key"] = groq_key

        st.caption(
            "Chua co key? Lay Pinecone key mien phi tai app.pinecone.io, "
            "Groq key mien phi tai console.groq.com/keys"
        )
    return pinecone_key, groq_key


PINECONE_API_KEY, GROQ_API_KEY = get_api_keys()
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

if not PINECONE_API_KEY or not GROQ_API_KEY:
    st.info("Vui long nhap Pinecone API Key va Groq API Key o thanh ben trai de bat dau.")
    st.stop()


# ----------------------------------------------------------------------------
# Ket noi Pinecone + tao index "sales" (dung integrated embedding, khong can
# tu goi model embedding rieng)
# ----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_pinecone_index(api_key: str, cloud: str, region: str):
    from pinecone import Pinecone

    pc = Pinecone(api_key=api_key)

    if not pc.has_index(INDEX_NAME):
        pc.create_index_for_model(
            name=INDEX_NAME,
            cloud=cloud,
            region=region,
            embed={
                "model": EMBED_MODEL,
                "field_map": {"text": "chunk_text"},
            },
        )

    return pc.Index(INDEX_NAME)


@st.cache_resource(show_spinner=False)
def get_groq_client(api_key: str):
    from groq import Groq

    return Groq(api_key=api_key)


try:
    index = get_pinecone_index(PINECONE_API_KEY, PINECONE_CLOUD, PINECONE_REGION)
    groq_client = get_groq_client(GROQ_API_KEY)
except Exception as e:
    st.error(f"Khong the ket noi Pinecone hoac Groq. Kiem tra lai API key. Chi tiet: {e}")
    st.stop()


# ----------------------------------------------------------------------------
# Cac ham tien ich
# ----------------------------------------------------------------------------
def slugify(text: str) -> str:
    """Chuyen ten file/sheet ve dang an toan (khong dau, khong khoang trang) de lam id/namespace."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", text).strip("-").lower()
    return text or "file"


def clean_value(v):
    """Chuyen 1 gia tri o Excel ve kieu ma Pinecone metadata chap nhan (str/number/bool)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return str(v)
    if isinstance(v, (bool,)):
        return v
    if isinstance(v, (int, float)):
        return v
    return str(v)


def column_kind(series: pd.Series) -> str:
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    return "text"


def read_excel_sheets(uploaded_file) -> dict:
    """Doc tat ca cac sheet trong 1 file Excel thanh dict {sheet_name: DataFrame}."""
    raw = uploaded_file.read()
    xls = pd.ExcelFile(io.BytesIO(raw))
    sheets = {}
    for sheet_name in xls.sheet_names:
        df = xls.parse(sheet_name)
        df = df.dropna(how="all")  # bo dong trong hoan toan
        if df.empty:
            continue
        df.columns = [str(c).strip() for c in df.columns]
        sheets[sheet_name] = df
    return sheets


def build_records_and_schema(filename: str, sheets: dict):
    """Bien moi dong Excel thanh 1 ban ghi Pinecone. Tra ve (records, schema, total_rows)."""
    file_slug = slugify(filename)
    records = []
    schema = {}
    total_rows = 0
    truncated = False

    for sheet_name, df in sheets.items():
        col_kinds = {c: column_kind(df[c]) for c in df.columns}
        schema[sheet_name] = col_kinds
        sheet_slug = slugify(sheet_name)

        for row_idx, row in df.iterrows():
            if total_rows >= MAX_ROWS_PER_FILE:
                truncated = True
                break
            total_rows += 1

            parts = []
            metadata = {
                "filename": filename,
                "sheet": sheet_name,
                "row_index": int(row_idx),
            }
            for col in df.columns:
                val = clean_value(row[col])
                parts.append(f"{col}: {val}")
                metadata[col] = val
                # them cot phu "<cot>__thang" khi la ngay, giup gom nhom theo thang de ve bieu do
                if col_kinds[col] == "date" and val:
                    try:
                        month_str = pd.to_datetime(val).strftime("%Y-%m")
                        metadata[f"{col}__thang"] = month_str
                    except Exception:
                        pass

            chunk_text = f"Tep {filename}, sheet {sheet_name}, dong {row_idx}: " + "; ".join(parts)
            record = {"_id": f"{file_slug}__{sheet_slug}__row{row_idx}", "chunk_text": chunk_text}
            record.update(metadata)
            records.append(record)
        if truncated:
            break

    return records, schema, total_rows, truncated


def upsert_in_batches(namespace: str, records: list, progress_cb=None):
    for i in range(0, len(records), UPSERT_BATCH_SIZE):
        batch = records[i : i + UPSERT_BATCH_SIZE]
        index.upsert_records(namespace=namespace, records=batch)
        if progress_cb:
            progress_cb(min(i + UPSERT_BATCH_SIZE, len(records)), len(records))


def list_all_ids(namespace: str) -> list:
    """Tra ve toan bo ID (chuoi) trong 1 namespace, doc dung tung trang tra ve boi index.list()."""
    ids = []
    for page in index.list(namespace=namespace):
        page_vectors = getattr(page, "vectors", None)
        items = page_vectors if page_vectors is not None else page
        for item in items or []:
            ids.append(item.id if hasattr(item, "id") else item)
    return ids


def registry_get(filename: str):
    file_slug = slugify(filename)
    res = index.fetch(ids=[file_slug], namespace=REGISTRY_NAMESPACE)
    vectors = getattr(res, "vectors", None) or res.get("vectors", {})
    return vectors.get(file_slug)


def registry_put(filename: str, schema: dict, total_rows: int):
    file_slug = slugify(filename)
    record = {
        "_id": file_slug,
        "chunk_text": f"Danh sach file: {filename}",
        "filename": filename,
        "namespace": file_slug,
        "schema_json": json.dumps(schema, ensure_ascii=False),
        "row_count": total_rows,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    index.upsert_records(namespace=REGISTRY_NAMESPACE, records=[record])


def registry_list() -> list:
    files = []
    try:
        all_ids = list_all_ids(REGISTRY_NAMESPACE)
        for i in range(0, len(all_ids), FETCH_BATCH_SIZE):
            batch_ids = all_ids[i : i + FETCH_BATCH_SIZE]
            res = index.fetch(ids=batch_ids, namespace=REGISTRY_NAMESPACE)
            vectors = getattr(res, "vectors", None) or res.get("vectors", {})
            for v in vectors.values():
                meta = getattr(v, "metadata", None) or v.get("metadata", {})
                files.append(meta)
    except Exception as e:
        st.warning(f"Khong doc duoc danh sach file: {e}")
    return files


def registry_delete(filename: str):
    file_slug = slugify(filename)
    try:
        index.delete(ids=[file_slug], namespace=REGISTRY_NAMESPACE)
    except Exception:
        pass
    try:
        # xoa toan bo du lieu cua file trong namespace rieng cua no
        index.delete(namespace=file_slug, delete_all=True)
    except Exception:
        pass


def fetch_all_rows(namespace: str) -> pd.DataFrame:
    """Lay lai TOAN BO du lieu goc cua 1 file tu Pinecone (dung cho tinh toan/ve bieu do chinh xac)."""
    all_ids = list_all_ids(namespace)

    rows = []
    for i in range(0, len(all_ids), FETCH_BATCH_SIZE):
        batch_ids = all_ids[i : i + FETCH_BATCH_SIZE]
        res = index.fetch(ids=batch_ids, namespace=namespace)
        vectors = getattr(res, "vectors", None) or res.get("vectors", {})
        for v in vectors.values():
            meta = getattr(v, "metadata", None) or v.get("metadata", {})
            row = {k: val for k, val in meta.items() if k != "chunk_text"}
            rows.append(row)

    return pd.DataFrame(rows)


def semantic_search(namespaces: list, query_text: str, top_k_per_file: int = 8):
    hits = []
    for ns in namespaces:
        try:
            res = index.search(
                namespace=ns,
                query={"inputs": {"text": query_text}, "top_k": top_k_per_file},
                fields=["chunk_text", "filename", "sheet", "row_index"],
            )
        except Exception:
            continue
        result_hits = getattr(res, "result", None) or res.get("result", {})
        hit_list = getattr(result_hits, "hits", None) if result_hits is not None else None
        if hit_list is None and isinstance(result_hits, dict):
            hit_list = result_hits.get("hits", [])
        for h in hit_list or []:
            fields = getattr(h, "fields", None) or h.get("fields", {})
            score = getattr(h, "_score", None)
            if score is None:
                score = h.get("_score", 0)
            hits.append({"score": score, **fields})

    hits.sort(key=lambda x: x.get("score", 0), reverse=True)
    return hits


# ----------------------------------------------------------------------------
# Groq: hieu cau hoi + tra loi
# ----------------------------------------------------------------------------
def build_schema_summary(files: list) -> str:
    lines = []
    for f in files:
        filename = f.get("filename", "?")
        try:
            schema = json.loads(f.get("schema_json", "{}"))
        except Exception:
            schema = {}
        lines.append(f"- Tep: {filename} (namespace: {f.get('namespace')})")
        for sheet_name, cols in schema.items():
            col_desc = ", ".join(f"{c} ({k})" for c, k in cols.items())
            lines.append(f"    Sheet '{sheet_name}': {col_desc}")
    return "\n".join(lines) if lines else "(chua co du lieu nao duoc luu)"


def classify_query(user_query: str, files: list) -> dict:
    schema_summary = build_schema_summary(files)
    system_prompt = (
        "Ban la bo phan tich cau hoi cho ung dung tra cuu du lieu ban hang luu trong Excel. "
        "Doc danh sach cac tep/cot du lieu hien co, sau do phan loai cau hoi cua nguoi dung va "
        "tra ve DUY NHAT 1 doi tuong JSON hop le, khong giai thich them, theo dung cau truc:\n"
        "{\n"
        '  "intent": "chart" hoac "qna",\n'
        '  "target_files": ["ten_tep_1", ...]  (de mang rong [] neu ap dung cho tat ca tep),\n'
        '  "group_by": "ten cot de nhom (dung cho chart)" hoac null,\n'
        '  "value_col": "ten cot so lieu de tinh toan (dung cho chart)" hoac null,\n'
        '  "agg": "sum" hoac "mean" hoac "count" hoac "max" hoac "min",\n'
        '  "chart_type": "bar" hoac "line" hoac "pie",\n'
        '  "search_query": "cau hoi rut gon de tim kiem ngu nghia (dung cho qna)"\n'
        "}\n"
        "intent = 'chart' khi nguoi dung hoi ve so lieu, thong ke, so sanh, xu huong, tong/trung binh, "
        "muon xem bieu do/do thi. Nguoc lai dung 'qna'.\n"
        "Chi duoc chon group_by/value_col trong danh sach cot co that duoi day.\n\n"
        f"Du lieu hien co:\n{schema_summary}"
    )

    resp = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {}

    parsed.setdefault("intent", "qna")
    parsed.setdefault("target_files", [])
    parsed.setdefault("group_by", None)
    parsed.setdefault("value_col", None)
    parsed.setdefault("agg", "sum")
    parsed.setdefault("chart_type", "bar")
    parsed.setdefault("search_query", user_query)
    return parsed


def answer_with_context(user_query: str, hits: list) -> str:
    if not hits:
        context = "(khong tim thay du lieu lien quan)"
    else:
        context = "\n".join(
            f"- [{h.get('filename')} / {h.get('sheet')} / dong {h.get('row_index')}] {h.get('chunk_text')}"
            for h in hits
        )

    system_prompt = (
        "Ban la tro ly phan tich du lieu ban hang. Chi duoc dua vao DU LIEU TRICH XUAT ben duoi de tra loi. "
        "Neu khong du thong tin de tra loi, hay noi ro la khong tim thay du lieu phu hop, khong bia dat. "
        "Tra loi ngan gon, ro rang, cung ngon ngu voi cau hoi cua nguoi dung.\n\n"
        f"DU LIEU TRICH XUAT:\n{context}"
    )

    resp = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content


# ----------------------------------------------------------------------------
# Giao dien: Upload file
# ----------------------------------------------------------------------------
st.title("Tra cuu & Ve bieu do tu file Excel (RAG + Pinecone + Groq)")

st.subheader("1) Tai len file Excel")
uploaded_files = st.file_uploader(
    "Chon 1 hoac nhieu file Excel (.xlsx, .xls)", type=["xlsx", "xls"], accept_multiple_files=True
)

if uploaded_files and st.button("Tai len va luu vao Pinecone", type="primary"):
    for uf in uploaded_files:
        existing = registry_get(uf.name)
        if existing is not None:
            st.warning(f"Bo qua '{uf.name}' vi ten file nay da duoc luu truoc do.")
            continue

        with st.status(f"Dang xu ly '{uf.name}'...", expanded=True) as status:
            try:
                sheets = read_excel_sheets(uf)
                if not sheets:
                    status.update(label=f"'{uf.name}' khong co du lieu.", state="error")
                    continue

                records, schema, total_rows, truncated = build_records_and_schema(uf.name, sheets)
                st.write(f"Doc duoc {total_rows} dong du lieu tu {len(sheets)} sheet.")
                if truncated:
                    st.warning(f"File qua lon, chi luu {MAX_ROWS_PER_FILE} dong dau tien.")

                progress = st.progress(0.0)

                def _cb(done, total):
                    progress.progress(done / total)

                namespace = slugify(uf.name)
                upsert_in_batches(namespace, records, progress_cb=_cb)
                registry_put(uf.name, schema, total_rows)

                status.update(label=f"Da luu '{uf.name}' thanh cong.", state="complete")
            except Exception as e:
                status.update(label=f"Loi khi xu ly '{uf.name}': {e}", state="error")
    st.rerun()

st.subheader("2) Cac file da luu trong Pinecone")
files = registry_list()
if not files:
    st.caption("Chua co file nao duoc luu.")
else:
    for f in files:
        cols = st.columns([5, 2, 2, 1])
        cols[0].write(f"**{f.get('filename')}**")
        cols[1].write(f"{f.get('row_count', '?')} dong")
        cols[2].write(f.get("uploaded_at", ""))
        if cols[3].button("Xoa", key=f"del_{f.get('namespace')}"):
            registry_delete(f.get("filename"))
            st.rerun()


# ----------------------------------------------------------------------------
# Giao dien: Hoi dap / Bieu do
# ----------------------------------------------------------------------------
st.subheader("3) Dat cau hoi")
user_query = st.text_input(
    "Vi du: 'Doanh thu theo thang nam 2024 nhu the nao?' hoac 'San pham nao ban chay nhat?'"
)

if st.button("Gui cau hoi") and user_query.strip():
    files = registry_list()
    if not files:
        st.warning("Chua co du lieu nao duoc luu. Hay tai len file Excel truoc.")
    else:
        with st.spinner("Dang phan tich cau hoi..."):
            plan = classify_query(user_query, files)

        target_names = plan.get("target_files") or [f.get("filename") for f in files]
        target_files = [f for f in files if f.get("filename") in target_names] or files

        if plan.get("intent") == "chart":
            st.markdown(f"**Loai yeu cau nhan dien:** Bieu do / thong ke")
            frames = []
            for f in target_files:
                df = fetch_all_rows(f.get("namespace"))
                if not df.empty:
                    df["_nguon_tep"] = f.get("filename")
                    frames.append(df)

            if not frames:
                st.warning("Khong lay duoc du lieu tuong ung.")
            else:
                df = pd.concat(frames, ignore_index=True, sort=False)

                group_by = plan.get("group_by")
                value_col = plan.get("value_col")
                agg = (plan.get("agg") or "sum").lower()
                chart_type = (plan.get("chart_type") or "bar").lower()

                if not group_by or group_by not in df.columns:
                    group_by = "_nguon_tep"
                    for c in df.columns:
                        if df[c].dtype == object and df[c].nunique() < len(df):
                            group_by = c
                            break

                for col in df.columns:
                    if col != group_by:
                        df[col] = pd.to_numeric(df[col], errors="ignore")

                if value_col and value_col in df.columns and agg != "count":
                    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
                    grouped = df.groupby(group_by)[value_col].agg(agg).reset_index()
                else:
                    value_col = "so_luong"
                    grouped = df.groupby(group_by).size().reset_index(name=value_col)

                grouped = grouped.sort_values(value_col, ascending=False)

                if chart_type == "line":
                    fig = px.line(grouped, x=group_by, y=value_col, markers=True)
                elif chart_type == "pie":
                    fig = px.pie(grouped, names=group_by, values=value_col)
                else:
                    fig = px.bar(grouped, x=group_by, y=value_col)

                st.plotly_chart(fig, use_container_width=True)
                with st.expander("Xem bang du lieu"):
                    st.dataframe(grouped, use_container_width=True)

                with st.spinner("Dang tom tat..."):
                    top_rows = grouped.head(5).to_string(index=False)
                    summary_prompt = (
                        f"Cau hoi: {user_query}\nKet qua tinh toan (top 5):\n{top_rows}\n"
                        "Hay viet 2-3 cau nhan xet ngan gon bang tieng Viet ve ket qua nay."
                    )
                    resp = groq_client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=[{"role": "user", "content": summary_prompt}],
                        temperature=0.3,
                    )
                    st.write(resp.choices[0].message.content)
        else:
            st.markdown("**Loai yeu cau nhan dien:** Hoi dap thong thuong")
            namespaces = [f.get("namespace") for f in target_files]
            with st.spinner("Dang tim du lieu lien quan..."):
                hits = semantic_search(namespaces, plan.get("search_query") or user_query)
            with st.spinner("Dang tra loi..."):
                answer = answer_with_context(user_query, hits)
            st.write(answer)
            if hits:
                with st.expander("Du lieu tham khao"):
                    for h in hits:
                        st.caption(f"[{h.get('filename')} / {h.get('sheet')} / dong {h.get('row_index')}]")
                        st.write(h.get("chunk_text"))
