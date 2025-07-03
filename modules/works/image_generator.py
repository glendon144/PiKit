import io
import requests
import openai
from PIL import Image

def generate_image(prompt: str, size: str = "512x512"):
    """Generate a DALL·E image and return as PIL.Image."""
    resp = openai.Image.create(prompt=prompt, n=1, size=size)
    url = resp["data"][0]["url"]
    img_bytes = requests.get(url, timeout=20).content
    return Image.open(io.BytesIO(img_bytes))
