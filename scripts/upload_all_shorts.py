#!/usr/bin/env python3
import os
import sys
import glob
import json
import time
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

PROJECTS_DIR = Path("projects/album-1")
SHORTS_DIR = PROJECTS_DIR / "shorts"
MANIFEST_PATH = SHORTS_DIR / "shorts_manifest.json"
UPLOAD_LOG = SHORTS_DIR / "upload_log.json"

def get_youtube_client():
    token_path = Path("token.json")
    if not token_path.exists():
        raise FileNotFoundError("token.json not found!")
    with open(token_path) as f:
        data = json.load(f)
    creds = Credentials.from_authorized_user_info(data)
    if creds.expired:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

def main():
    if not MANIFEST_PATH.exists():
        print("Manifest not found. Run render first.")
        return

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    
    upload_results = {}
    if UPLOAD_LOG.exists():
        try:
            upload_results = json.loads(UPLOAD_LOG.read_text(encoding="utf-8"))
        except Exception:
            upload_results = {}

    youtube = get_youtube_client()
    print("Connected to YouTube API successfully.")

    for slug, info in manifest.items():
        short_path = info.get("short_path")
        if not short_path or not os.path.exists(short_path):
            continue
            
        if slug in upload_results and upload_results[slug].get("video_id"):
            print(f"[Already Uploaded] {slug}: https://youtu.be/{upload_results[slug]['video_id']}")
            continue
            
        title_file = PROJECTS_DIR / f"single-{slug}" / "artifacts" / "title.txt"
        if title_file.exists():
            track_title = title_file.read_text(encoding="utf-8").strip()
        else:
            track_title = slug.replace("-", " ").title()
            
        print(f"\n[Uploading] {track_title} ({slug})...")
        body = {
            'snippet': {
                'title': f"{track_title} ⚡ Funky Bass Solo #shorts",
                'description': f"Melhor momento de '{track_title}' do canal Funky Destiny! 🎸🔥\n\nAssista ao clipe completo e ouça o álbum completo no canal.\n\n#shorts #bass #funk #slapbass #groove #funkydestiny #bassguitar",
                'tags': ['shorts', 'bass', 'funk', 'slap bass', 'groove', 'funky destiny', 'bass solo', track_title.lower()],
                'categoryId': '10'
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False
            }
        }
        
        try:
            media = MediaFileUpload(short_path, mimetype='video/mp4', resumable=True)
            request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"  Uploaded {int(status.progress() * 100)}%...")
            video_id = response.get('id')
            print(f"  ✅ Uploaded successfully! Video ID: {video_id} -> https://youtu.be/{video_id}")
            
            upload_results[slug] = {
                "video_id": video_id,
                "url": f"https://youtu.be/{video_id}",
                "title": body['snippet']['title'],
                "status": "public",
                "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            UPLOAD_LOG.write_text(json.dumps(upload_results, indent=2, ensure_ascii=False), encoding="utf-8")
            time.sleep(2) # rate limit pause
        except Exception as e:
            print(f"  ❌ Error uploading {slug}: {e}")
            break

if __name__ == "__main__":
    main()
