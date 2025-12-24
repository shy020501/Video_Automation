import os
import json
import argparse
import random
import re
import time
import requests
import numpy as np

from moviepy import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips
from moviepy.audio.AudioClip import concatenate_audioclips
from PIL import Image, ImageFilter, ImageDraw, ImageFont

from openai import OpenAI
import replicate
import asyncio
import aiohttp
import aiofiles
import beatoven_sdk

DATA_PROMPT = """You are helping me build a dataset for generative video creation.

Task:
- Generate EXACTLY 10 unique jobs.
- For each job, list 3–4 animals that would be visually and conceptually suitable for that job.
- Jobs must be imaginative but still easy to recognize visually in a short video.
- Animals should make intuitive sense for the job (based on behavior, stereotypes, or symbolism).

Constraints:
- DO NOT reuse or paraphrase any of the following existing jobs:
{existing_jobs}

- Each job must be a single noun phrase (e.g., "firefighter", "librarian", "street photographer").
- Animals must be common, recognizable animals (no mythical creatures).

Output format:
Return ONLY valid JSON in the following structure:

{{
  "job_name": {{
    "animals": ["animal_1", "animal_2", ...],
    "used": false
  }}
}}

- Use lowercase for all job and animal names.
- Do not include any explanations, comments, or extra text.
"""

IMAGE_PROMPT = """Cinematic photographic image, ultra-realistic, natural and lifelike lighting.
A towering anthropomorphic {animal} portrayed as a professional {job}, with a powerful yet elegant physique and confident upright posture.

Outfit design:
The {animal} wears a premium, tailored {job} uniform that makes the profession instantly recognizable at a glance.
Include iconic {job} signifiers (distinctive silhouette, accessories, tools, insignia, badges, helmet/hat, utility belt, gloves, or footwear) while keeping everything realistic and high-end.
The outfit is intelligently adapted to the {animal}'s anatomy—custom openings for ears/horns, adjusted collar and shoulder structure for a different neck shape, tailored sleeves/legs for paws or hooves, and natural accommodation for a tail, wings, or fur/feathers.
The design preserves the {animal}'s natural facial features and texture; the uniform complements the animal rather than covering it.
Realistic fabric weight, stitching, seams, and subtle wear consistent with real professional gear.

Facial expression is calm, dignified, and focused, conveying intelligence and purpose.
Full-body shot, centered composition, standing or walking forward with confidence.

Environment:
A realistic, job-specific working environment directly associated with the profession of a {job}.
The setting should clearly indicate where a {job} would normally work in real life, using recognizable tools, furniture, equipment, architecture, and spatial layout.
The environment feels functional and authentic rather than ceremonial or decorative.
Natural lighting appropriate to the location, with cinematic depth but grounded realism.

Photography style:
High-end editorial photography, shallow depth of field, crisp focus, rich details, natural reflections, cinematic contrast.
No cartoon style, no illustration, no exaggeration.

Pose and orientation:
The {animal} stands still, facing directly forward toward the camera.
Body orientation remains front-facing, with a balanced, grounded stance.

Composition:
Single subject, full body visible, clean background composition, professional cinematic framing."""


VIDEO_PROMPT = """The anthropomorphic {animal} dressed as a {job} walks forward at a slow, confident, ceremonial pace.
The movement is dignified and controlled, with smooth, deliberate steps and natural body motion.
Posture remains upright and composed, conveying authority and professionalism.
The character does not look directly at the camera; instead, their gaze subtly shifts forward or slightly around the environment, as if entering an important professional or ceremonial moment.

Clothing motion:
The job-specific outfit moves naturally with each step, showing realistic fabric weight, subtle folds, and gentle motion.

Environment:
The scene takes place in the same grand, professional setting as the image, with warm cinematic lighting.
Reflections from polished floors, architectural details, and ambient light enhance realism.

Camera:
Camera is very slowly tracking backward.
No sudden movements, no zooms, no shakes.
Ultra-smooth cinematic motion with shallow depth of field.
"""

BGM_PROMPT = """Fast-paced, short intro.
Anthropomorphic animals as a {job}.
High-energy, exciting, confident.
Electronic synths, punchy bass, driving drums.
Modern EDM-inspired cinematic groove.
No piano, no vocals, no lyrics.
Target duration: about {duration} seconds (okay if longer; will be trimmed)."""

