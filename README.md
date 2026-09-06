# OCR2Txt v1.3 - Vibed by TwentySeV

Công cụ GUI để chọn (nhiều) vùng bất kỳ trên trang PDF và OCR ra text — nhẹ,
chỉ OCR đúng vùng cần thiết (không OCR cả trang), chạy nền không đơ UI.

## 0. Tính năng hiện có (v3)

- Xem PDF: zoom in/out (nút hoặc **nhập trực tiếp % zoom**), xoay trang,
  chuyển trang (nút hoặc **nhập số trang để nhảy tới**).
- Vẽ vùng chọn OCR bằng chuột (click + kéo), kéo để di chuyển vị trí.
- **Multi-region — XUYÊN TRANG (cross-page)**: vẽ nhiều vùng chọn, kể cả ở
  NHIỀU TRANG khác nhau, và giữ được đồng thời (không bị mất khi chuyển
  trang) — nhấn **Space** trước khi kéo để THÊM vùng mới vào trang đang xem
  (không xóa vùng cũ của trang đó, và không đụng tới vùng ở trang khác). Mỗi
  vùng có nhãn `#<số thứ tự>#<số trang>` (vd `#1#12` = vùng số 1, trang 12)
  để đối chiếu với kết quả OCR — số thứ tự được **đánh số lại liên tục 1..N**
  mỗi khi thêm/thay thế/xóa vùng, luôn đúng bằng tổng số vùng đang có, không
  bị nhảy số dù vẽ đi vẽ lại nhiều lần.
- **Hotkey**: `Enter` = Extract (OCR toàn bộ vùng đã đánh dấu, mọi trang),
  `Delete` = xóa toàn bộ vùng chọn hiện có (ở MỌI trang).
- **Extract tất cả trang**: dùng vùng chọn ở **trang đang xem** làm mẫu, OCR
  lặp lại đúng vị trí đó trên MỌI trang trong file (hóa đơn, biểu mẫu cùng
  layout...) — vùng đã đánh dấu ở trang khác không liên quan tới nút này.
  Kết quả mỗi trang có thể chứa nhiều vùng (nối bằng `---`), các trang nối
  với nhau bằng `--- Trang X ---`.
- **Nút Hủy**: dừng ngay quá trình Extract tất cả trang giữa chừng (mất toàn
  bộ kết quả đang xử lý dở, không giữ lại phần đã xong).
- **Engine OCR** (chọn qua dropdown "Engine"): **Tesseract** (mặc định khi mở
  app — nhẹ, khởi động nhanh) hoặc **PaddleOCR** (chính xác cao hơn, đặc biệt
  với dấu câu nhỏ, nhưng khởi tạo chậm hơn nhiều) — chọn ngôn ngữ Việt /
  English / Việt+Anh. Chỉ giữ đúng 1 engine trong bộ nhớ tại một thời điểm;
  đổi engine sẽ khởi tạo lại (có thể mất vài giây tới cả phút với PaddleOCR
  lần đầu).
- **Độ tin cậy (confidence score)**: cả 2 engine đều lấy sẵn confidence từ
  chính engine (Tesseract: trung bình `conf` theo từ; PaddleOCR: trung bình
  `rec_scores` theo dòng) và hiển thị ở thanh trạng thái sau khi Extract
  xong, ví dụ `Hoàn tất. Độ tin cậy: 82%`. Nếu có nhiều vùng/nhiều trang,
  hiển thị riêng từng vùng/trang, ví dụ
  `Hoàn tất. Độ tin cậy: Vùng 1: 82%, Vùng 2: 76%`.
- **Table detection** (chọn qua dropdown "Table"): nhận diện vùng chọn là
  bảng và OCR ra thẳng bảng markdown (`| Cột 1 | Cột 2 |` ...) thay vì text
  thường. 2 chế độ:
  - **Heuristic**: dựng bảng từ vị trí (bounding box) của từng từ/dòng nhận
    dạng được — nhẹ, nhanh, dùng được với cả 2 engine. Chính xác với bảng có
    hàng/cột thẳng hàng; có thể sai lệch với bảng merge ô hoặc layout phức
    tạp.
  - **PP-Structure (nâng cao)**: dùng model chuyên nhận diện cấu trúc bảng
    của PaddleOCR — chính xác hơn nhiều kể cả bảng phức tạp, nhưng **chỉ
    dùng được khi Engine = PaddleOCR**, tải thêm model riêng ở lần dùng đầu
    tiên (cần mạng), và xử lý chậm hơn đáng kể so với Heuristic.
