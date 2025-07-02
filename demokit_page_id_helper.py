import requests

def get_page_ids(access_token):
    url = "https://graph.facebook.com/v17.0/me/accounts"
    params = {
        "access_token": access_token
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        pages = data.get("data", [])
        print("\nYour Facebook Pages:")
        for page in pages:
            print(f"- {page['name']}: {page['id']}")
    else:
        print("Error fetching pages:", response.text)

if __name__ == "__main__":
    print("DemoKit Facebook Page ID Helper")
    token = input("Enter your Facebook Access Token: ").strip()
    get_page_ids(token)
