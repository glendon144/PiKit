import os
import json
import requests

class CredentialsSimplifier:

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
                print(f"  Page Access Token: {page['access_token']}")
                # Offer live injection
                save = input(f"Save this Page Access Token for {page['name']}? (y/n): ").strip().lower()
                if save == 'y':
                    self.save_fb_credentials(page['access_token'], page['id'])
        else:
            print("Error fetching pages:", response.text)

def menu():
    mgr = CredentialsSimplifier()

    while True:
        print("\n=== DemoKit Credential Flow Simplifier ===")
        print("1) Exchange User Token for Page Tokens")
        print("2) Quit")
        choice = input("Select an option: ").strip()

        if choice == "1":
            user_token = input("Enter User Access Token: ").strip()
            mgr.exchange_for_page_tokens(user_token)
        elif choice == "2":
            break
        else:
            print("Invalid selection.")

if __name__ == "__main__":
    menu()