FONT_PATH = "./data/fonts/PlayfairDisplay-VariableFont_wght.ttf"

SUNO_GENERATE_URL = "https://api.sunoapi.org/api/v1/generate"
SUNO_RECORD_INFO_URL = "https://api.sunoapi.org/api/v1/generate/record-info"

def get_font(path: str, size: int):
    return ImageFont.truetype(path, size=size)

def sanitize_file_name(s: str):
    s = s.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s

def find_unused_pair(data):
    return [
        (job, value.get("animals", []))
        for job, value in data.items()
        if isinstance(value, dict) and value.get("used") is False
    ]

def create_data(client, data):
    existing_jobs = list(data.keys())

    prompt = DATA_PROMPT.format(
        existing_jobs=", ".join(existing_jobs) if existing_jobs else "none"
    )

    response = client.responses.create(
        model="gpt-5-nano",
        input=prompt,
    )

    try:
        raw = response.output_text.strip()
        raw = raw[raw.find("{"): raw.rfind("}") + 1]
        new_data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Failed to parse JSON from model output:\n{response.output_text}"
        ) from e

    data.update(new_data)

def generate_image(job: str, animal: str, image_path: str):
    prompt = IMAGE_PROMPT.format(job=job, animal=animal)

    output = replicate.run(
        "bytedance/seedream-4",
        input={
            "prompt": prompt,
            "aspect_ratio": "9:16"
        },
    )

    img_file = output[0]
    with open(image_path, "wb") as f:
        f.write(img_file.read())

def generate_video(job: str, animal: str, image_path: str, video_path: str):
    prompt = VIDEO_PROMPT.format(job=job, animal=animal)

    with open(image_path, "rb") as image:
        output = replicate.run(
            "bytedance/seedance-1-pro-fast",
            input={
                "image": image,
                "prompt": prompt,
                "fps": 24,
                "duration": 4,
                "aspect_ratio": "9:16",
                "resolution": "720p",
            }
        )

    with open(video_path, "wb") as file:
        file.write(output.read())

