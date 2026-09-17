import re
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict, Any
from .config import FFMPEG_PATH, TEMP_DIR

class SilenceRemover:
    """Detects and removes long pauses from video, adjusting timestamps."""

    def __init__(self, min_silence_duration: float = 0.35, noise_threshold_db: int = -30):
        self.min_silence_duration = min_silence_duration
        self.noise_threshold_db = noise_threshold_db

    def detect_silence(self, audio_or_video_path: Path) -> List[Tuple[float, float]]:
        """Returns list of (silence_start, silence_end) in seconds."""
        cmd = [
            FFMPEG_PATH, "-y",
            "-i", str(audio_or_video_path),
            "-af", f"silencedetect=noise={self.noise_threshold_db}dB:d={self.min_silence_duration}",
            "-f", "null", "-"
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = res.stderr.decode("utf-8", errors="ignore")

        silences = []
        current_start = None

        for line in output.splitlines():
            start_match = re.search(r"silence_start:\s*([0-9\.]+)", line)
            if start_match:
                current_start = float(start_match.group(1))
            end_match = re.search(r"silence_end:\s*([0-9\.]+)", line)
            if end_match and current_start is not None:
                end = float(end_match.group(1))
                if end - current_start >= self.min_silence_duration:
                    silences.append((current_start, end))
                current_start = None

        return silences

    def calculate_keep_intervals(self, total_duration: float, silences: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Calculates intervals of active speech to keep."""
        if not silences:
            return [(0.0, total_duration)]

        keeps = []
        last_end = 0.0

        for s_start, s_end in silences:
            # Add margin of 0.05s so speech doesn't get clipped unnaturally
            keep_start = max(0.0, last_end)
            keep_end = min(total_duration, s_start + 0.05)
            if keep_end > keep_start + 0.1:
                keeps.append((keep_start, keep_end))
            last_end = max(0.0, s_end - 0.05)

        if last_end < total_duration:
            keeps.append((last_end, total_duration))

        return keeps

    def cut_silence_from_video(self, video_path: Path, keep_intervals: List[Tuple[float, float]], output_path: Path = None) -> Path:
        """Uses FFmpeg to cut and concatenate keep intervals."""
        if output_path is None:
            output_path = TEMP_DIR / f"{video_path.stem}_trimmed.mp4"

        if len(keep_intervals) <= 1:
            # Nothing to cut or single interval
            return video_path

        # Build FFmpeg complex filter
        filter_parts = []
        concat_inputs = []
        for idx, (start, end) in enumerate(keep_intervals):
            filter_parts.append(
                f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{idx}];"
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{idx}];"
            )
            concat_inputs.append(f"[v{idx}][a{idx}]")

        filter_str = "".join(filter_parts) + "".join(concat_inputs) + f"concat=n={len(keep_intervals)}:v=1:a=1[outv][outa]"

        cmd = [
            FFMPEG_PATH, "-y",
            "-i", str(video_path),
            "-filter_complex", filter_str,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg silence cut failed: {res.stderr.decode('utf-8', errors='ignore')}")

        return output_path

    def adjust_word_timestamps(self, words: List[Dict[str, Any]], keep_intervals: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
        """Maps old timestamps to new shortened video timestamps."""
        if len(keep_intervals) <= 1:
            return words

        adjusted = []
        for w in words:
            w_start = w["start"]
            w_end = w["end"]

            # Find which keep interval this word falls into
            new_start = None
            new_end = None
            elapsed_new_time = 0.0

            for k_start, k_end in keep_intervals:
                interval_dur = k_end - k_start
                if w_start >= k_start and w_start <= k_end:
                    new_start = elapsed_new_time + (w_start - k_start)
                if w_end >= k_start and w_end <= k_end:
                    new_end = elapsed_new_time + (w_end - k_start)
                elif w_end > k_end and new_start is not None and new_end is None:
                    new_end = elapsed_new_time + interval_dur

                elapsed_new_time += interval_dur

            if new_start is not None and new_end is not None:
                adjusted.append({
                    "word": w["word"],
                    "start": round(new_start, 3),
                    "end": round(max(new_start + 0.05, new_end), 3)
                })

        return adjusted
