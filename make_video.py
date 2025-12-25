import os
import json
import argparse
import random
import time
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips
from openai import OpenAI

from utils.utils import sanitize_file_name, find_unused_pair
from utils.bgm import generate_bgm, loop_or_trim_audio_to_duration
from utils.video import generate_image, generate_video, make_intro, overlay_top_caption
from utils.upload import upload_to_youtube

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

    title = f"What it ____ was a {job}"
    description = f"AI-generated animal {job}"

    video_id = upload_to_youtube(
        file_path=final_path,
        title=title,
        description=description,
        tags=["ai", "animals", "shorts", job],
        # privacy_status="public",
        privacy_status="private",
    )
    print(f"[Youtube] Uploaded: {video_id}")

    # data[job]["used"] = True
    # with open(data_path, "w", encoding="utf-8") as f:
    #     json.dump(data, f, indent=4, ensure_ascii=False)
