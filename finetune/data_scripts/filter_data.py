import os
import re
import soundfile as sf

ACRONYM = re.compile(r"(?:[a-zA-Z]\.){2,}")
ACRONYM_NO_PERIOD = re.compile(r"(?:[A-Z]){2,}")

def text_filter(text: str) -> bool:
    if not text:
        return False
    if re.search(r"\d", text):
        return False
    if ACRONYM.search(text) or ACRONYM_NO_PERIOD.search(text):
        return False
    if text[-1] not in ".,?!":
        return False
    return True

def filter_and_process_dataset(dataset_dir="finetune/dataset"):
    """
    Đọc metadata.csv, lọc dữ liệu kém chất lượng (audio hỏng, text rác, quá ngắn/dài).
    Tạo metadata mới đã clean.
    """
    metadata_path = os.path.join(dataset_dir, "metadata.csv")
    cleaned_metadata_path = os.path.join(dataset_dir, "metadata_cleaned.csv")
    raw_audio_dir = os.path.join(dataset_dir, "raw_audio")
    
    if not os.path.exists(metadata_path):
        print(f"❌ Không tìm thấy file {metadata_path}")
        return

    print("🧹 Bắt đầu lọc dữ liệu...")
    
    valid_samples = []
    skipped_counts = {
        "audio_not_found": 0,
        "audio_error": 0,
        "duration_out_of_range": 0,
        "text_invalid": 0
    }

    with open(metadata_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    total_files = len(lines)
    
    for line in lines:
        parts = line.strip().split('|')
        if len(parts) < 2:
            continue
            
        filename = parts[0]
        text = parts[1]
        
        file_path = os.path.join(raw_audio_dir, filename)
        
        if not os.path.exists(file_path):
            skipped_counts["audio_not_found"] += 1
            continue
            
        try:
            # Chỉ đọc header để lấy duration cho nhanh
            info = sf.info(file_path)
            duration = info.duration
            
            # Lọc audio quá ngắn (<3s) hoặc quá dài (>15s)
            if not (3.0 <= duration <= 15.0):
                skipped_counts["duration_out_of_range"] += 1
                continue
        except Exception:
            skipped_counts["audio_error"] += 1
            continue
            
        if not text_filter(text):
            skipped_counts["text_invalid"] += 1
            continue

        valid_samples.append(f"{filename}|{text}\n")

    with open(cleaned_metadata_path, 'w', encoding='utf-8') as f:
        f.writelines(valid_samples)
        
    print(f"\n🦜 KẾT QUẢ LỌC DỮ LIỆU:")
    print(f"   - Tổng ban đầu: {total_files}")
    print(f"   - Hợp lệ: {len(valid_samples)} ({len(valid_samples)/total_files*100:.1f}%)")
    print(f"   - Bị loại: {total_files - len(valid_samples)}")
    print(f"     + Không tìm thấy audio: {skipped_counts['audio_not_found']}")
    print(f"     + Lỗi file audio: {skipped_counts['audio_error']}")
    print(f"     + Thời lượng không hợp lệ (3-15s): {skipped_counts['duration_out_of_range']}")
    print(f"     + Text rác/chứa số: {skipped_counts['text_invalid']}")
    
    print(f"\n✅ Đã lưu metadata sạch tại: {cleaned_metadata_path}")

if __name__ == "__main__":
    # Luôn xác định đường dẫn tương đương với thư mục gốc của project
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    target_dir = os.path.join(project_root, "finetune", "dataset")
    
    filter_and_process_dataset(dataset_dir=target_dir)
