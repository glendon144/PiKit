import os
import json
import requests

class CredentialsManager:

    def __init__(self):
        os.makedirs("credentials", exist_ok=True)
        self.fb_credentials_path = "credentials/fb_credentials.json"

    def save_fb_credentials(self, token, page_id):
        data = {
            "access_token": token,
            "page_id": page_id
        }
        with open(self.fb_credentials_path, "w") as f:
            json.dump(data, f, indent=4)
        print("\n✅ Facebook credentials saved successfully.")

    def validate_token(self, app_id, app_secret, user_token):
        debug_url = "https://graph.facebook.com/debug_token"
        params = {
            "input_token": user_token,
            "access_token": f"{app_id}|{app_secret}"
        }
        response = requests.get(debug_url, params=params)
        if response.status_code == 200:
            data = response.json()
            print("\nToken Validation Result:")
            print("App ID:", data['data'].get('app_id'))
            print("Type:", data['data'].get('type'))
            print("Expires at:", data['data'].get('expires_at'))
            print("Permissions:")
            for perm in data['data'].get('scopes', []):
                print(" -", perm)
        else:
            print("Error:", response.text)

    def exchange_for_page_tokens(self, user_token):
        url = "https://graph.facebook.com/v17.0/me/accounts"
        params = {
            "access_token": user_token
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            pages = data.get("data", [])
            print("\nYour Pages and Page Access Tokens:")
            for page in pages:
                print(f"- {page['name']}")
                print(f"  Page ID: {page['id']}")
                print(f"  Page Access Token: {page['access_token']}\n")
        else:
            print("Error:", response.text)

def menu():
    mgr = CredentialsManager()

    while True:
        print("\n=== DemoKit Credentials Manager ===")
        print("1) Save Facebook Credentials")
        print("2) Validate User Token")
        print("3) Exchange User Token for Page Tokens")
        print("4) Quit")
        choice = input("Select an option: ").strip()

        if choice == "1":
            token = input("Enter Facebook Page Access Token: ").strip()
            page_id = input("Enter Facebook Page ID: ").strip()
            mgr.save_fb_credentials(token, page_id)
        elif choice == "2":
            app_id = input("Enter Facebook App ID: ").strip()
            app_secret = input("Enter Facebook App Secret: ").strip()
            user_token = input("Enter User Access Token: ").strip()
            mgr.validate_token(app_id, app_secret, user_token)
        elif choice == "3":
            user_token = input("Enter User Access Token: ").strip()
            mgr.exchange_for_page_tokens(user_token)
        elif choice == "4":
            break
        else:
            print("Invalid selection.")

if __name__ == "__main__":
    menu()
