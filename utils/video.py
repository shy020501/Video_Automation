import numpy as np
import replicate
from PIL import Image, ImageFilter, ImageDraw, ImageFont
from moviepy import VideoFileClip, ImageClip

from utils.utils import get_font

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

FONT_PATH = "./data/fonts/PlayfairDisplay-VariableFont_wght.ttf"

def generate_image(job: str, animal: str, image_path: str):
    prompt = IMAGE_PROMPT.format(job=job, animal=animal)

    print(f"[Seedream-4] Creating image of {animal}")

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

    print(f"[Seedance-1-pro-fast] Creating video of {animal}")
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