def _draw_center_text(img: Image.Image, job: str, font_main: ImageFont.ImageFont, font_job: ImageFont.ImageFont):
    draw = ImageDraw.Draw(img)
    W, H = img.size

    line1 = "What if ____ was a"
    line2 = f"\"{job.capitalize()}\""

    bbox1 = draw.textbbox((0, 0), line1, font=font_main)
    w1, h1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
    x1 = (W - w1) // 2
    y1 = int(H * 0.18)

    bbox2 = draw.textbbox((0, 0), line2, font=font_job)
    w2, h2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]
    x2 = (W - w2) // 2
    y2 = y1 + h1 + int(h2 * 0.3)

    shadow1 = max(2, font_main.size // 18)
    shadow2 = max(2, font_job.size // 18)

    draw.text((x1 + shadow1, y1 + shadow1), line1, font=font_main, fill=(0, 0, 0))
    draw.text((x1, y1), line1, font=font_main, fill=(255, 255, 255))

    draw.text((x2 + shadow2, y2 + shadow2), line2, font=font_job, fill=(0, 0, 0))
    draw.text((x2, y2), line2, font=font_job, fill=(255, 255, 255))

    return img

def _draw_top_label(img: Image.Image, text: str, font: ImageFont.ImageFont):
    draw = ImageDraw.Draw(img)
    W, H = img.size

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    x = (W - tw) // 2
    y = int(H * 0.035)

    shadow = max(2, font.size // 14)
    draw.text((x + shadow, y + shadow), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=(255, 255, 255))

    return img

def make_intro(first_video_path: str, job: str, intro_sec: float = 1.5):
    base = VideoFileClip(first_video_path)
    frame = base.get_frame(0)
    img = Image.fromarray(frame).filter(ImageFilter.GaussianBlur(radius=12))

    font_main = get_font(FONT_PATH, size=max(48, img.size[0] // 13))
    font_job  = get_font(FONT_PATH, size=max(96, img.size[0] // 10))

    img = _draw_center_text(img, job, font_main, font_job)

    intro_clip = ImageClip(np.array(img)).with_duration(intro_sec).with_fps(base.fps)
    base.close()
    return intro_clip

def overlay_top_caption(clip, caption: str):
    font = get_font(FONT_PATH, size=max(54, int(clip.w / 12)))

    def _fn(frame):
        img = Image.fromarray(frame)
        img = _draw_top_label(img, caption, font)
        return np.array(img)

    return clip.image_transform(_fn)

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_path", type=str, default="./data")
    parser.add_argument("--output_path", type=str, default="./output")
    parser.add_argument("--concept", type=str, default="animal_with_job")
    parser.add_argument("--category", type=str, default=None)
    args = parser.parse_args()

    os.makedirs(args.output_path, exist_ok=True)

    # API setting
    api_path = f"{args.data_path}/keys.json"

    with open(api_path, "r", encoding="utf-8") as f:
        keys = json.load(f)

    if "OPENAI_API_KEY" not in keys:
        raise RuntimeError("OPENAI_API_KEY is missing in keys.json")
    if "REPLICATE_API_TOKEN" not in keys:
        raise RuntimeError("REPLICATE_API_TOKEN is missing in keys.json")
    if "SUNO_API_KEY" not in keys:
        raise RuntimeError("SUNO_API_KEY is missing in keys.json")

    os.environ["OPENAI_API_KEY"] = keys["OPENAI_API_KEY"]
    os.environ["REPLICATE_API_TOKEN"] = keys["REPLICATE_API_TOKEN"]
    os.environ["SUNO_API_KEY"] = keys["SUNO_API_KEY"]
    openai_client = OpenAI()

    print("Environment variables set:")
    print("OPENAI_API_KEY =", "SET" if "OPENAI_API_KEY" in os.environ else "MISSING")
    print("REPLICATE_API_TOKEN =", "SET" if "REPLICATE_API_TOKEN" in os.environ else "MISSING")

    # Prompt check + generation
    data_path = f"{args.data_path}/{args.concept}.json"
    if not os.path.exists(data_path):
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4, ensure_ascii=False)
        data = {}
    else:
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    unused_pairs = find_unused_pair(data)

    if not unused_pairs:
        create_data(openai_client, data)
        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        unused_pairs = find_unused_pair(data)

    # Image generation
    video_paths = []
    if args.category is not None:
        job, animals = args.category.replace('_', ' '), None
        for _job, _animals in unused_pairs:
            if job == _job:
                animals = _animals
                break
        if animals is None:
            raise RuntimeError(f"'{job}' does not exist in unused pair.")
    else:
        job, animals = random.choice(unused_pairs)
    
    job_s = sanitize_file_name(job)
    output_path = os.path.join(args.output_path, job_s)
    os.makedirs(output_path, exist_ok=True)
    
    for animal in animals:
        animal_s =  sanitize_file_name(animal)
        image_path = os.path.join(output_path, f"{job_s}_{animal_s}.jpg")
        if not os.path.exists(image_path):
            generate_image(job, animal, image_path)

        video_path = os.path.join(output_path, f"{job_s}_{animal_s}.mp4")
        if not os.path.exists(video_path):
            generate_video(job, animal, image_path, video_path)
        video_paths.append(video_path)
        
    intro_clip = make_intro(video_paths[0], job, intro_sec=1.0)

    animal_clips = []
    for idx, (animal, vp) in enumerate(zip(animals, video_paths), start=1):
        c = VideoFileClip(vp)
        c = overlay_top_caption(c, f"{idx}. {animal.title()}")
        animal_clips.append(c)

    final = concatenate_videoclips([intro_clip] + animal_clips, method="compose")

    bgm_path = os.path.join(output_path, f"{job_s}_bgm.mp3")
    if not os.path.exists(bgm_path):
        generate_bgm(
            job=job,
            duration=int(final.duration),
            audio_path=bgm_path,
        )
        time.sleep(2.0)
    audio = AudioFileClip(bgm_path)
    audio = loop_or_trim_audio_to_duration(audio, final.duration + 0.2).subclipped(0, final.duration)
    final = final.with_audio(audio)

    final_path = os.path.join(output_path, f"{job_s}_final.mp4")
    final.write_videofile(
        final_path,
        codec="libx264",
        audio_codec="aac",
        fps=24,
        audio=True,
        preset="medium",
        threads=4,
    )

    audio.close()
    final.close()
    for c in animal_clips:
        c.close()

    print(f"[DONE] video saved to: {final_path}")
