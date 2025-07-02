import json
import os

class FacebookCredentials:
    def __init__(self, filename="credentials/fb_credentials.json"):
        self.filename = filename
        self.token = None
        self.page_id = None
        self.load_credentials()

    def save_credentials(self, token, page_id):
        self.token = token
        self.page_id = page_id
        data = {"access_token": token, "page_id": page_id}
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        with open(self.filename, "w") as f:
            json.dump(data, f)

    def load_credentials(self):
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                data = json.load(f)
                self.token = data.get("access_token")
                self.page_id = data.get("page_id")

    def is_configured(self):
        return self.token is not None and self.page_id is not None
