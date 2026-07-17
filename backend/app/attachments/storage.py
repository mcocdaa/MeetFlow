import os
import shutil
import tempfile
import uuid
from pathlib import Path

from app.errors import AppError

INLINE_IMAGES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def sniff_inline_image(path: Path) -> str | None:
    with path.open("rb") as stream:
        header = stream.read(16)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


class AttachmentStorage:
    def __init__(self, data_dir: Path, max_bytes: int):
        self.root = (data_dir / "uploads").resolve()
        self.max_bytes = max_bytes

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def meeting_dir(self, meeting_id: str) -> Path:
        target = (self.root / meeting_id).resolve()
        if self.root not in target.parents:
            raise AppError(400, "invalid_path", "附件路径无效")
        return target

    def attachment_path(self, meeting_id: str, stored_name: str) -> Path:
        directory = self.meeting_dir(meeting_id)
        target = (directory / stored_name).resolve()
        if directory not in target.parents:
            raise AppError(400, "invalid_path", "附件路径无效")
        return target

    async def save(self, meeting_id: str, upload) -> tuple[str, Path, int]:
        target_dir = self.meeting_dir(meeting_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload.filename or "file").suffix[:16]
        stored_name = f"{uuid.uuid4()}{suffix}"
        final_path = self.attachment_path(meeting_id, stored_name)
        size = 0
        fd, temp_name = tempfile.mkstemp(dir=target_dir, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as stream:
                while chunk := await upload.read(64 * 1024):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise AppError(
                            413,
                            "attachment_too_large",
                            "单个附件不能超过 20 MB",
                        )
                    stream.write(chunk)
            os.replace(temp_name, final_path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        return stored_name, final_path, size

    def remove_meeting(self, meeting_id: str) -> None:
        shutil.rmtree(self.meeting_dir(meeting_id), ignore_errors=True)
