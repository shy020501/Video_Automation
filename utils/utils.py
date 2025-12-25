from PIL import ImageFont
import re

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