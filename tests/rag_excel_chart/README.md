# Tra cứu & Vẽ biểu đồ từ Excel (Streamlit + Pinecone + Groq)

Ứng dụng cho phép: tải file Excel lên → tự động lưu vào Pinecone (không lưu trùng tên file) →
đặt câu hỏi bằng ngôn ngữ tự nhiên → tự nhận diện câu hỏi cần trả lời văn bản hay cần vẽ biểu đồ.

## Cài đặt (chỉ làm 1 lần)

```bash
cd tests/rag_excel_chart
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## API key

Ứng dụng tự động đọc `PINECONE_API_KEY` và `GROQ_API_KEY` từ file `.env` ở thư mục gốc của dự án
(`python_fastapi_crm/.env`) — không cần tạo thêm file `.env` riêng trong thư mục này.

Nếu muốn dùng key khác (hoặc chạy ứng dụng này ở nơi không có file `.env` gốc), có 2 cách:
- Sao chép `.env.example` thành `.env` ngay trong thư mục `tests/rag_excel_chart/` rồi dán key vào
  (file này sẽ ghi đè key ở thư mục gốc).
- Hoặc chạy ứng dụng, dán key trực tiếp vào ô ở thanh bên trái (sidebar).

## Chạy ứng dụng

```bash
streamlit run app.py
```

Trình duyệt sẽ tự mở tại `http://localhost:8501`.

## Cách dùng

1. Ở mục "1) Tải lên file Excel" — chọn file `.xlsx`/`.xls`, bấm "Tải lên và lưu vào Pinecone".
   Nếu file trùng tên với file đã lưu trước đó, ứng dụng sẽ tự bỏ qua để tránh lưu trùng.
2. Mục "2) Các file đã lưu" hiển thị danh sách file hiện có trong Pinecone, có nút "Xóa" nếu muốn
   xóa và tải lại.
3. Mục "3) Đặt câu hỏi" — gõ câu hỏi bất kỳ, ví dụ:
   - "Doanh thu theo tháng năm 2024 như thế nào?" → ứng dụng tự vẽ biểu đồ.
   - "Sản phẩm nào bán chạy nhất?" → ứng dụng tự vẽ biểu đồ xếp hạng.
   - "Khách hàng công ty ABC đã mua những gì?" → ứng dụng trả lời bằng văn bản dựa trên dữ liệu.

## Lưu ý

- Index Pinecone tên "sales" sẽ được tự động tạo trong lần chạy đầu tiên.
- Dữ liệu Excel được lưu thật trong Pinecone (không lưu file gốc trên máy), nên có thể truy cập
  lại ở bất kỳ máy nào dùng cùng Pinecone API key.
- Giới hạn 20.000 dòng/file để tránh treo ứng dụng với file quá lớn.
