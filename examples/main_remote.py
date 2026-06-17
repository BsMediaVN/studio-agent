"""
VieNeu-TTS SDK Example: Remote Mode
Version: 1.1.6
"""

from vieneu import Vieneu
import os

def main():
    print("🚀 Initializing VieNeu Remote Client...")
    
    # ---------------------------------------------------------
    # PART 0: PRE-REQUISITES & CONFIG
    # ---------------------------------------------------------
    # Ensure output directory exists
    os.makedirs("outputs", exist_ok=True)
    
    # Replace with your actual LMDeploy server URL
    # Example: 'http://localhost:23333/v1' or a public tunnel URL
    REMOTE_API_BASE = 'http://bore.pub:34939/v1' # Replace with your actual LMDeploy server URL
    REMOTE_MODEL_ID = "pnnbao-ump/VieNeu-TTS"

    # ---------------------------------------------------------
    # PART 1: INITIALIZATION
    # ---------------------------------------------------------
    # Remote mode is LIGHTWEIGHT: It doesn't load the heavy 0.3B/0.5B model locally.
    # It only loads a small Codec (distill-neucodec) to encode/decode audio instantly.
    print(f"📡 Connecting to server: {REMOTE_API_BASE}...")
    try:
        tts = Vieneu(
            mode='remote', 
            api_base=REMOTE_API_BASE, 
            model_name=REMOTE_MODEL_ID
        )
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return

    # ---------------------------------------------------------
    # PART 2: LIST REMOTE VOICES
    # ---------------------------------------------------------
    # Fetch available voice presets from the remote server
    available_voices = tts.list_preset_voices()
    print(f"📋 Found {len(available_voices)} remote voices.")
    
    if available_voices:
        print("   Showing all voices:")
        for desc, name in available_voices:
            print(f"   - {desc} (ID: {name})")

    # ---------------------------------------------------------
    # PART 3: USE SPECIFIC VOICE ID
    # ---------------------------------------------------------
    if available_voices:
        print("\n--- PART 3: Using Specific Voice ID ---")
        # Select a demonstration voice (Index 1 preferred for variety)
        voice_info = available_voices[1] if len(available_voices) > 1 else available_voices[0]
        desc, voice_id = voice_info
        
        print(f"👤 Synthesis voice: {desc} (ID: {voice_id})")
        
        # Get reference data for this specific voice
        voice_data = tts.get_preset_voice(voice_id)
        
        test_text = f"Chào bạn, tôi đang nói bằng giọng của {desc}."
        audio_spec = tts.infer(text=test_text, voice=voice_data)
        
        save_path = f"outputs/remote_{voice_id}.wav"
        tts.save(audio_spec, save_path)
        print(f"💾 Saved synthesis to: {save_path}")

    # ---------------------------------------------------------
    # PART 4: REMOTE SPEECH SYNTHESIS (DEFAULT)
    # ---------------------------------------------------------
    print("\n--- PART 4: Standard Synthesis (Default) ---")
    text_input = "Chế độ remote giúp tích hợp VieNeu vào ứng dụng Web hoặc App cực nhanh mà không cần GPU tại máy khách."
    
    print("🎧 Sending synthesis request to server...")
    # The SDK handles splitting long text and joining results automatically
    audio = tts.infer(text=text_input)
    
    tts.save(audio, "outputs/remote_output.wav")
    print("💾 Saved remote synthesis to: outputs/remote_output.wav")

    # ---------------------------------------------------------
    # PART 5: ZERO-SHOT VOICE CLONING (REMOTE)
    # ---------------------------------------------------------
    # Even in remote mode, you can still clone voices!
    # STEP: The SDK encodes the audio LOCALLY first, then sends 'codes' to the server.
    ref_audio = "examples/audio_ref/example_ngoc_huyen.wav"
    ref_text = "Tác phẩm dự thi bảo đảm tính khoa học, tính đảng, tính chiến đấu, tính định hướng."
    
    if os.path.exists(ref_audio):
        print("\n--- PART 5: Remote Voice Cloning ---")
        print(f"🦜 Encoding {ref_audio} locally and sending codes to server...")
        cloned_audio = tts.infer(
            text="Đây là giọng nói được clone và xử lý thông qua VieNeu Server.",
            ref_audio=ref_audio,
            ref_text=ref_text
        )
        tts.save(cloned_audio, "outputs/remote_cloned_output.wav")
        print("💾 Saved remote cloned voice to: outputs/remote_cloned_output.wav")

    # ---------------------------------------------------------
    # PART 6: NATIVE ASYNC INFERENCE (High Performance)
    # ---------------------------------------------------------
    print("\n📌 PART 6: Native Async Processing")
    print("=" * 60)
    
    # Define voice for async tasks (Using index 0 as default)
    if available_voices:
        _, batch_voice_id = available_voices[0]
        voice_data_batch = tts.get_preset_voice(batch_voice_id)
    else:
        voice_data_batch = None

    try:
        import asyncio
        import time
        
        async def run_async_examples():
            print("🚀 Testing Native Async API...")
            async_batch_texts = [
                "Sài Gòn trong mắt tôi là những buổi sáng sớm tinh mơ, khi nắng vừa lên và thành phố bắt đầu nhộn nhịp tiếng còi xe, tiếng rao hàng rong âm vang khắp các con hẻm nhỏ.",
                "Nhắc đến Sài Gòn, người ta không thể quên được hương vị cà phê sữa đá lề đường hay bát hủ tiếu gõ thơm phức, những nét ẩm thực đã trở thành linh hồn của mảnh đất này.",
                "Dù là một đô thị sầm uất với những tòa cao ốc chọc trời, Sài Gòn vẫn giữ cho mình những góc phố rêu phong, những mái chùa cổ kính thầm lặng chứng kiến dòng thời gian trôi.",
                "Người Sài Gòn nổi tiếng bao dung và hiếu khách, sẵn sàng dang tay đón nhận những người con từ khắp mọi miền tổ quốc về đây để cùng nhau xây dựng ước mơ và tương lai."
            ]
            
            start_async = time.time()
            # infer_batch_async maintains order and manages concurrency internally
            batch_results = await tts.infer_batch_async(
                async_batch_texts, 
                voice=voice_data_batch,
                concurrency_limit=10
            )
            
            elapsed_async = time.time() - start_async
            print(f"✅ Async Batch completed in {elapsed_async:.2f}s")
            
            for i, wav in enumerate(batch_results):
                tts.save(wav, f"outputs/remote_native_batch_async_{i}.wav")
            print(f"💾 Saved {len(batch_results)} async batch files.")

        # Run the async loop
        asyncio.run(run_async_examples())
        
    except ImportError:
        print("⚠️  aiohttp not installed. Please run: pip install aiohttp")
    except Exception as e:
        print(f"⚠️  Async example error: {e}")

    # ---------------------------------------------------------
    # PART 7: DONE
    # ---------------------------------------------------------
    print("\n✅ All remote tasks completed!")
    print("📁 Check the 'outputs/' folder for generated files.")

if __name__ == "__main__":
    main()