- Hậu xử lý tự động: dấu `.` đứng riêng ở **đầu dòng** (bullet bị scan lỗi từ
  dấu gạch đầu dòng `-`) được tự động sửa lại thành `-` (chỉ áp dụng cho OCR
  text thường, không áp dụng cho kết quả Table detection).
- Output Panel: sửa trực tiếp, Copy toàn bộ, Clear, Export ra `.txt`/`.docx`.
- Kéo & thả file PDF trực tiếp vào cửa sổ.

## 1. Cài đặt

### 1.1. Cài Python packages

```bash
pip install -r requirements.txt
```

Mặc định `requirements.txt` cài cả **Tesseract** (engine mặc định lúc mở
app, qua `pytesseract`) lẫn **PaddleOCR** (engine tùy chọn, đổi qua dropdown
"Engine" trong app) — để dùng được cả 2 mà không cần sửa code. PaddleOCR lần
chạy đầu tiên sẽ tự tải model về máy (cần mạng).

### 1.2. Cài Tesseract OCR (chương trình ngoài, không phải package Python)

`pytesseract` chỉ là lớp gọi tới chương trình Tesseract OCR cài sẵn trên máy
— cần cài riêng:

- **Windows:** [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki),
  nhớ tick gói ngôn ngữ **Vietnamese**, sau đó thêm vào biến môi trường `PATH`.
- **macOS:** `brew install tesseract tesseract-lang`
- **Linux (Debian/Ubuntu):** `sudo apt install tesseract-ocr tesseract-ocr-vie`

Nếu chỉ muốn dùng PaddleOCR và không cần Tesseract: có thể bỏ dòng
`pytesseract` trong `requirements.txt` — khi đó dropdown "Engine" vẫn hiện
lựa chọn Tesseract nhưng sẽ báo lỗi rõ ràng nếu chọn (thiếu package/binary).

## 2. Chạy ứng dụng

```bash
python main.py
```

## 3. Cách dùng

1. Bấm **Mở PDF...** hoặc kéo-thả file .pdf vào cửa sổ.
2. Duyệt trang (nút ◀▶ hoặc gõ số trang vào ô "Đi tới trang" rồi Enter) /
   zoom (nút Zoom +/- hoặc gõ % rồi Enter) / xoay trang.
3. **Click + kéo chuột** trên trang để tạo vùng chọn OCR. Kéo vùng chọn để
   di chuyển; vẽ lại (không giữ Space) nếu muốn thay vùng khác.
4. Chọn **Ngôn ngữ** (Việt / English / Việt+Anh), **Engine** (Tesseract /
   PaddleOCR) và **Table** (Tắt / Heuristic / PP-Structure) nếu cần, bấm
   **Extract** (hoặc nhấn phím **Enter**).
5. Kết quả hiện ở khung OUTPUT bên phải — có thể sửa trực tiếp, **Copy**,
   **Clear**, hoặc **Export...** ra file `.txt`/`.docx`. Độ tin cậy của lần
   Extract gần nhất hiện ở thanh trạng thái phía dưới.

### Multi-region — kể cả xuyên nhiều trang (cross-page)

1. Vẽ vùng chọn thứ nhất như bình thường (trên trang bất kỳ).
2. Nhấn phím **Space** — lần kéo chuột tiếp theo sẽ **thêm** vùng chọn mới
   vào trang đang xem, không xóa vùng cũ của trang đó.
3. (Tùy chọn) Chuyển sang trang khác — vùng chọn ở trang cũ **vẫn được giữ
   nguyên**, không bị mất. Nhấn Space rồi vẽ tiếp ở trang mới nếu muốn thêm
   vùng ở đó.
4. Bấm **Extract** (hoặc Enter) — OCR **TẤT CẢ** vùng đã đánh dấu, ở **MỌI
   trang**, mỗi vùng OCR đúng trên trang riêng của nó. Kết quả các vùng nối
   nhau bằng `---` (muốn biết đoạn nào từ vùng/trang nào, đối chiếu với nhãn
   `#<id>#<trang>` trên canvas lúc đang chọn vùng).
5. Nhấn **Delete** bất cứ lúc nào để xóa **toàn bộ** vùng chọn (ở mọi trang)
   và vẽ lại từ đầu.

⚠️ **Xoay trang** (nút "⟳ Xoay") sẽ xóa TOÀN BỘ vùng chọn đang có (ở mọi
trang) — vì góc xoay đổi thì vị trí đã đánh dấu không còn đúng nữa. App sẽ
hỏi xác nhận trước nếu đang có vùng chọn.

### OCR hàng loạt qua nhiều trang ("Extract tất cả trang")

