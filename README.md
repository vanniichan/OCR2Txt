# OCR2Txt

**Công cụ GUI để chọn (nhiều) vùng bất kỳ trên trang PDF và OCR ra text** — nhẹ, chỉ OCR đúng vùng cần thiết (không OCR cả trang), hỗ trợ multi-region xuyên nhiều trang, nhận diện bảng, và chạy nền không đơ UI.

`v1.3` · License: MIT · Vibe by **TwentySeV**

<img width="1492" height="977" alt="image" src="https://github.com/user-attachments/assets/a139820d-f090-49db-b058-3e0b29859801" />

---

## Mục lục

- [OCR2Txt](#ocr2txt)
  - [Mục lục](#mục-lục)
  - [Tính năng](#tính-năng)
  - [Công nghệ sử dụng](#công-nghệ-sử-dụng)
  - [Cài đặt](#cài-đặt)
    - [Cài Tesseract OCR (chương trình ngoài, không phải package Python)](#cài-tesseract-ocr-chương-trình-ngoài-không-phải-package-python)
  - [Chạy ứng dụng](#chạy-ứng-dụng)
  - [Cách dùng](#cách-dùng)
    - [Multi-region — kể cả xuyên nhiều trang](#multi-region--kể-cả-xuyên-nhiều-trang)
    - [OCR hàng loạt qua nhiều trang ("Extract tất cả trang")](#ocr-hàng-loạt-qua-nhiều-trang-extract-tất-cả-trang)
  - [Đóng gói thành .exe (PyInstaller)](#đóng-gói-thành-exe-pyinstaller)
  - [Đóng góp](#đóng-góp)
  - [License](#license)

---

## Tính năng

- **Xem PDF**: zoom in/out (nút hoặc nhập trực tiếp % zoom), xoay trang, chuyển trang (nút hoặc nhập số trang để nhảy tới).
- **Vẽ vùng chọn OCR** bằng chuột (click + kéo), kéo để di chuyển vị trí.
- **Multi-region — xuyên trang (cross-page)**: vẽ nhiều vùng chọn, kể cả ở nhiều trang khác nhau, giữ đồng thời (không mất khi chuyển trang). Nhấn `Space` trước khi kéo để thêm vùng mới vào trang đang xem mà không xóa vùng cũ. Mỗi vùng có nhãn `#<số thứ tự>#<số trang>` (vd `#1#12`) để đối chiếu với kết quả OCR, tự đánh số lại liên tục 1..N.
- **Hotkey**: `Enter` = Extract (OCR toàn bộ vùng đã đánh dấu, mọi trang), `Delete` = xóa toàn bộ vùng chọn hiện có.
- **Extract tất cả trang**: dùng vùng chọn ở trang đang xem làm mẫu, OCR lặp lại đúng vị trí đó trên mọi trang (hóa đơn, biểu mẫu cùng layout...). Có nút **Hủy** để dừng giữa chừng.
- **Chạy song song (thử nghiệm)**: tùy chọn OCR nhiều vùng/trang cùng lúc bằng nhiều luồng CPU khi dùng engine Tesseract — tăng tốc đáng kể khi Extract hàng loạt, kết quả giống hệt chế độ tuần tự (chỉ khác tốc độ). Mặc định tắt.
- **2 Engine OCR** (đổi qua dropdown, khởi tạo trong nền — không đơ UI khi đổi):
  - **Tesseract** (mặc định — nhẹ, khởi động nhanh).
  - **PaddleOCR** (chính xác cao hơn, đặc biệt với dấu câu/ký tự nhỏ, nhưng khởi tạo chậm hơn nhiều, đặc biệt lần đầu).
- **Độ tin cậy (confidence score)**: hiển thị ở thanh trạng thái sau khi Extract; đồng thời **tô màu cảnh báo ngay trên canvas** (vàng = trung bình, đỏ = thấp) cho từng vùng chọn để dễ dàng phát hiện chỗ cần kiểm tra lại thủ công khi xử lý số lượng lớn.
- **Table detection** (dropdown "Table"): OCR vùng chọn ra thẳng bảng markdown.
  - **Heuristic**: dựng bảng từ vị trí từ/dòng — nhẹ, dùng được với cả 2 engine.
  - **PP-Structure (nâng cao)**: model chuyên bảng của PaddleOCR — chính xác hơn nhiều với bảng phức tạp, chỉ dùng được khi Engine = PaddleOCR.
- **Tự động khử nhiễu thông minh**: tự đo mức nhiễu của từng vùng ảnh, chỉ chạy bước khử nhiễu (tốn thời gian) khi thực sự cần — nhanh hơn đáng kể với PDF gốc kỹ thuật số mà không ảnh hưởng chất lượng với bản scan.
- **Hậu xử lý tự động**: dấu `.` đứng riêng ở đầu dòng (bullet bị scan lỗi từ `-`) được tự động sửa lại thành `-`.
- **Output Panel**: sửa trực tiếp, Copy toàn bộ, Clear, Export ra `.txt`/`.docx`.
- Kéo & thả file PDF trực tiếp vào cửa sổ.

## Công nghệ sử dụng

| Thành phần | Vai trò |
|---|---|
| [PySide6](https://doc.qt.io/qtforpython/) | Giao diện GUI (Qt for Python) |
| [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/) | Đọc/render PDF |
| [OpenCV](https://opencv.org/) | Tiền xử lý ảnh (khử nhiễu, nhị phân hóa, deskew) |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) / [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Engine OCR |
| [python-docx](https://python-docx.readthedocs.io/) | Export kết quả ra `.docx` |

## Cài đặt

```bash
git clone https://github.com/vanniichan/OCR2Txt.git
cd OCR2Txt
pip install -r requirements.txt
```

Mặc định `requirements.txt` cài cả **Tesseract** (qua `pytesseract`) lẫn **PaddleOCR** để dùng được cả 2 engine mà không cần sửa code. PaddleOCR lần chạy đầu tiên sẽ tự tải model về máy (cần mạng).

### Cài Tesseract OCR (chương trình ngoài, không phải package Python)

`pytesseract` chỉ là lớp gọi tới chương trình Tesseract cài sẵn trên máy — cần cài riêng:

- **Windows**: [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki) — nhớ tick gói ngôn ngữ **Vietnamese**, sau đó thêm vào biến môi trường `PATH`.
- **macOS**: `brew install tesseract tesseract-lang`
- **Linux (Debian/Ubuntu)**: `sudo apt install tesseract-ocr tesseract-ocr-vie`

Nếu chỉ muốn dùng PaddleOCR: có thể bỏ dòng `pytesseract` trong `requirements.txt` — dropdown "Engine" vẫn hiện Tesseract nhưng sẽ báo lỗi rõ ràng nếu chọn.

## Chạy ứng dụng

```bash
python main.py
```

## Cách dùng

1. Bấm **Open PDF...** hoặc kéo-thả file `.pdf` vào cửa sổ.
2. Duyệt trang / zoom / xoay trang bằng thanh công cụ.
3. **Click + kéo chuột** trên trang để tạo vùng chọn OCR. Kéo vùng chọn để di chuyển; xóa (`Delete`) và vẽ lại nếu muốn đổi kích thước.
4. Chọn **Ngôn ngữ**, **Engine**, **Table** (nếu cần), bấm **Extract** (hoặc phím `Enter`).
5. Kết quả hiện ở khung OUTPUT bên phải — sửa trực tiếp, Copy, Clear, hoặc Export ra `.txt`/`.docx`.

### Multi-region — kể cả xuyên nhiều trang

1. Vẽ vùng chọn thứ nhất (trang bất kỳ).
2. Nhấn `Space` — lần kéo chuột tiếp theo sẽ thêm vùng mới vào trang đang xem, không xóa vùng cũ.
3. (Tùy chọn) Chuyển trang khác — vùng chọn cũ vẫn được giữ nguyên. Lặp lại bước 2 nếu muốn thêm vùng ở trang mới.
4. Bấm **Extract** — OCR tất cả vùng đã đánh dấu, ở mọi trang, kết quả nối bằng `---`.
5. Nhấn `Delete` bất cứ lúc nào để xóa toàn bộ vùng chọn và vẽ lại từ đầu.

> ⚠️ **Xoay trang** sẽ xóa toàn bộ vùng chọn đang có (vì góc xoay đổi thì vị trí đã đánh dấu không còn đúng) — app sẽ hỏi xác nhận trước.

### OCR hàng loạt qua nhiều trang ("Extract tất cả trang")

1. Ở trang đang xem, vẽ vùng chọn (1 hoặc nhiều vùng) ở vị trí mong muốn.
2. Bấm **Extract tất cả trang** — OCR đúng vị trí đó trên mọi trang của file.
3. Muốn dừng giữa chừng: bấm **Hủy** (kết quả của lượt chạy đó sẽ không được giữ lại).

## Đóng gói thành .exe (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --name "OCR2Txt" --onedir --windowed main.py
```

- Dùng `--onedir` (không dùng `--onefile`) để khởi động nhanh hơn.
- Nếu build kèm PaddleOCR, file build sẽ khá nặng (có thể >500MB–1GB). Cân nhắc bỏ PaddleOCR khỏi `requirements.txt` trước khi build nếu cần bản gọn nhẹ, chỉ dùng Tesseract.
- Nếu dùng Tesseract, người dùng cuối vẫn cần cài Tesseract riêng trên máy (không bundle được vào `.exe` vì là chương trình ngoài).

## Đóng góp

Đây là project cá nhân, phát triển chủ yếu phục vụ nhu cầu sử dụng của tác giả, nhưng luôn hoan nghênh phản hồi và đóng góp. Có ý tưởng cải thiện, hoặc muốn đề xuất tính năng mới — mở [Issues](https://github.com/vanniichan/OCR2Txt/issues) trên repo này.

## License

Phát hành theo giấy phép [MIT](LICENSE) — tự do sử dụng, sửa đổi, phân phối lại, miễn giữ nguyên thông báo bản quyền.
