import openai
import os
from modules.logger import Logger

class AIInterface:
    def __init__(self, logger=None):
        self.api_key = None
        self.logger = logger if logger else Logger()
        self.load_api_key_from_file()

    def load_api_key_from_file(self):
        """
        Try to load API key from common key files:
          - ~/openai_key
          - ~/openai.key
          - /home/<user>/openai.key (expanduser)
        """
        possible_paths = [
            os.path.expanduser("~/openai_key"),
            os.path.expanduser("~/openai.key")
        ]
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, "r") as f:
                    self.api_key = f.read().strip()
                openai.api_key = self.api_key
                self.logger.info(f"API key loaded from file: {path}")
                return

        # If not found yet, log and defer to manual input
        self.logger.info("No API key file found. You can import it via the GUI or set via set_api_key().")

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
