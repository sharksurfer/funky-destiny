#!/usr/bin/env python3
"""YouTube automated uploader with SEO best practices and thumbnail upload.

Features:
- Authenticates via OAuth 2.0 (using client_secret.json and saves session token.json).
- Supports single video upload or batch upload of all 24 singles.
- Supports 1h+ compilation mix upload with YouTube chapters automatically embedded in description.
- Automatically pairs and uploads corresponding custom high-CTR thumbnail (-thumb.jpg).
- Built-in SEO metadata optimization:
    * Title with strong CTR hook and channel branding
    * First 150 chars optimized description for search intent
    * Musical genre tags & keywords
    * Category 10 (Music)
    * Configurable privacy status (private, unlisted, public)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CHANNEL_NAME, PROJECTS, REPO, load_masters

CLIENT_SECRET_FILE = REPO / "client_secret.json"
TOKEN_FILE = REPO / "token.json"
# Allow oauthlib scope modifications by Google without raising an exception
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
]


def get_authenticated_service():
    """Authenticate and return Google YouTube Resource."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        sys.exit(
            "[youtube] Missing dependencies. Run: pip3 install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        )

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception as e:
            print(f"[youtube] Existing token invalid, re-authenticating: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                sys.exit(
                    f"\n[youtube] ERROR: '{CLIENT_SECRET_FILE.name}' not found in repo root!\n"
                    f"Please download your OAuth client credentials JSON from Google Cloud Console,\n"
                    f"save it as '{CLIENT_SECRET_FILE}' and run again.\n"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())
        print(f"[youtube] Session token saved to {TOKEN_FILE}")

    return build("youtube", "v3", credentials=creds)


def generate_seo_metadata(title: str, tag: str, is_mix: bool = False, chapters_text: str = "") -> dict:
    """Generate high-performing YouTube SEO title, description, and tags."""
    clean_tag = tag.strip().lower() if tag else "funk"

    if is_mix:
        album_title = "KNUCKLE POP OVERDRIVE"
        seo_title = f"{album_title} - 1 Hour Heavy Bass Mix | {CHANNEL_NAME} (Official Album)"
        seo_desc = (
            f"⚡ '{album_title}' — 1 Hour of relentless heavy bass grooves, aggressive slap solos, and cyberpunk funk rhythms by {CHANNEL_NAME}.\n"
            f"Perfect for coding, workout, driving, gaming, and pure bass enthusiasts.\n\n"
            f"🎵 TRACKLIST & CHAPTERS:\n{chapters_text}\n\n"
            f"🔥 ABOUT {CHANNEL_NAME}:\n"
            f"Original instrumental funk, driving synth-bass, and punchy rhythmic slap bass compositions.\n\n"
            f"#KnucklePopOverdrive #FunkMusic #BassGuitar #SlapBass #FunkyDestiny #1HourMix #Groove #BassMix"
        )
        seo_tags = [
            "knuckle pop overdrive", "1 hour bass mix", "heavy bass", "slap bass mix", "funk instrumental",
            "bass groove", "funky destiny", "cyberpunk funk", "bass backing track",
            "workout bass music", "instrumental funk mix", "bass solos", "groove music"
        ]
    else:
        # Single track
        style_desc = {
            "heavybass": "Heavy Bass Groove",
            "guitarboy": "Electric Guitar & Slap Bass",
            "smoothbass": "Smooth Neon Bassline",
            "pianobass": "Moody Keys & Heavy Bass",
            "mediumbass": "Classic Funk Groove",
        }.get(clean_tag, "Heavy Bass Groove")

        seo_title = f"{title} - {style_desc} | {CHANNEL_NAME} (Official Audio)"
        seo_desc = (
            f"Listen to '{title}' by {CHANNEL_NAME} — {style_desc}.\n\n"
            f"Bass-heavy instrumental funk featuring punchy slap grooves, electric rhythmic drive, and cyberpunk aesthetic.\n\n"
            f"🎧 Artist: {CHANNEL_NAME}\n"
            f"🎵 Track: {title}\n"
            f"⚡ Style: {style_desc}\n\n"
            f"Subscribe to {CHANNEL_NAME} for weekly heavy bass grooves and instrumental funk releases.\n\n"
            f"#{title.replace(' ', '')} #FunkMusic #BassGroove #SlapBass #{CHANNEL_NAME.replace(' ', '')}"
        )
        seo_tags = [
            title.lower(), f"{title.lower()} bass", CHANNEL_NAME.lower(), "funk instrumental",
            "slap bass", "bass groove", "heavy bass", "funk bass solo", "bassline",
            clean_tag, "instrumental music"
        ]

    return {
        "title": seo_title[:100],  # YouTube title limit 100 chars
        "description": seo_desc,
        "tags": seo_tags,
        "categoryId": "10",  # Music category
    }


