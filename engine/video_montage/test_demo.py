import sys
import subprocess
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from engine.video_montage.config import FFMPEG_PATH, TEMP_DIR, TARGET_WIDTH, TARGET_HEIGHT
from engine.video_montage.pipeline import VideoMontagePipeline

def generate_test_speech_video(output_path: Path) -> Path:
    """Creates a vertical 1080x1920 video with realistic synthesized Russian speech."""
    speech_text = (
        "Привет! Это пример субтитров в стиле Glass. "
        "Если ты эксперт или предприниматель, тебе больше не нужен монтажер. "
        "Нейросеть делает всю работу за секунды: "
        "вырезает паузы, придумывает мощный хук и анимирует текст. "
        "Попробуй прямо сейчас!"
    )
    aiff_path = TEMP_DIR / "speech_raw.aiff"
    wav_path = TEMP_DIR / "speech_raw.wav"

    print("🗣️ [Demo] Synthesizing speech track...")
    subprocess.run(["say", "-v", "Milena", speech_text, "-o", str(aiff_path)], check=True)
    subprocess.run([FFMPEG_PATH, "-y", "-i", str(aiff_path), "-ar", "44100", "-ac", "2", str(wav_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    print("🎥 [Demo] Generating vertical speaker video from portrait...")
    speaker_img = Path(__file__).resolve().parent / "sample_speaker.jpg"
    if speaker_img.exists():
        cmd = [
            FFMPEG_PATH, "-y",
            "-loop", "1", "-i", str(speaker_img),
            "-i", str(wav_path),
            "-vf", f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,crop={TARGET_WIDTH}:{TARGET_HEIGHT}",
            "-c:v", "libx264", "-preset", "ultrafast", "-shortest",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path)
        ]
    else:
        cmd = [
            FFMPEG_PATH, "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x13121a:s={TARGET_WIDTH}x{TARGET_HEIGHT}:r=30",
            "-i", str(wav_path),
            "-c:v", "libx264", "-preset", "ultrafast", "-shortest",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path)
        ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print(f"🎬 [Demo] Created realistic speaker test video: {output_path}")
    return output_path


def main():
    print("=" * 60)
    print("🚀 BRANDLY GLASS-STYLE AUTO-MONTAGE PIPELINE TEST")
    print("=" * 60)

    # Check if a custom video was passed
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        input_video = Path(sys.argv[1])
        print(f"📁 Using provided video: {input_video}")
    else:
        raw_video_path = TEMP_DIR / "raw_speaker_input.mp4"
        input_video = generate_test_speech_video(raw_video_path)

    final_output = BASE_DIR / "test_reels_glass.mp4"

    pipeline = VideoMontagePipeline()
    result = pipeline.process_video(
        input_video=input_video,
        output_video=final_output,
        palette="amber",       # Янтарь (желтый акцент как в Brandly)
        cut_silence=True,
        generate_hook=True,
        add_emojis=True,
        watermark="Brandly AI"
    )

    print("\n" + "=" * 60)
    print("🎉 MONTAGE RESULT SUMMARY:")
    print("=" * 60)
    print(f"📁 Output Video: {result['output_path']}")
    print(f"⏱️ Duration:     {result['duration']:.2f}s")
    print(f"📝 Words:        {result['words_count']}")
    print(f"⚡ Generated Hook: {result['hook']}")
    print(f"⚡ Processed in: {result['elapsed_seconds']}s")
    print("=" * 60)

if __name__ == "__main__":
    main()
