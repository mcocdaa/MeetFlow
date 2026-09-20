import hashlib
import io
import pytest

from app.database import retry_on_db_lock
from sqlalchemy.exc import OperationalError


def test_streaming_sha256_verification(authenticated_client, meeting_id):
    content = b"Streamed content with sha256 verification"
    expected_sha256 = hashlib.sha256(content).hexdigest()

    # Success case with correct SHA256 header
    res = authenticated_client.post(
        f"/api/attachments/meeting/{meeting_id}",
        files={"file": ("verified.txt", content, "text/plain")},
        headers={"X-Content-SHA256": expected_sha256},
    )
    assert res.status_code == 201
    attachment = res.json()
    assert attachment["sha256"] == expected_sha256

    # Failure case with mismatched SHA256 header
    bad_res = authenticated_client.post(
        f"/api/attachments/meeting/{meeting_id}",
        files={"file": ("bad.txt", content, "text/plain")},
        headers={"X-Content-SHA256": "0" * 64},
    )
    assert bad_res.status_code == 400
    assert bad_res.json()["error"]["code"] == "checksum_mismatch"


def test_chunked_resumable_upload_lifecycle(authenticated_client, meeting_id):
    full_data = b"Part1-data-AAAA" + b"Part2-data-BBBB" + b"Part3-data-CCCC"
    total_size = len(full_data)
    expected_sha256 = hashlib.sha256(full_data).hexdigest()

    chunk1 = b"Part1-data-AAAA"
    chunk2 = b"Part2-data-BBBB"
    chunk3 = b"Part3-data-CCCC"
    chunks = [chunk1, chunk2, chunk3]

    # 1. Initialize session
    init_res = authenticated_client.post(
        f"/api/attachments/meeting/{meeting_id}/chunks/init",
        json={
            "filename": "big_archive.bin",
            "total_size": total_size,
            "total_chunks": 3,
            "sha256": expected_sha256,
        },
    )
    assert init_res.status_code == 201
    session_id = init_res.json()["session_id"]

    # 2. Upload chunk 0
    res_c0 = authenticated_client.post(
        f"/api/attachments/meeting/{meeting_id}/chunks/{session_id}",
        data={"chunk_index": 0},
        files={"chunk": ("chunk0.part", chunk1, "application/octet-stream")},
    )
    assert res_c0.status_code == 200
    assert res_c0.json()["status"] == "uploaded"

    # 3. Check status (resume check)
    status_1 = authenticated_client.get(
        f"/api/attachments/meeting/{meeting_id}/chunks/{session_id}"
    ).json()
    assert status_1["uploaded_chunks"] == [0]
    assert status_1["complete"] is False

    # 4. Upload remaining chunks
    for idx, chunk_bytes in [(1, chunk2), (2, chunk3)]:
        res = authenticated_client.post(
            f"/api/attachments/meeting/{meeting_id}/chunks/{session_id}",
            data={"chunk_index": idx},
            files={"chunk": (f"chunk{idx}.part", chunk_bytes, "application/octet-stream")},
        )
        assert res.status_code == 200

    # 5. Check status: complete
    status_2 = authenticated_client.get(
        f"/api/attachments/meeting/{meeting_id}/chunks/{session_id}"
    ).json()
    assert status_2["uploaded_chunks"] == [0, 1, 2]
    assert status_2["complete"] is True

    # 6. Complete upload
    complete_res = authenticated_client.post(
        f"/api/attachments/meeting/{meeting_id}/chunks/{session_id}/complete"
    )
    assert complete_res.status_code == 201
    attachment = complete_res.json()
    assert attachment["original_name"] == "big_archive.bin"
    assert attachment["size"] == total_size
    assert attachment["sha256"] == expected_sha256

    # 7. Download and verify content
    download = authenticated_client.get(attachment["download_url"])
    assert download.status_code == 200
    assert download.content == full_data


def test_chunked_upload_abort(authenticated_client, meeting_id):
    init_res = authenticated_client.post(
        f"/api/attachments/meeting/{meeting_id}/chunks/init",
        json={
            "filename": "abandoned.bin",
            "total_size": 100,
            "total_chunks": 2,
        },
    )
    session_id = init_res.json()["session_id"]

    abort_res = authenticated_client.delete(
        f"/api/attachments/meeting/{meeting_id}/chunks/{session_id}"
    )
    assert abort_res.status_code == 204

    # Getting status after abort should fail with 404
    get_res = authenticated_client.get(
        f"/api/attachments/meeting/{meeting_id}/chunks/{session_id}"
    )
    assert get_res.status_code == 404


def test_retry_on_db_lock_decorator():
    call_count = 0

    @retry_on_db_lock(max_retries=3, initial_backoff=0.01, backoff_factor=1.5)
    def flaky_db_op():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise OperationalError("database is locked", {}, None)
        return "success"

    assert flaky_db_op() == "success"
    assert call_count == 3
