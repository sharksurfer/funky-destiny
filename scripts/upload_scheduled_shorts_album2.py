#!/usr/bin/env python3
import os
import sys
import glob
import json
import time
import datetime
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

PROJECTS_DIR = Path("projects/album-2")
SHORTS_DIR = PROJECTS_DIR / "shorts"
MANIFEST_PATH = SHORTS_DIR / "shorts_manifest.json"
UPLOAD_LOG = SHORTS_DIR / "upload_log.json"

# Schedule: 1 day yes, 1 day no (interval of 2 days between releases)
# Base time: Tomorrow at 15:00 UTC (12:00 BRT - lunch peak)
DAYS_INTERVAL = 2

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

    # Base schedule date: Tomorrow at 15:00 UTC
    now_utc = datetime.datetime.utcnow()
    # Start tomorrow at 15:00 UTC (12:00 BRT)
    base_date = (now_utc + datetime.timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)

    slug_list = list(manifest.keys())
    print(f"Preparing to upload & schedule {len(slug_list)} shorts with {DAYS_INTERVAL} days interval (1 day on, 1 day off)...")

    for idx, slug in enumerate(slug_list):
        info = manifest[slug]
        short_path = info.get("short_path")
        if not short_path or not os.path.exists(short_path):
            print(f"File missing for {slug}: {short_path}")
            continue
            
        if slug in upload_results and upload_results[slug].get("video_id"):
            print(f"[Already Uploaded] {slug}: https://youtu.be/{upload_results[slug]['video_id']} (Scheduled for: {upload_results[slug].get('scheduled_for')})")
            continue

        # Calculate release date for this video
        release_dt = base_date + datetime.timedelta(days=idx * DAYS_INTERVAL)
        publish_at_iso = release_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        track_title = info.get("title", slug.replace("-", " ").title())
        print(f"\n[{idx+1}/{len(slug_list)}] Uploading & Scheduling: {track_title} ({slug})")
        print(f"  📅 Scheduled release: {publish_at_iso} ({release_dt.strftime('%d/%m/%Y %H:%M UTC')})")

        body = {
            'snippet': {
                'title': f"{track_title} ⚡ Funky Bass Solo #shorts",
                'description': f"Melhor momento de '{track_title}' do Álbum 2 (Funky Destiny)! 🎸🔥\n\nAssista ao clipe completo e ouça o álbum no canal.\n\n#shorts #bass #funk #slapbass #groove #funkydestiny #heavybass",
                'tags': ['shorts', 'bass', 'funk', 'slap bass', 'groove', 'funky destiny', 'bass solo', 'album 2', track_title.lower()],
                'categoryId': '10'
            },
            'status': {
                'privacyStatus': 'private',
                'publishAt': publish_at_iso,
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
            print(f"  ✅ Uploaded & Scheduled! Video ID: {video_id} -> https://youtu.be/{video_id}")
            
            upload_results[slug] = {
                "video_id": video_id,
                "url": f"https://youtu.be/{video_id}",
                "title": body['snippet']['title'],
                "status": "scheduled",
                "scheduled_for": publish_at_iso,
                "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            UPLOAD_LOG.write_text(json.dumps(upload_results, indent=2, ensure_ascii=False), encoding="utf-8")
            time.sleep(2)
        except Exception as e:
            print(f"  ❌ Error uploading {slug}: {e}")
            break

if __name__ == "__main__":
    main()
