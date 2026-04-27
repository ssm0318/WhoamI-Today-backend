import os
import subprocess
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

ALLOWED_VIDEO_EXTENSIONS = ['.mp4', '.mov', '.webm']
ALLOWED_VIDEO_MIME_TYPES = ['video/mp4', 'video/quicktime', 'video/webm']
MAX_VIDEO_SIZE_BYTES = 50 * 1024 * 1024  # 50MB
MAX_VIDEO_DURATION_SECONDS = 30


def validate_video_file(file):
    """Validate video file extension, size, and duration. Returns duration in seconds."""
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValidationError(
            f'지원하지 않는 동영상 형식입니다. 허용: {", ".join(ALLOWED_VIDEO_EXTENSIONS)}'
        )

    if file.size > MAX_VIDEO_SIZE_BYTES:
        raise ValidationError(
            f'동영상 파일이 너무 큽니다. 최대 {MAX_VIDEO_SIZE_BYTES // (1024 * 1024)}MB'
        )

    duration = _get_video_duration(file)
    if duration is not None and duration > MAX_VIDEO_DURATION_SECONDS:
        raise ValidationError(
            f'동영상이 너무 깁니다. 최대 {MAX_VIDEO_DURATION_SECONDS}초'
        )

    return duration


def generate_video_thumbnail(video_file):
    """Generate a JPEG thumbnail from a video file using ffmpeg. Returns ContentFile or None."""
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
        for chunk in video_file.chunks():
            tmp_video.write(chunk)
        tmp_video_path = tmp_video.name

    tmp_thumb_path = tmp_video_path + '_thumb.jpg'

    try:
        subprocess.run(
            [
                'ffmpeg', '-i', tmp_video_path,
                '-ss', '00:00:00.0',
                '-vframes', '1',
                '-vf', 'scale=480:-2,format=yuvj420p',
                '-strict', 'unofficial',
                '-update', '1',
                '-y', tmp_thumb_path,
            ],
            capture_output=True,
            timeout=15,
        )

        if os.path.exists(tmp_thumb_path):
            with open(tmp_thumb_path, 'rb') as f:
                thumbnail_content = f.read()
            return ContentFile(thumbnail_content, name='thumbnail.jpg')
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # FileNotFoundError: ffmpeg not installed (e.g. local dev without ffmpeg)
        pass
    finally:
        if os.path.exists(tmp_video_path):
            os.unlink(tmp_video_path)
        if os.path.exists(tmp_thumb_path):
            os.unlink(tmp_thumb_path)
        video_file.seek(0)

    return None


def _get_video_duration(file):
    """Extract video duration in seconds using ffprobe."""
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        for chunk in file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        # FileNotFoundError: ffprobe not installed (e.g. local dev without ffmpeg)
        pass
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        file.seek(0)

    return None
