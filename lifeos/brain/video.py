"""Videos (issue 84): what the Brain is given of one. It reads a transcript it writes itself and a few key frames, so a file is never sent whole.
A file over 500 MB is refused with a clear message before anything is read."""
import shutil
import subprocess
import tempfile
from pathlib import Path

from frappe import _

from lifeos.brain.sources import VIDEO_EXT

MAX_BYTES = 500 * 1024 * 1024
FRAMES = 4


def is_video(file_name: str | None) -> bool:
	return (file_name or "").lower().endswith(VIDEO_EXT)


def too_big_message(file_name: str, size: int) -> str | None:
	"""The message to show when a video is over the limit, else None."""
	if (size or 0) <= MAX_BYTES:
		return None
	return _("{0} is {1} MB. Life OS reads videos up to 500 MB. Cut it shorter or send a smaller file.").format(file_name, round(size / 1048576))


def key_frames(file_doc, count: int = FRAMES) -> list:
	"""Up to `count` small JPEG frames spread over the video, as bytes. Empty when ffmpeg is not installed or cannot read the file."""
	if not shutil.which("ffmpeg"):
		return []
	try:
		source = file_doc.get_full_path()
		seconds = _duration(source)
		step = max(seconds / (count + 1), 0.5)
		with tempfile.TemporaryDirectory() as tmp:
			subprocess.run(["ffmpeg", "-v", "error", "-i", source, "-vf", f"fps=1/{step:.2f},scale=640:-2", "-frames:v", str(count), f"{tmp}/f%d.jpg"],
				check=True, timeout=120, capture_output=True)
			return [p.read_bytes() for p in sorted(Path(tmp).glob("f*.jpg"))[:count]]  # nosemgrep: frappe-security-file-traversal -- ffmpeg's own output in a temporary folder made here
	except Exception:
		return []


def _duration(source: str) -> float:
	try:
		out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", source], check=True, timeout=30,
			capture_output=True, text=True).stdout.strip()
		return float(out)
	except Exception:
		return 10.0
