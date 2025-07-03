import os
import openai
from modules.logger import Logger


class AIInterface:
    KEY_PATH = os.path.expanduser("~/openai.key")

    def __init__(self, logger=None):
        self.logger = logger or Logger()
        self.api_key = None
        if os.path.exists(self.KEY_PATH):
            self.set_api_key(open(self.KEY_PATH).read().strip())

    def set_api_key(self, key: str):
        self.api_key = key.strip()
        openai.api_key = self.api_key
        self.logger.info("OpenAI API key set.")

    def query(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("OpenAI API key not set")
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            reply = resp["choices"][0]["message"]["content"].strip()
            self.logger.info(f"AI reply received ({len(reply)} chars)")
            return reply
        except Exception as exc:
            self.logger.error(f"OpenAI error: {exc}")
            raise
