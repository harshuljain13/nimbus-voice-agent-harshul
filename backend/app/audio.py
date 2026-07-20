"""Audio helpers (Phase 8+): transcode arbitrary browser audio to a uniform WAV, and wrap raw
PCM (Gemini TTS, Phase 9) into a WAV container.

Browsers record WebM/Opus; transcoding to 16 kHz mono WAV up front means every ASR provider gets
a format it accepts. ffmpeg comes from the pip-bundled static build (works on Render/Railway with
no apt install), falling back to a system ffmpeg on PATH.
"""

from __future__ import annotations

import io
import shutil
import struct
import subprocess
from functools import lru_cache

ASR_SAMPLE_RATE = 16000


@lru_cache(maxsize=1)
def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg") or "ffmpeg"


def to_wav(data: bytes, sample_rate: int = ASR_SAMPLE_RATE) -> bytes:
    """Transcode any ffmpeg-readable audio to mono PCM WAV at sample_rate."""
    proc = subprocess.run(
        [_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-ac", "1", "-ar", str(sample_rate), "-f", "wav", "pipe:1"],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg transcode failed: {proc.stderr.decode('utf-8', 'replace')[:200]}")
    return proc.stdout


def pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, bits: int = 16) -> bytes:
    """Wrap raw little-endian PCM in a minimal WAV header (used by Gemini TTS in Phase 9)."""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + len(pcm)))
    buf.write(b"WAVEfmt ")
    buf.write(struct.pack("<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, bits))
    buf.write(b"data")
    buf.write(struct.pack("<I", len(pcm)))
    buf.write(pcm)
    return buf.getvalue()