Nếu tài liệu có nhiều trang cùng layout (hóa đơn, biểu mẫu...):

1. Đứng ở **trang đang xem**, vẽ vùng chọn (1 hoặc nhiều vùng) ở (các) vị trí
   mong muốn — vùng ở CÁC TRANG KHÁC (nếu có, do đang dùng multi-region xuyên
   trang) sẽ **không** được dùng làm mẫu, chỉ vùng ở trang đang xem mới tính.
2. Bấm **Extract tất cả trang** — OCR đúng (các) vị trí đó trên MỌI trang của
   file. Trong mỗi trang, kết quả các vùng nối bằng `---`; giữa các trang nối
   bằng `--- Trang X ---`.
3. Muốn dừng giữa chừng: bấm **Hủy** — toàn bộ kết quả của lượt chạy đó sẽ
   không được giữ lại (kể cả các trang đã OCR xong trước khi hủy).

## 4. Kiến trúc dự án

```
pdf_ocr_tool/
├── main.py                    # entry point
├── requirements.txt
└── app/
    ├── pdf_viewer.py           # QGraphicsView: render/zoom/xoay/cache + multi-region XUYÊN TRANG + hotkey
    ├── models.py                # RegionRef (id, page, rect) — kiểu dữ liệu dùng chung viewer <-> worker
    ├── ocr_engine.py            # TesseractEngine (mặc định) / PaddleOCREngine (tùy chọn) + confidence + table
    ├── table_detect.py          # Table detection: heuristic (box clustering) + HTML->markdown (PP-Structure)
    ├── preprocessing.py         # OpenCV: denoise, threshold/CLAHE tùy engine, deskew
    ├── text_postprocess.py       # Hậu xử lý text: fix dấu "." đầu dòng -> "-"
    ├── ocr_worker.py              # QThread: MultiRegionOCRWorker (cross-page) + BatchOCRWorker (1 trang -> nhiều trang, hỗ trợ hủy)
    ├── output_panel.py            # Output: copy / edit / clear / export
    └── main_window.py              # Lắp ráp UI, điều phối luồng, hotkey routing
```

### Nguyên lý double-DPI (quan trọng)

- Trang PDF được render ở **DPI thấp (~120)** để pan/zoom mượt trong lúc xem,
  và được **cache** theo `(số trang, góc xoay)` để không render lại mỗi lần.
- Khi bấm **Extract**, mỗi vùng chọn được quy đổi sang tọa độ gốc của trang
  (points, độc lập với DPI/zoom hiển thị), rồi PyMuPDF **render lại đúng
  vùng đó ở DPI cao (300)** bằng tham số `clip`. Nhờ vậy OCR chính xác hơn
  nhiều so với việc crop trực tiếp ảnh đang hiển thị, mà vẫn không phải
  render cả trang ở DPI cao (tốn thời gian/bộ nhớ).

### Preprocessing thích ứng theo engine

- **PaddleOCR** (deep-learning): chỉ khử nhiễu + tăng tương phản nhẹ (CLAHE),
  KHÔNG ép nhị phân cứng — giữ chi tiết ký tự/dấu câu nhỏ tốt hơn.
- **Tesseract** (truyền thống): nhị phân hóa (adaptive threshold) trước khi
  nhận diện, đúng như cách Tesseract hoạt động tốt nhất.

### Confidence score

- `BaseOCREngine.recognize()` trả về `(text, confidence)` thay vì chỉ text —
  `confidence` là số 0-100 hoặc `None` nếu không xác định được (ví dụ không
  nhận dạng được gì).
- Tesseract: gọi thêm `pytesseract.image_to_data()` (cùng ảnh, cùng config
  với `image_to_string()`) chỉ để lấy `conf` trung bình theo từ — không dùng
  kết quả text của lệnh này, để không đổi hành vi text hiện tại.
- PaddleOCR: lấy trung bình `rec_scores` (API mới) hoặc score trong từng dòng
  kết quả `.ocr()` (API cũ), nhân 100.
- Với multi-region/nhiều trang: hiển thị riêng từng vùng/trang trên thanh
  trạng thái (không gộp thành 1 số trung bình duy nhất).

### Table detection

- **Heuristic** (`table_detect.words_to_markdown_table`): dùng
  `BaseOCREngine.recognize_words()` (box + text + confidence theo từng
  từ/dòng — Tesseract qua `image_to_data`, PaddleOCR qua box/poly của từng
  dòng kết quả), gom cụm 1 chiều theo tâm y (hàng) rồi tâm x (cột, dùng tâm x
  của TẤT CẢ từ trong vùng để xác định biên cột chung), dựng thành bảng
  markdown. Ngưỡng gom cụm tính thích ứng theo median khoảng cách/kích thước
  chữ, không dùng số cố định.
