# 🦜 Hướng dẫn Fine-tune VieNeu-TTS (LoRA)

Thư mục này chứa toàn bộ công cụ cần thiết để bạn huấn luyện (fine-tune) mô hình VieNeu-TTS với giọng nói của riêng mình bằng phương pháp **LoRA (Low-Rank Adaptation)**.

## ⚙️ Cài đặt (Setup)

Nếu bạn chưa có sẵn mã nguồn, hãy thực hiện cài đặt môi trường:

```bash
git clone https://github.com/pnnbao97/VieNeu-TTS.git
cd VieNeu-TTS
uv sync
```

## 📋 Quy trình huấn luyện (Workflow)

Để đạt được kết quả tốt nhất, bạn cần đi qua các bước sau:

### 1. Chuẩn bị dữ liệu (`dataset/`)
Bạn cần chuẩn bị:
- Thư mục `finetune/dataset/raw_audio/`: Chứa các file âm thanh (.wav) của người nói. Độ dài mỗi file nên trong khoảng từ 3-15 giây để chất lượng finetune đạt tối đa. Theo kinh nghiệm của chúng tôi, tổng thời lượng nên trong khoảng từ 2-4 giờ để model có thể học hết các đặc điểm của giọng mẫu.
- File `finetune/dataset/metadata.csv`: Chứa thông tin văn bản tương ứng với audio. Định dạng: `file_name|text` (ví dụ: `audio_001.wav|Xin chào Việt Nam.`).

*Mẹo: Nếu chưa có dữ liệu, bạn có thể chạy `uv run python finetune/data_scripts/get_hf_sample.py` để tải dữ liệu mẫu.*

### 2. Tiền xử lý và Làm sạch dữ liệu
Chạy các script sau theo thứ tự:

1.  **Lọc dữ liệu (`filter_data.py`)**: Loại bỏ các đoạn âm thanh quá ngắn, quá dài hoặc văn bản chứa ký tự không hợp lệ.
    ```bash
    uv run python finetune/data_scripts/filter_data.py
    ```
    *Kết quả: Tạo ra file `metadata_cleaned.csv`.*

2.  **Mã hóa âm thanh (`encode_data.py`)**: Chuyển đổi audio sang dạng mã hóa của NeuCodec để mô hình LLM có thể học được.
    ```bash
    uv run python finetune/data_scripts/encode_data.py
    ```
    *Kết quả: Tạo ra file `metadata_encoded.csv`.*

### 3. Cấu hình huấn luyện (`configs/lora_config.py`)
Mở file `finetune/configs/lora_config.py` để điều chỉnh các thông số:
- `model`: Chọn base model (vd: `pnnbao-ump/VieNeu-TTS-0.3B`).
- `max_steps`: Số bước huấn luyện (mặc định 5000 là đủ cho giọng đơn lẻ).
- `learning_rate`: Tốc độ học (mặc định là `2e-4`).

### 4. Bắt đầu Huấn luyện (`train.py`)
Chạy script huấn luyện chính:
```bash
uv run python finetune/train.py
```
Mô hình sẽ được lưu định kỳ vào thư mục `finetune/output/`.

---

## 📓 Sử dụng Notebook (Khuyên dùng)
Nếu bạn không quen sử dụng script console, chúng tôi cung cấp file Notebook `finetune_VieNeu-TTS.ipynb`. File này đã tích hợp sẵn mọi bước từ chuẩn bị đến huấn luyện, cực kỳ dễ theo dõi trên Google Colab hoặc máy cục bộ.

---

## 🚀 Sử dụng LoRA sau khi huấn luyện

Sau khi huấn luyện xong, bạn sẽ có các file adapter (vd: `adapter_model.bin`). Bạn có thể:

1.  **Sử dụng trực tiếp trong Gradio**: 
    - Upload thư mục kết quả trong `output/` lên HuggingFace.
    - Nhập Repo ID vào tab **LoRA Adapter** trong ứng dụng Gradio.
2.  **Sử dụng trong Code**:
    ```python
    tts.load_lora_adapter("path/to/your/lora_folder")
    ```

