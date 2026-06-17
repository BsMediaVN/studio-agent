import os
import csv
import soundfile as sf
from datasets import load_dataset
from tqdm import tqdm

from datasets import load_dataset, Audio
import io

def download_sample_data(output_dir="finetune/dataset", num_samples=10):
    """
    Tải bộ dữ liệu mẫu từ Hugging Face (ví dụ: pnnbao-ump/ngochuyen_voice) và chuẩn bị cho finetune.
    """
    
    raw_audio_dir = os.path.join(output_dir, "raw_audio")
    metadata_path = os.path.join(output_dir, "metadata.csv")
    
    os.makedirs(raw_audio_dir, exist_ok=True)
    
    print(f"🔄 Đang tải dataset pnnbao-ump/ngochuyen_voice từ Hugging Face...")
    dataset = load_dataset("pnnbao-ump/ngochuyen_voice", split="train", streaming=True)
    
    dataset = dataset.cast_column("audio", Audio(decode=False))
    
    print(f"✅ Đã kết nối. Bắt đầu lưu {num_samples} mẫu vào '{output_dir}'...")
    
    # File format: filename|transcription
    with open(metadata_path, 'w', encoding='utf-8', newline='') as f:
        
        count = 0
        for sample in tqdm(dataset, total=num_samples):
            if count >= num_samples:
                break
                
            try:
                audio_data = sample["audio"]
                audio_bytes = audio_data["bytes"]
                
                audio_array, sampling_rate = sf.read(io.BytesIO(audio_bytes))
                
                text = sample["transcription"]
                
                original_filename = sample.get("file_name", f"sample_{count:03d}.wav")
                filename = os.path.basename(original_filename)
                
                file_path = os.path.join(raw_audio_dir, filename)
                
                sf.write(file_path, audio_array, sampling_rate)
                
                # Ghi vào metadata (format: filename|text)
                f.write(f"{filename}|{text}\n")
                
                count += 1
            except Exception as e:
                print(f"\n⚠️ Lỗi khi xử lý mẫu {count}: {e}")
                continue
            
    print(f"\n🦜 Hoàn tất! Đã tạo dữ liệu mẫu tại:")
    print(f"   - Audio: {raw_audio_dir}")
    print(f"   - Metadata: {metadata_path}")
    print("\nBạn có thể kiểm tra file metadata.csv để xem cấu trúc.")

if __name__ == "__main__":
    # Luôn xác định đường dẫn tương đương với thư mục gốc của project
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    target_dir = os.path.join(project_root, "finetune", "dataset")
    
    download_sample_data(output_dir=target_dir, num_samples=7000)
