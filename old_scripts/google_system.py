import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.oauthlib import flow
from googleapiclient.discovery import build
import pandas as pd

def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/drive'])
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("No valid credentials found. Please follow the instructions to generate credentials.")
            flow = flow.InstalledAppFlow.from_client_secrets_file(
                'credentials.json', ['https://www.googleapis.com/auth/drive'])
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def get_drive_service(creds):
    return build('drive', 'v3', credentials=creds)

def download_files_from_folder(drive_service, folder_id, download_path):
    query = f"'{folder_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query).execute()
    files = results.get('files', [])
    for file in files:
        file_id = file['id']
        file_name = file['name']
        request = drive_service.files().get_media(fileId=file_id)
        file_path = f"{download_path}/{file_name}"
        with open(file_path, 'wb') as f:
            f.write(request.execute())
        print(f"Downloaded {file_name} to {file_path}")

def process_files(local_path):
    # Your processing logic here
    for file in os.listdir(local_path):
        if file.endswith('.csv'):
            df = pd.read_csv(os.path.join(local_path, file))
            # Process your data here
            print(df.head())

if __name__ == "__main__":
    credentials_path = input("Enter the path to your credentials.json file: ")
    if not os.path.exists('credentials.json'):
        print("Credentials file not found. Please download it from the Google Cloud Console and save it as 'credentials.json' in the same directory as this script.")
    else:
        creds = get_credentials()
        drive_service = get_drive_service(creds)
        
        folder_id = input("Enter Google Drive folder ID: ")
        download_path = './downloads'
        os.makedirs(download_path, exist_ok=True)

        download_files_from_folder(drive_service, folder_id, download_path)
        process_files(download_path)
