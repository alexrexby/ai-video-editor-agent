import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional

from .config import FFMPEG_PATH, FFPROBE_PATH, TARGET_WIDTH, TARGET_HEIGHT, TARGET_FPS, TEMP_DIR
from .transcriber import Transcriber
from .silence import SilenceRemover
from .ai_hook import AIHookGenerator
from .glass_renderer import GlassSubtitleRenderer

class VideoMontagePipeline:
    """Master orchestrator for AI video auto-montage with Glass subtitles."""

    def __init__(self):
        self.transcriber = Transcriber()
        self.silence_remover = SilenceRemover(min_silence_duration=0.35)
        self.hook_generator = AIHookGenerator()

    def get_video_duration(self, video_path: Path) -> float:
        """Gets accurate video duration in seconds via ffprobe."""
        cmd = [
            FFPROBE_PATH, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            return float(res.stdout.decode().strip())
        except Exception:
            return 0.0

    def process_video(
        self,
        input_video: Path,
        output_video: Optional[Path] = None,
        palette: str = "amber",
        cut_silence: bool = True,
        generate_hook: bool = True,
        add_emojis: bool = True,
        watermark: Optional[str] = "Brandly AI"
    ) -> Dict[str, Any]:
        """Runs the full auto-montage pipeline on input video."""
        t_start = time.time()
        input_video = Path(input_video)
        if not input_video.exists():
            raise FileNotFoundError(f"Input video not found: {input_video}")

        if output_video is None:
            output_video = TEMP_DIR / f"{input_video.stem}_reels_glass.mp4"
        output_video = Path(output_video)

        print(f"🎬 [Pipeline] Starting montage for: {input_video.name}")
        duration = self.get_video_duration(input_video)
        print(f"⏱️ [Pipeline] Original duration: {duration:.2f}s")

        # Step 1: Extract Audio
        print("🔊 [Step 1/5] Extracting audio track...")
        audio_path = self.transcriber.extract_audio(input_video)

        # Step 2: Transcribe with Whisper (Word-level)
        print("🧠 [Step 2/5] Transcribing speech with Whisper...")
        trans_res = self.transcriber.transcribe(audio_path)
        words = trans_res.get("words", [])
        transcript_text = trans_res.get("text", "")
        print(f"📝 [Pipeline] Recognized {len(words)} words: '{transcript_text[:70]}...'")

        # Step 3: Silence Trimming (Jump cuts)
        current_video = input_video
        if cut_silence and len(words) > 0:
            print("✂️ [Step 3/5] Detecting and trimming silent pauses...")
            silences = self.silence_remover.detect_silence(audio_path)
            if silences:
                print(f"✂️ [Pipeline] Found {len(silences)} pauses. Cutting silence...")
                keep_intervals = self.silence_remover.calculate_keep_intervals(duration, silences)
                trimmed_video = self.silence_remover.cut_silence_from_video(input_video, keep_intervals)
                words = self.silence_remover.adjust_word_timestamps(words, keep_intervals)
                current_video = trimmed_video
                duration = self.get_video_duration(current_video)
                print(f"⏱️ [Pipeline] New trimmed duration: {duration:.2f}s")
            else:
                print("✂️ [Pipeline] No significant pauses found.")
        else:
            print("⏩ [Step 3/5] Silence trimming skipped.")

        # Step 4: AI Hook & Emojis
        hook_text = None
        if generate_hook and transcript_text:
            print("⚡ [Step 4/5] Generating viral hook for first 3 seconds...")
            hook_text = self.hook_generator.generate_hook(transcript_text)
            print(f"⚡ [Pipeline] Generated Hook: '{hook_text}'")

        if add_emojis and words:
            words = self.hook_generator.add_emojis_to_words(words)

        # Step 5: Render Subtitles & Composite Video
        print(f"🎨 [Step 5/5] Rendering Glass subtitles (palette: {palette})...")
        renderer = GlassSubtitleRenderer(
            palette_name=palette,
            show_hook=bool(hook_text),
            watermark_text=watermark
        )
        phrases = renderer.group_words_into_phrases(words, max_words_per_phrase=3)

        # Prepare FFmpeg pipe for 1080x1920 vertical composition
        total_frames = int(duration * TARGET_FPS)
        print(f"🚀 [Pipeline] Compositing {total_frames} frames to {output_video.name}...")

        # FFmpeg command: scale input video to fit/fill 1080x1920, then overlay RGBA pipe
        scale_filter = (
            f"[0:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_WIDTH}:{TARGET_HEIGHT}[bg];"
            f"[bg][1:v]overlay=0:0[outv]"
        )

        ffmpeg_cmd = [
            FFMPEG_PATH, "-y",
            "-i", str(current_video),
            "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{TARGET_WIDTH}x{TARGET_HEIGHT}",
            "-r", str(TARGET_FPS),
            "-i", "-",
            "-filter_complex", scale_filter,
            "-map", "[outv]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-c:a", "aac", "-b:a", "192k",
            str(output_video)
        ]

        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Stream generated subtitle frames into FFmpeg with discrete state memoization
        last_rendered_frame = None
        last_state_key = None

        for frame_idx in range(total_frames):
            time_sec = frame_idx / TARGET_FPS
            state_key = renderer.get_state_key(time_sec, phrases, hook_text=hook_text)
            if state_key != last_state_key or last_rendered_frame is None:
                img = renderer.render_frame(time_sec, phrases, hook_text=hook_text)
                last_rendered_frame = img.tobytes()
                last_state_key = state_key

            proc.stdin.write(last_rendered_frame)

        proc.stdin.close()
        proc.wait()

        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"FFmpeg compositing failed: {err}")

        elapsed = time.time() - t_start
        print(f"✅ [Pipeline] Montage complete in {elapsed:.2f}s! Output saved to: {output_video}")

        return {
            "output_path": output_video,
            "duration": duration,
            "words_count": len(words),
            "hook": hook_text,
            "elapsed_seconds": round(elapsed, 2)
        }
