import os
import json

def save_credentials():
    token = input("Enter your Facebook Access Token: ").strip()
    page_id = input("Enter your Facebook Page ID: ").strip()

    data = {
        "access_token": token,
        "page_id": page_id
    }

    os.makedirs("credentials", exist_ok=True)
    with open("credentials/fb_credentials.json", "w") as f:
        json.dump(data, f, indent=4)

    print("\n✅ Credentials saved successfully to credentials/fb_credentials.json")

if __name__ == "__main__":
    save_credentials()
