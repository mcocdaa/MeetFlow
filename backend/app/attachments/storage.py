import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

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

    def target_dir(self, target_type: str, target_id: str) -> Path:
        target = (self.root / target_type / target_id).resolve()
        if self.root not in target.parents:
            raise AppError(400, "invalid_path", "附件路径无效")
        return target

    def attachment_path(
        self, target_type: str, target_id: str, stored_name: str
    ) -> Path:
        directory = self.target_dir(target_type, target_id)
        target = (directory / stored_name).resolve()
        if directory not in target.parents:
            raise AppError(400, "invalid_path", "附件路径无效")
        return target

    async def save(
        self,
        target_type: str,
        target_id: str,
        upload,
        expected_sha256: str | None = None,
    ) -> tuple[str, Path, int, str]:
        target_dir = self.target_dir(target_type, target_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload.filename or "file").suffix[:16]
        stored_name = f"{uuid.uuid4()}{suffix}"
        final_path = self.attachment_path(target_type, target_id, stored_name)
        size = 0
        hasher = hashlib.sha256()
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
                    hasher.update(chunk)
                    stream.write(chunk)
            computed_sha256 = hasher.hexdigest()
            if expected_sha256:
                if computed_sha256.lower() != expected_sha256.strip().lower():
                    raise AppError(400, "checksum_mismatch", "附件 SHA-256 校验不匹配")
            os.replace(temp_name, final_path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        return stored_name, final_path, size, computed_sha256

    def chunk_session_dir(self, target_type: str, target_id: str, session_id: str) -> Path:
        target_dir = self.target_dir(target_type, target_id)
        session_dir = (target_dir / f".chunks-{session_id}").resolve()
        if target_dir not in session_dir.parents:
            raise AppError(400, "invalid_path", "附件分片路径无效")
        return session_dir

    def init_chunk_session(
        self,
        target_type: str,
        target_id: str,
        filename: str,
        total_size: int,
        total_chunks: int,
        expected_sha256: str | None = None,
    ) -> str:
        if total_size > self.max_bytes:
            raise AppError(413, "attachment_too_large", "单个附件不能超过 20 MB")
        if total_chunks <= 0:
            raise AppError(400, "invalid_chunks", "分片数量必须大于 0")

        session_id = str(uuid.uuid4())
        session_dir = self.chunk_session_dir(target_type, target_id, session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "session_id": session_id,
            "filename": Path(filename).name[:255],
            "total_size": total_size,
            "total_chunks": total_chunks,
            "expected_sha256": expected_sha256,
        }
        (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return session_id

    async def save_chunk(
        self,
        target_type: str,
        target_id: str,
        session_id: str,
        chunk_index: int,
        upload,
    ) -> int:
        session_dir = self.chunk_session_dir(target_type, target_id, session_id)
        meta_file = session_dir / "meta.json"
        if not meta_file.is_file():
            raise AppError(404, "chunk_session_not_found", "分片上传会话不存在或已过期")
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if not (0 <= chunk_index < meta["total_chunks"]):
            raise AppError(400, "invalid_chunk_index", "分片索引超出范围")

        chunk_path = session_dir / f"chunk_{chunk_index:05d}.part"
        size = 0
        fd, temp_name = tempfile.mkstemp(dir=session_dir, prefix=".chunk-")
        try:
            with os.fdopen(fd, "wb") as stream:
                while chunk := await upload.read(64 * 1024):
                    size += len(chunk)
                    stream.write(chunk)
            os.replace(temp_name, chunk_path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            chunk_path.unlink(missing_ok=True)
            raise
        return size

    def get_chunk_session(
        self, target_type: str, target_id: str, session_id: str
    ) -> dict[str, Any]:
        session_dir = self.chunk_session_dir(target_type, target_id, session_id)
        meta_file = session_dir / "meta.json"
        if not meta_file.is_file():
            raise AppError(404, "chunk_session_not_found", "分片上传会话不存在或已过期")
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        uploaded_chunks = []
        for i in range(meta["total_chunks"]):
            if (session_dir / f"chunk_{i:05d}.part").is_file():
                uploaded_chunks.append(i)
        return {
            "session_id": session_id,
            "filename": meta["filename"],
            "total_size": meta["total_size"],
            "total_chunks": meta["total_chunks"],
            "uploaded_chunks": uploaded_chunks,
            "complete": len(uploaded_chunks) == meta["total_chunks"],
        }

    def complete_chunk_session(
        self, target_type: str, target_id: str, session_id: str
    ) -> tuple[str, Path, int, str, str]:
        session_dir = self.chunk_session_dir(target_type, target_id, session_id)
        meta_file = session_dir / "meta.json"
        if not meta_file.is_file():
            raise AppError(404, "chunk_session_not_found", "分片上传会话不存在或已过期")
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        total_chunks = meta["total_chunks"]

        # Check all chunks
        for i in range(total_chunks):
            if not (session_dir / f"chunk_{i:05d}.part").is_file():
                raise AppError(400, "incomplete_chunks", f"分片 {i} 尚未上传")

        filename = meta["filename"]
        suffix = Path(filename).suffix[:16]
        stored_name = f"{uuid.uuid4()}{suffix}"
        final_path = self.attachment_path(target_type, target_id, stored_name)

        target_dir = self.target_dir(target_type, target_id)
        fd, temp_name = tempfile.mkstemp(dir=target_dir, prefix=".assembled-")
        hasher = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(fd, "wb") as outfile:
                for i in range(total_chunks):
                    chunk_path = session_dir / f"chunk_{i:05d}.part"
                    with chunk_path.open("rb") as infile:
                        while piece := infile.read(64 * 1024):
                            size += len(piece)
                            if size > self.max_bytes:
                                raise AppError(
                                    413,
                                    "attachment_too_large",
                                    "单个附件不能超过 20 MB",
                                )
                            hasher.update(piece)
                            outfile.write(piece)
            computed_sha256 = hasher.hexdigest()
            expected = meta.get("expected_sha256")
            if expected and computed_sha256.lower() != expected.strip().lower():
                raise AppError(400, "checksum_mismatch", "附件 SHA-256 校验不匹配")
            os.replace(temp_name, final_path)
            shutil.rmtree(session_dir, ignore_errors=True)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise

        return stored_name, final_path, size, computed_sha256, filename

    def abort_chunk_session(self, target_type: str, target_id: str, session_id: str) -> None:
        session_dir = self.chunk_session_dir(target_type, target_id, session_id)
        shutil.rmtree(session_dir, ignore_errors=True)

    def remove_target(self, target_type: str, target_id: str) -> None:
        shutil.rmtree(self.target_dir(target_type, target_id), ignore_errors=True)

