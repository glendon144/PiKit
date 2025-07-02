import openai
import os
from modules.logger import Logger

class AIInterface:
    def __init__(self, logger=None):
        self.api_key = None
        self.logger = logger if logger else Logger()
        self.load_api_key_from_file()

    def load_api_key_from_file(self):
        """Try to load API key from ~/openai_key"""
        key_path = os.path.expanduser("~/openai_key")
        if os.path.exists(key_path):
            with open(key_path, "r") as f:
                self.api_key = f.read().strip()
            openai.api_key = self.api_key
            self.logger.info("API key loaded from file.")
        else:
            self.logger.info("API key file not found. Prompting user instead.")

    def set_api_key(self, key):
        self.api_key = key
        openai.api_key = key
        self.logger.info("API key successfully set")

    def get_api_key(self):
        return self.api_key

    def query(self, prompt):
        if not self.api_key:
            raise Exception("API key not set.")
        try:
            self.logger.debug(f"Querying OpenAI with prompt: {prompt}")
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            reply = response["choices"][0]["message"]["content"]
            self.logger.debug("AI Query successful")
            return reply
        except Exception as e:
            self.logger.error(f"OpenAI API call failed: {e}")
            raise