- **PP-Structure** (`PaddleOCREngine.recognize_table`): gọi module cấu trúc
  bảng riêng của PaddleOCR (`PPStructureV3` bản ≥3.0, fallback `PPStructure`
  bản cũ hơn — tự dò như cách `PaddleOCREngine` đã dò 2 dòng API `.predict()`
  / `.ocr()`), model được init **lazy** (chỉ tạo khi thực sự dùng Table mode
  này lần đầu, không tốn thêm thời gian khởi động app). Kết quả HTML được
  convert sang markdown qua `table_detect.html_table_to_markdown` (convert
  đơn giản, không tái tạo đầy đủ rowspan/colspan).
- Vì API của PP-Structure thay đổi khá nhiều giữa các bản `paddleocr`, phần
  này được code theo hướng best-effort (thử vài entrypoint/cấu trúc kết quả
  đã biết) — nếu máy bạn cài bản `paddleocr` không có `PPStructureV3` lẫn
  `PPStructure`, chế độ này sẽ báo lỗi rõ ràng thay vì âm thầm trả về sai;
  dùng Heuristic trong trường hợp đó.

### Threading & hủy tác vụ

Toàn bộ việc render DPI cao + preprocess + OCR chạy trong `QThread`
(`ocr_worker.py`), giao tiếp với UI qua signal (`progress`, `finished_ok`,
`failed`) — UI không bị đơ, thanh trạng thái dưới cùng hiển thị tiến trình.
`BatchOCRWorker` hỗ trợ hủy qua cờ hiệu (`request_cancel()`, kiểm tra ở đầu
mỗi vòng lặp trang) thay vì `terminate()` — an toàn hơn vì không ngắt đột
ngột khi đang gọi C-extension (PyMuPDF/OpenCV/PaddleOCR/pytesseract).

## 5. Đóng gói thành .exe (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --name "OCR2Txt" --onedir --windowed main.py
```

Lưu ý:
- Dùng `--onedir` (không dùng `--onefile`) để khởi động nhanh hơn — onefile
  phải giải nén ra thư mục tạm mỗi lần mở app.
- Nếu build kèm PaddleOCR (kể cả khi engine mặc định là Tesseract, chỉ cần
  còn cài package `paddleocr`/`paddlepaddle` để dropdown "Engine"/"Table"
  PP-Structure hoạt động), file build sẽ khá nặng (có thể >500MB–1GB) do
  model + dependency (paddlepaddle). Cân nhắc bỏ hẳn PaddleOCR khỏi
  `requirements.txt` trước khi build nếu cần bản phân phối gọn nhẹ, chỉ dùng
  Tesseract (khi đó dropdown "Engine" chỉ nên để Tesseract, và "Table" không
  dùng được PP-Structure).
- Nếu dùng Tesseract, người dùng cuối vẫn cần cài Tesseract riêng trên máy
  (không bundle theo .exe được vì đó là binary ngoài).

## 6. Giới hạn hiện tại / hướng mở rộng

- Vùng chọn hiện chỉ hỗ trợ *di chuyển*, chưa có *kéo resize bằng handle ở
  góc/cạnh* — muốn đổi kích thước thì xóa (Delete) và vẽ lại.
- "Extract tất cả trang" áp dụng ĐÚNG tọa độ (page-space) của vùng chọn ở
  trang mẫu lên mọi trang — nếu PDF có các trang kích thước khác nhau, vị trí
  OCR có thể bị lệch trên những trang có kích thước khác trang mẫu.
- Multi-region xuyên trang: **xoay trang sẽ xóa toàn bộ vùng chọn** đang có ở
  MỌI trang (không chỉ trang đang xem) — vì góc xoay là thuộc tính chung của
  cả tài liệu, không phải riêng từng trang.
- Table detection (Heuristic) chỉ chính xác với bảng có hàng/cột thẳng hàng
  tương đối rõ ràng; bảng có ô merge hoặc layout phức tạp nên dùng chế độ
  PP-Structure (yêu cầu engine PaddleOCR).
- Nút Hủy (của "Extract tất cả trang") không giữ lại kết quả các trang đã
  OCR xong trước khi hủy (theo lựa chọn tối ưu code, chấp nhận đánh đổi để
  tránh phức tạp hóa worker). Nút Extract thường (cross-page) hiện chưa hỗ
  trợ hủy giữa chừng.