def upload_video(
    youtube,
    video_path: Path,
    thumb_path: Path | None,
    title: str,
    tag: str = "",
    privacy_status: str = "private",
    is_mix: bool = False,
    chapters_text: str = "",
) -> str | None:
    """Upload video and thumbnail using resumable upload protocol."""
    from googleapiclient.http import MediaFileUpload

    metadata = generate_seo_metadata(title, tag, is_mix=is_mix, chapters_text=chapters_text)

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": metadata["categoryId"],
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"\n[youtube] Uploading: '{video_path.name}' ({video_path.stat().st_size / (1024*1024):.1f} MB)")
    print(f"[youtube] Title: {metadata['title']}")
    print(f"[youtube] Privacy: {privacy_status}")

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=1024 * 1024 * 10)
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    retry_count = 0
    max_retries = 10
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"[youtube] Upload progress: {int(status.progress() * 100)}%")
            retry_count = 0  # reset on successful chunk
        except Exception as err:
            retry_count += 1
            if retry_count > max_retries:
                raise err
            wait_time = min(2 ** retry_count, 60)
            print(f"[youtube] Transient network timeout/error ({err}). Retrying in {wait_time}s... ({retry_count}/{max_retries})")
            time.sleep(wait_time)

    video_id = response.get("id")
    print(f"[youtube] SUCCESS! Video ID: {video_id} -> https://youtu.be/{video_id}")

    # Record to local ledger for automatic tracking and thumbnail sync
    try:
        ledger_file = PROJECTS / "uploads_ledger.json"
        ledger = {}
        if ledger_file.exists():
            ledger = json.loads(ledger_file.read_text())
        ledger[metadata["title"]] = {
            "video_id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "is_mix": is_mix,
            "tag": tag,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        ledger_file.write_text(json.dumps(ledger, indent=2, ensure_ascii=False))
    except Exception as err:
        print(f"[youtube] Warning: could not write to ledger: {err}")

    # Upload custom thumbnail if available
    if thumb_path and Path(thumb_path).exists():
        print(f"[youtube] Setting custom thumbnail: {thumb_path.name}...")
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
            ).execute()
            print("[youtube] Thumbnail uploaded successfully!")
        except Exception as e:
            print(f"[youtube] Warning: Failed to set thumbnail: {e}")

    return video_id



def upload_single_song(youtube, song_slug: str, privacy: str = "private") -> str | None:
    masters = load_masters()
    track = next((t for t in masters if t["slug"] == song_slug), None)
    if not track:
        sys.exit(f"[youtube] Unknown song slug: {song_slug}")

    proj = PROJECTS / f"single-{track['slug']}"
    video_file = proj / "renders" / f"{track['slug']}.mp4"
    thumb_file = proj / "renders" / f"{track['slug']}-thumb.jpg"

    if not video_file.exists():
        sys.exit(f"[youtube] Video file not found: {video_file}. Run render_single.py first!")

    return upload_video(
        youtube=youtube,
        video_path=video_file,
        thumb_path=thumb_file if thumb_file.exists() else None,
        title=track["title"],
        tag=track.get("tag", ""),
        privacy_status=privacy,
        is_mix=False,
    )


def upload_compilation_mix(youtube, project_name: str, privacy: str = "private") -> str | None:
    proj = PROJECTS / project_name
    video_file = proj / "renders" / f"{project_name}.mp4"
    thumb_file = proj / "renders" / f"{project_name}-thumb.jpg"
    chapters_file = proj / "artifacts" / "chapters.txt"

    if not video_file.exists():
        sys.exit(f"[youtube] Mix video not found: {video_file}. Run build_mix.py first!")

    chapters_content = chapters_file.read_text() if chapters_file.exists() else ""

    return upload_video(
        youtube=youtube,
        video_path=video_file,
        thumb_path=thumb_file if thumb_file.exists() else None,
        title="1 HOUR BASS MIX",
        tag="heavybass",
        privacy_status=privacy,
        is_mix=True,
        chapters_text=chapters_content,
    )


def update_thumbnail_for_video(youtube, video_id: str, thumb_path: Path) -> bool:
    """Update custom thumbnail for an existing uploaded video."""
    if not thumb_path.exists():
        print(f"[youtube] Thumbnail not found: {thumb_path}")
        return False
    try:
        from googleapiclient.http import MediaFileUpload
        print(f"[youtube] Updating thumbnail for video {video_id} with {thumb_path.name}...")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
        ).execute()
        print(f"[youtube] Thumbnail updated successfully for {video_id}!")
        return True
    except Exception as e:
        print(f"[youtube] Failed to update thumbnail: {e}")
        return False


