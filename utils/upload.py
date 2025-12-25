# upload.py
import os
import json
import math
import mimetypes
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import requests

import os
import json
import mimetypes
from typing import Optional, List

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_authenticated_youtube(
    client_secrets_file: str = "./data/client_secret.json",
    token_file: str = "./data/youtube_token.json",
):
    creds = None

    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as f:
            creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(
    file_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    category_id: str = "15",
    privacy_status: str = "public",
    client_secrets_file: str = "./data/client_secret.json",
    token_file: str = "./data/youtube_token.json",
) -> str:
    youtube = get_authenticated_youtube(client_secrets_file, token_file)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "video/mp4"

    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[YouTube] Uploading... {int(status.progress() * 100)}%")

    video_id = response["id"]
    return video_id


# # -----------------------------
# # TikTok upload (Content Posting API - Inbox Draft)
# # -----------------------------
# TIKTOK_OPEN_API = "https://open.tiktokapis.com"
# TIKTOK_INIT_INBOX_UPLOAD = f"{TIKTOK_OPEN_API}/v2/post/publish/inbox/video/init/"


# @dataclass
# class TikTokUploadResult:
#     publish_id: str
#     upload_url: str


# def _tiktok_init_inbox_upload(
#     access_token: str,
#     video_size: int,
#     chunk_size: int,
#     total_chunk_count: int,
# ) -> TikTokUploadResult:
#     """
#     Step 1) Initialize TikTok inbox video upload.
#     Returns publish_id + upload_url.
#     """
#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Content-Type": "application/json; charset=UTF-8",
#     }
#     payload = {
#         "source_info": {
#             "source": "FILE_UPLOAD",
#             "video_size": video_size,
#             "chunk_size": chunk_size,
#             "total_chunk_count": total_chunk_count,
#         }
#     }

#     r = requests.post(TIKTOK_INIT_INBOX_UPLOAD, headers=headers, json=payload, timeout=60)
#     # TikTok returns data + error object; handle both
#     try:
#         j = r.json()
#     except Exception:
#         raise RuntimeError(f"[TikTok] init failed (non-json). status={r.status_code} body={r.text[:500]}")

#     if r.status_code != 200 or "data" not in j:
#         raise RuntimeError(f"[TikTok] init failed. status={r.status_code} body={j}")

#     data = j["data"]
#     publish_id = data["publish_id"]
#     upload_url = data["upload_url"]
#     print(f"[TikTok] init ok. publish_id={publish_id}")
#     return TikTokUploadResult(publish_id=publish_id, upload_url=upload_url)


# def _tiktok_put_chunk(
#     upload_url: str,
#     chunk_bytes: bytes,
#     start: int,
#     end: int,
#     total: int,
#     content_type: str = "video/mp4",
# ) -> None:
#     """
#     Step 2) PUT one chunk to upload_url with Content-Range.
#     """
#     headers = {
#         "Content-Type": content_type,
#         "Content-Length": str(len(chunk_bytes)),
#         "Content-Range": f"bytes {start}-{end}/{total}",
#     }
#     r = requests.put(upload_url, headers=headers, data=chunk_bytes, timeout=300)
#     if r.status_code not in (200, 201, 204):
#         raise RuntimeError(f"[TikTok] PUT chunk failed. status={r.status_code} body={r.text[:500]}")


# def upload_to_tiktok_inbox_draft(
#     video_path: str,
#     access_token: str,
#     chunk_size_mb: int = 32,
# ) -> str:
#     """
#     Upload a video to TikTok as an Inbox Draft (user must open TikTok notification to post/edit).

#     Returns: publish_id (useful for tracking/debug).
#     Notes:
#       - Requires `video.upload` scope authorized by the TikTok user. :contentReference[oaicite:1]{index=1}
#       - Chunk rules: 5MB~64MB per chunk (final chunk may be up to 128MB). :contentReference[oaicite:2]{index=2}
#     """
#     if not os.path.exists(video_path):
#         raise FileNotFoundError(video_path)

#     total_size = os.path.getsize(video_path)

#     # enforce TikTok chunk rules (choose safe chunk size)
#     chunk_size = chunk_size_mb * 1024 * 1024
#     chunk_size = max(chunk_size, 5 * 1024 * 1024)
#     chunk_size = min(chunk_size, 64 * 1024 * 1024)

#     if total_size <= 5 * 1024 * 1024:
#         chunk_size = total_size  # must upload whole for tiny files

#     total_chunks = max(1, math.ceil(total_size / chunk_size))
#     if total_chunks > 1000:
#         raise RuntimeError(f"[TikTok] Too many chunks ({total_chunks}). Reduce chunk size or video length.")

#     init = _tiktok_init_inbox_upload(
#         access_token=access_token,
#         video_size=total_size,
#         chunk_size=chunk_size,
#         total_chunk_count=total_chunks,
#     )

#     # Upload sequentially
#     with open(video_path, "rb") as f:
#         for idx in range(total_chunks):
#             start = idx * chunk_size
#             f.seek(start)
#             data = f.read(chunk_size)
#             if not data:
#                 break
#             end = start + len(data) - 1
#             _tiktok_put_chunk(
#                 upload_url=init.upload_url,
#                 chunk_bytes=data,
#                 start=start,
#                 end=end,
#                 total=total_size,
#                 content_type="video/mp4",
#             )
#             pct = int(((idx + 1) / total_chunks) * 100)
#             print(f"[TikTok] Uploading... {pct}% (chunk {idx+1}/{total_chunks})")

#     print("[TikTok] Done. Draft uploaded. User must open TikTok inbox notification to post/edit.")
#     return init.publish_id


# # -----------------------------
# # Convenience: read tokens from env
# # -----------------------------
# def require_env(name: str) -> str:
#     v = os.environ.get(name, "").strip()
#     if not v:
#         raise RuntimeError(f"Missing env var: {name}")
#     return v
