import os
import json
import argparse
import random
import re
from openai import OpenAI
import replicate

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

def sanitize_file_name(output_path, job, animal, extension):
    def slug(s):
        s = s.strip().lower()
        s = re.sub(r"\s+", "_", s)
        s = re.sub(r"[^a-z0-9_]+", "", s)
        return s
    job_s = slug(job)
    animal_s = slug(animal)
    image_path = os.path.join(output_path, job_s)
    os.makedirs(image_path, exist_ok=True)
    return os.path.join(image_path, f"{job_s}_{animal_s}.{extension}")

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

def generate_image(job, animal, image_path):
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

def generate_video(job, animal, image_path, video_path):
    prompt = VIDEO_PROMPT.format(job=job, animal=animal)
    image = open(image_path, "rb")

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_path", type=str, default="./data")
    parser.add_argument("--output_path", type=str, default="./output")
    parser.add_argument("--concept", type=str, default="animal_with_job")
    args = parser.parse_args()

    os.makedirs(args.output_path, exist_ok=True)

    # API setting $9.49
    api_path = f"{args.data_path}/keys.json"

    with open(api_path, "r", encoding="utf-8") as f:
        keys = json.load(f)

    if "OPENAI_API_KEY" not in keys:
        raise RuntimeError("OPENAI_API_KEY is missing in keys.json")
    if "REPLICATE_API_TOKEN" not in keys:
        raise RuntimeError("REPLICATE_API_TOKEN is missing in keys.json")

    os.environ["OPENAI_API_KEY"] = keys["OPENAI_API_KEY"]
    os.environ["REPLICATE_API_TOKEN"] = keys["REPLICATE_API_TOKEN"]
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
    job, animals = random.choice(unused_pairs)
    
    # For debugging
    job = "chef"
    animals = ["pig", "rabbit", "chicken", "cow"]
    
    for animal in animals:
        image_path = sanitize_file_name(args.output_path, job, animal, "jpg")
        if not os.path.exists(image_path):
            generate_image(job, animal, image_path)

        video_path = sanitize_file_name(args.output_path, job, animal, "mp4")
        if not os.path.exists(video_path):
            generate_video(job, animal, image_path, video_path)
        video_paths.append(video_path)
        