def sync_all_channel_thumbnails(youtube) -> None:
    """Update thumbnails for all uploaded channel videos using ledger and/or channel listings."""
    from common import load_masters
    masters = load_masters()
    success_count = 0

    ledger_file = PROJECTS / "uploads_ledger.json"
    if ledger_file.exists():
        try:
            ledger = json.loads(ledger_file.read_text())
            print(f"[youtube] Found {len(ledger)} tracked videos in {ledger_file.name}:")
            for video_title, info in ledger.items():
                vid_id = info.get("video_id")
                if not vid_id:
                    continue
                thumb_to_upload = None
                if info.get("is_mix"):
                    cand = PROJECTS / "funky-destiny-1hour-bass-mix" / "renders" / "funky-destiny-1hour-bass-mix-thumb.jpg"
                    if cand.exists():
                        thumb_to_upload = cand
                else:
                    for m in masters:
                        if m["title"].upper() in video_title.upper():
                            cand = PROJECTS / f"single-{m['slug']}" / "renders" / f"{m['slug']}-thumb.jpg"
                            if cand.exists():
                                thumb_to_upload = cand
                                break
                if thumb_to_upload:
                    print(f"\n[youtube] Updating '{video_title}' ({vid_id}) -> {thumb_to_upload.name}")
                    ok = update_thumbnail_for_video(youtube, vid_id, thumb_to_upload)
                    if ok:
                        success_count += 1
                    time.sleep(2)
            print(f"\n[youtube] Sync complete via ledger! Updated {success_count} thumbnails.")
            return
        except Exception as e:
            print(f"[youtube] Error reading ledger: {e}")

    # Fallback to playlistItems if read scopes are granted
    try:
        print("[youtube] Fetching list of uploaded videos from YouTube channel playlist...")
        channels_response = youtube.channels().list(mine=True, part="contentDetails").execute()
        uploads_playlist_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        videos = []
        next_page_token = None
        while True:
            res = youtube.playlistItems().list(
                playlistId=uploads_playlist_id,
                part="snippet",
                maxResults=50,
                pageToken=next_page_token
            ).execute()
            for item in res.get("items", []):
                videos.append({
                    "id": item["snippet"]["resourceId"]["videoId"],
                    "title": item["snippet"]["title"]
                })
            next_page_token = res.get("nextPageToken")
            if not next_page_token:
                break

        print(f"[youtube] Found {len(videos)} videos on channel.")
        for v in videos:
            vid_id = v["id"]
            v_title = v["title"].upper()
            thumb_to_upload = None

            if "1 HOUR" in v_title or "COMPILATION" in v_title or "BASS MIX" in v_title:
                cand = PROJECTS / "funky-destiny-1hour-bass-mix" / "renders" / "funky-destiny-1hour-bass-mix-thumb.jpg"
                if cand.exists():
                    thumb_to_upload = cand
            else:
                for m in masters:
                    if m["title"].upper() in v_title:
                        cand = PROJECTS / f"single-{m['slug']}" / "renders" / f"{m['slug']}-thumb.jpg"
                        if cand.exists():
                            thumb_to_upload = cand
                            break

            if thumb_to_upload:
                print(f"\n[youtube] Matching '{v['title']}' -> {thumb_to_upload.name}")
                ok = update_thumbnail_for_video(youtube, vid_id, thumb_to_upload)
                if ok:
                    success_count += 1
                time.sleep(2)

        print(f"\n[youtube] Complete! Updated {success_count} thumbnails on YouTube.")
    except Exception as err:
        print(f"[youtube] Could not list channel videos: {err}")
        print("[youtube] Tip: Use --update-thumbnail <VIDEO_ID> <PATH_TO_JPG> to update specific videos directly.")



def schedule_video_publication(youtube, video_id: str, publish_at_iso: str) -> bool:
    """Schedule a private video to become public at a specific ISO 8601 UTC timestamp."""
    try:
        body = {
            "id": video_id,
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at_iso,
                "selfDeclaredMadeForKids": False
            }
        }
        res = youtube.videos().update(part="status", body=body).execute()
        print(f"[youtube] Video {video_id} scheduled for: {publish_at_iso}")
        return True
    except Exception as e:
        print(f"[youtube] Failed to schedule video {video_id}: {e}")
        return False