---

## 📦 Tạo `voices.json` cho Model của bạn (Khuyên dùng!)

Khi upload model fine-tuned lên HuggingFace, bạn **nên kèm theo file `voices.json`** để người dùng có thể sử dụng model của bạn mà **không cần cung cấp reference audio**.

### Tại sao cần `voices.json`?

- ✅ Người dùng chỉ cần: `tts = Vieneu(backbone_repo="your-username/your-model")`
- ✅ Không cần upload/chỉ định file audio mẫu nữa
- ✅ Model "portable" - mang theo giọng của nó
- ✅ Trải nghiệm tốt hơn cho người dùng cuối

### Cách tạo `voices.json`:

#### Bước 1: Chuẩn bị audio mẫu

Chọn 1 file audio đại diện cho giọng nói đã fine-tune (3-10 giây, chất lượng tốt):

```bash
# Ví dụ: Chọn file từ dataset
cp finetune/dataset/raw_audio/best_sample.wav reference.wav
```

#### Bước 2: Chạy script tạo `voices.json`

```bash
uv run python finetune/create_voices_json.py \
  --audio reference.wav \
  --text "Đây là văn bản chính xác của audio mẫu." \
  --name my_voice \
  --description "Giọng nữ miền Nam, trẻ trung"
```

**Lưu ý:** `--text` phải **khớp chính xác 100%** với nội dung audio (kể cả dấu câu).

File `voices.json` sẽ được tạo ra với cấu trúc:
```json
{
  "default_voice": "my_voice",
  "presets": {
    "my_voice": {
      "codes": [234, 123, 456, ...],
      "text": "Đây là văn bản chính xác của audio mẫu.",
      "description": "Giọng nữ miền Nam, trẻ trung"
    }
  }
}
```

#### Bước 3: Upload lên HuggingFace

**Option A: Upload LoRA trực tiếp**

```bash
# Copy voices.json vào thư mục output LoRA
cp voices.json finetune/output/your_run_name/

# Upload toàn bộ lên HF
huggingface-cli upload your-username/your-lora-model finetune/output/your_run_name
```

**Option B: Upload Merged Model (khuyên dùng cho production)**

1. **Merge LoRA vào base model:**
   ```bash
   uv run python finetune/merge_lora.py \
     --base_model pnnbao-ump/VieNeu-TTS-0.3B \
     --adapter finetune/output/your_run_name \
     --output finetune/output/merged_model
   ```

2. **Copy `voices.json` vào thư mục merged:**
   ```bash
   cp voices.json finetune/output/merged_model/
   ```

3. **Upload lên HF:**
   ```bash
   huggingface-cli upload your-username/your-model finetune/output/merged_model
   ```

#### Bước 4: Người dùng cuối sử dụng

Giờ đây, người dùng chỉ cần:

```python
from vieneu import Vieneu

# Khởi tạo với model của bạn
tts = Vieneu(backbone_repo="your-username/your-model")

# Tổng hợp ngay - KHÔNG CẦN truyền voice!
audio = tts.infer("Xin chào, tôi là giọng nói custom!")

tts.save(audio, "output.wav")
```

SDK sẽ tự động:
1. Tải `voices.json` từ repo
2. Sử dụng `default_voice` được chỉ định
3. Người dùng không cần lo lắng về reference audio


---

## 🦜 Bí kíp để giọng nói hay (Tips)

1.  **Chất lượng Audio**: Đây là yếu tố quan trọng nhất. Audio phải sạch, không có tiếng vang (reverb), không có nhạc nền hoặc tiếng ồn.
2.  **Nội dung đa dạng**: Cố gắng có đa dạng các loại câu (câu hỏi, câu cảm thán, câu khẳng định) để mô hình học được biểu cảm.
3.  **Dấu câu chính xác**: Hãy đảm bảo văn bản trong `metadata.csv` khớp 100% với những gì người nói phát âm, kể cả các dấu ngắt nghỉ.
4.  **Hardware**: Khuyên dùng GPU có bộ nhớ từ 12GB VRAM trở lên (như RTX 3060, 4060 Ti).

---
