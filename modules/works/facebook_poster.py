import requests

class FacebookPoster:
    def __init__(self, credentials):
        self.credentials = credentials

    def post(self, message):
        if not self.credentials.is_configured():
            print("Facebook credentials not configured.")
            return False

        url = f"https://graph.facebook.com/{self.credentials.page_id}/feed"
        payload = {
            "message": message,
            "access_token": self.credentials.token
        }

        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("Successfully posted to Facebook!")
            return True
        else:
            print("Failed to post. Response:", response.text)
            return False