def schedule_album_campaign(youtube) -> None:
    """Schedule all 12 singles and the album mix according to the optimal release calendar."""
    from common import load_masters
    masters = load_masters()
    ledger_file = PROJECTS / "uploads_ledger.json"
    if not ledger_file.exists():
        sys.exit(f"[youtube] Ledger file not found at {ledger_file}")

    ledger = json.loads(ledger_file.read_text())

    # Release calendar: 3 singles per week (Mon/Wed/Fri at 15:00 UTC = 12:00 Brasilia)
    # Followed by Album mix on Fri Dec 04 at 20:00 UTC = 17:00 Brasilia
    schedule_plan = [
        ("knuckle-pop-overdrive", "2026-11-06T15:00:00Z"),
        ("asphalt-bass-shakedown", "2026-11-09T15:00:00Z"),
        ("concrete-thumb-riot", "2026-11-11T15:00:00Z"),
        ("curbside-low-end-theory", "2026-11-13T15:00:00Z"),
        ("gutter-funk-resurrection", "2026-11-16T15:00:00Z"),
        ("modulus-groove-improvisation-iii", "2026-11-18T15:00:00Z"),
        ("piston-slap-machine", "2026-11-20T15:00:00Z"),
        ("redline-bass-burn", "2026-11-23T15:00:00Z"),
        ("seismic-thumbprint", "2026-11-25T15:00:00Z"),
        ("shattered-pickguard", "2026-11-27T15:00:00Z"),
        ("subterranean-pluck", "2026-11-30T15:00:00Z"),
        ("voltage-in-the-tendon", "2026-12-02T15:00:00Z"),
        ("mix", "2026-12-04T20:00:00Z"),
    ]

    print("\n=== STARTING AUTOMATED PUBLICATION SCHEDULING ===")
    for item_key, pub_time in schedule_plan:
        target_video_id = None
        target_title = None

        if item_key == "mix":
            for title, info in ledger.items():
                if info.get("is_mix"):
                    target_video_id = info.get("video_id")
                    target_title = title
                    break
        else:
            track = next((t for t in masters if t["slug"] == item_key), None)
            if track:
                for title, info in ledger.items():
                    if not info.get("is_mix") and track["title"].upper() in title.upper():
                        target_video_id = info.get("video_id")
                        target_title = title
                        break

        if target_video_id:
            print(f"\nScheduling: {target_title[:45]}...")
            schedule_video_publication(youtube, target_video_id, pub_time)
            time.sleep(1)
        else:
            print(f"Warning: Could not find video in ledger for '{item_key}'")

    print("\n=== ALL VIDEOS SCHEDULED SUCCESSFULLY! ===")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--song", help="Upload a specific single by slug")
    ap.add_argument("--all-singles", action="store_true", help="Batch upload all 24 singles")
    ap.add_argument("--mix", help="Upload compilation mix by project folder (e.g. funky-destiny-1hour-bass-mix)")
    ap.add_argument("--schedule-campaign", action="store_true",
                    help="Schedule all uploaded singles and mix according to release calendar")
    ap.add_argument("--update-thumbnail", nargs=2, metavar=("VIDEO_ID", "THUMB_PATH"),
                    help="Update thumbnail for an already uploaded video: --update-thumbnail <VIDEO_ID> <PATH_TO_JPG>")
    ap.add_argument("--sync-channel-thumbnails", action="store_true",
                    help="Automatically match and update thumbnails for all uploaded channel videos")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private",
                    help="Video privacy setting (default: private for safety)")
    args = ap.parse_args()

    if not (args.song or args.all_singles or args.mix or args.update_thumbnail or args.sync_channel_thumbnails or args.schedule_campaign):
        ap.print_help()
        sys.exit(1)

    youtube = get_authenticated_service()

    if args.schedule_campaign:
        schedule_album_campaign(youtube)
    elif args.sync_channel_thumbnails:
        sync_all_channel_thumbnails(youtube)
    elif args.update_thumbnail:
        vid_id, t_path = args.update_thumbnail
        update_thumbnail_for_video(youtube, vid_id, Path(t_path))
    elif args.song:
        upload_single_song(youtube, args.song, privacy=args.privacy)
    elif args.mix:
        upload_compilation_mix(youtube, args.mix, privacy=args.privacy)
    elif args.all_singles:
        masters = load_masters()
        print(f"[youtube] Starting batch upload for {len(masters)} singles...")
        for i, t in enumerate(masters, 1):
            print(f"\n--- [{i}/{len(masters)}] Uploading {t['title']} ---")
            try:
                upload_single_song(youtube, t["slug"], privacy=args.privacy)
                time.sleep(2)  # Avoid rate throttling
            except Exception as e:
                print(f"[youtube] ERROR uploading {t['title']}: {e}")


if __name__ == "__main__":
    main()


