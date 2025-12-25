import os
import requests
import time
from moviepy import AudioFileClip
from moviepy.audio.AudioClip import concatenate_audioclips

BGM_PROMPT = """Fast-paced, short intro.
Anthropomorphic animals as a {job}.
High-energy, exciting, confident.
Electronic synths, punchy bass, driving drums.
Modern EDM-inspired cinematic groove.
No piano, no vocals, no lyrics.
Target duration: about {duration} seconds (okay if longer; will be trimmed)."""

SUNO_GENERATE_URL = "https://api.sunoapi.org/api/v1/generate"
SUNO_RECORD_INFO_URL = "https://api.sunoapi.org/api/v1/generate/record-info"

def generate_bgm(
    job: str,
    duration: int,
    audio_path: str
):
    prompt = BGM_PROMPT.format(job=job, duration=duration)
    suno_api_key = os.environ.get("SUNO_API_KEY")

    payload = {
        "customMode": True,
        "instrumental": True,
        "model": "V4_5ALL",
        "callBackUrl": "https://api.example.com/callback",
        "prompt": prompt,
        "style": "hybrid electronic cinematic short",
        "title": f"{job} bgm",
        "personaId": "",
        "negativeTags": "vocals, piano, lyrics, singing, heavy metal",
        "vocalGender": "",
        "styleWeight": 0.65,
        "weirdnessConstraint": 0.5,
        "audioWeight": 0.65,
    }

    headers = {
        "Authorization": f"Bearer {suno_api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(SUNO_GENERATE_URL, json=payload, headers=headers)
    resp.raise_for_status()
    task_id = resp.json()["data"]["taskId"]

    print(f"[Suno] taskId = {task_id}")

    audio_url = None
    for _ in range(120):
        time.sleep(5)

        info_resp = requests.get(
            SUNO_RECORD_INFO_URL,
            params={"taskId": task_id},
            headers=headers,
        )
        info_resp.raise_for_status()
        info = info_resp.json()["data"]

        if info["status"] == "SUCCESS":
            suno_data = info["response"]["sunoData"]
            audio_url = suno_data[0]["audioUrl"]
            break

    if audio_url is None:
        raise RuntimeError("Suno BGM generation timed out")

    print("[Suno] downloading:", audio_url)
    r = requests.get(audio_url, stream=True)
    r.raise_for_status()
    with open(audio_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    print("[Suno] BGM saved to:", audio_path)

def loop_or_trim_audio_to_duration(audio_clip: AudioFileClip, target_duration: float):
    if audio_clip.duration is None:
        return audio_clip

    if audio_clip.duration >= target_duration:
        return audio_clip.subclipped(0, target_duration)

    parts = []
    t = 0.0
    while t < target_duration:
        remain = target_duration - t
        if audio_clip.duration <= remain:
            parts.append(audio_clip)
            t += audio_clip.duration
        else:
            parts.append(audio_clip.subclipped(0, remain))
            t += remain
    return concatenate_audioclips(parts)