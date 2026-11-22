#!/usr/bin/env python3
import os
import sys
import glob
import json
import time
import subprocess
import numpy as np
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

OUTPUT_DIR = Path("projects/album-1/shorts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def find_best_energy_window(video_path, target_duration=45.0):
    cmd_probe = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    total_dur = float(subprocess.check_output(cmd_probe).decode().strip())
    
    # Extract audio stream to raw f32le 16kHz mono
    cmd = ['ffmpeg', '-y', '-i', video_path, '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', 'pipe:1']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    raw, _ = p.communicate()
    
    samples = np.frombuffer(raw, dtype=np.float32)
    win_samples = 16000
    num_secs = len(samples) // win_samples
    if num_secs <= target_duration:
        return 0.0, float(num_secs)
        
    rms_per_sec = []
    for s in range(num_secs):
        chunk = samples[s*win_samples : (s+1)*win_samples]
        rms = np.sqrt(np.mean(chunk**2)) if len(chunk) > 0 else 0.0
        rms_per_sec.append(rms)

    target_len = int(target_duration)
    best_s = 15
    best_val = -1.0
    start_search = min(15, max(0, int(num_secs * 0.15)))
    end_search = max(start_search + 1, num_secs - target_len - 5)
    
    for s in range(start_search, end_search):
        energy = sum(rms_per_sec[s:s+target_len])
        if energy > best_val:
            best_val = energy
            best_s = s
            
    return float(best_s), float(target_duration)

def create_short_video(input_path, output_path, start_sec, duration):
    # Direct center crop 9:16 (1080x1920) with audio fade in (0.5s) and fade out (1.0s)
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_sec),
        '-i', input_path,
        '-t', str(duration),
        '-vf', 'crop=ih*(9/16):ih:(iw-ow)/2:0,scale=1080:1920',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
        '-c:a', 'aac', '-b:a', '192k',
        '-af', f'afade=t=in:st=0:d=0.5,afade=t=out:st={duration - 1.0}:d=1.0',
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

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

def upload_short(youtube, file_path, title, song_name, privacy_status="public"):
    body = {
        'snippet': {
            'title': f"{title} ⚡ Funky Bass Solo #shorts",
            'description': f"Melhor momento de '{song_name}' do canal Funky Destiny! 🎸🔥\n\nOuça o álbum completo no canal.\n\n#shorts #bass #funk #slapbass #groove #funkydestiny",
            'tags': ['shorts', 'bass', 'funk', 'slap bass', 'groove', 'funky destiny', 'bass solo', song_name.lower()],
            'categoryId': '10' # Music
        },
        'status': {
            'privacyStatus': privacy_status,
            'selfDeclaredMadeForKids': False
        }
    }
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = request.next_chunk()
    return response.get('id')

if __name__ == "__main__":
    print("Script template ready.")
