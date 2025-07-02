import requests

def fetch_page_feed(page_id, page_access_token, limit=10):
    url = f"https://graph.facebook.com/v17.0/{page_id}/feed"
    params = {
        "access_token": page_access_token,
        "limit": limit
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        posts = data.get("data", [])
        print(f"\nLast {limit} posts on Page {page_id}:")
        for post in posts:
            print(f"- Post ID: {post['id']}")
            if 'message' in post:
                print(f"  Message: {post['message'][:100]}")
            else:
                print("  (No message content)")
    else:
        print("Error fetching feed:", response.text)

if __name__ == "__main__":
    print("DemoKit Post Verification Helper")
    page_id = input("Enter your Facebook Page ID: ").strip()
    page_access_token = input("Enter your Facebook Page Access Token: ").strip()
    fetch_page_feed(page_id, page_access_token)
