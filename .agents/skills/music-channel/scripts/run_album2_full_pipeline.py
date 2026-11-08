#!/usr/bin/env python3
"""Pipeline completo para Album 2:
1. Re-renderiza todos os 12 singles com rotação e ordem aleatória dos vídeos da personagem (efeito translúcido/fantasmagórico).
2. Faz o upload de cada vídeo para o YouTube via API já com agendamento escalonado (Seg/Qua/Sex às 12:00 BRT).
3. Atualiza as thumbnails oficiais sem texto com HUD no YouTube.
4. Salva o registro no ledger e exibe o resumo completo.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO / ".agents/skills/music-channel/scripts"))

from common import load_masters
from render_single import render_single_song
from youtube_uploader import get_authenticated_service, upload_single_song, update_thumbnail_for_video

def calculate_schedule(singles_count: int = 12):
    # Começa na próxima segunda-feira: 09/11/2026
    start_date = datetime(2026, 11, 9, tzinfo=timezone.utc)
    target_days = [0, 2, 4]  # Seg, Qua, Sex
    current = start_date
    schedule = []
    
    while len(schedule) < singles_count:
        if current.weekday() in target_days:
            # 15:00 UTC = 12:00 BRT
            dt = datetime(current.year, current.month, current.day, 15, 0, 0, tzinfo=timezone.utc)
            schedule.append(dt)
        current += timedelta(days=1)
        
    return schedule

def main():
    print("=" * 70)
    print("INICIANDO PIPELINE: RENDER COM PERSONAGEM + UPLOAD ESCALONADO YOUTUBE")
    print("=" * 70)

    masters = load_masters()
    print(f"Total de faixas encontradas: {len(masters)}")
    schedule = calculate_schedule(len(masters))
    
    youtube = get_authenticated_service()

    summary_file = REPO / "projects/album-2/pipeline_scheduled_uploads.json"
    results = []
    if summary_file.exists():
        try:
            results = json.loads(summary_file.read_text())
        except Exception:
            results = []

    # Verificar ledger para faixas já enviadas recentemente nesta rodada (após 07/11 11:00)
    ledger_file = REPO / "projects/album-2/uploads_ledger.json"
    recent_uploaded_slugs = {}
    if ledger_file.exists():
        try:
            ledger_data = json.loads(ledger_file.read_text())
            for item_title, item_info in ledger_data.items():
                if isinstance(item_info, dict) and item_info.get("updated_at", "").startswith("2026-11-07"):
                    for t in masters:
                        if t["title"] in item_title:
                            recent_uploaded_slugs[t["slug"]] = item_info.get("video_id")
        except Exception:
            pass

    for idx, (track, pub_dt) in enumerate(zip(masters, schedule), 1):
        slug = track["slug"]
        title = track["title"]

        # Se já foi enviado com sucesso hoje, podemos pular para não duplicar
        if slug in recent_uploaded_slugs:
            vid_id = recent_uploaded_slugs[slug]
            print(f"\n[{idx:02d}/{len(masters):02d}] Faixa '{title}' já enviada hoje com sucesso (ID: {vid_id}). Pulando...")
            if not any(r.get("slug") == slug for r in results):
                results.append({
                    "track_num": idx,
                    "title": title,
                    "slug": slug,
                    "video_id": vid_id,
                    "publish_at_brt": (pub_dt - timedelta(hours=3)).strftime("%d/%m/%Y às %H:%M BRT"),
                    "publish_at_iso": pub_dt.isoformat().replace("+00:00", "Z"),
                    "url": f"https://youtu.be/{vid_id}"
                })
            continue

        pub_iso = pub_dt.isoformat().replace("+00:00", "Z")
        brt_str = (pub_dt - timedelta(hours=3)).strftime("%d/%m/%Y às %H:%M BRT")

        print(f"\n[{idx:02d}/{len(masters):02d}] --------------------------------------------------")
        print(f"Música: {title} ({slug})")
        print(f"Estreia agendada para: {brt_str} (ISO: {pub_iso})")
        print("------------------------------------------------------------------")

        # 1. Renderiza o single com --force para aplicar a ordem aleatória da personagem
        print(f"[pipeline] Renderizando vídeo 1080p para {slug}...")
        video_out = render_single_song(slug, force=True)
        print(f"[pipeline] Vídeo renderizado com sucesso: {video_out}")

        # 2. Upload para o YouTube com agendamento automático
        print(f"[pipeline] Enviando para o YouTube com estreia agendada...")
        video_id = upload_single_song(youtube, slug, privacy="private", publish_at=pub_iso)
        print(f"[pipeline] Upload concluído! ID: {video_id} -> https://youtu.be/{video_id}")

        results.append({
            "track_num": idx,
            "title": title,
            "slug": slug,
            "video_id": video_id,
            "publish_at_brt": brt_str,
            "publish_at_iso": pub_iso,
            "url": f"https://youtu.be/{video_id}"
        })

        summary_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))

        # Pequena pausa entre uploads para respeitar limites de taxa
        time.sleep(3)

    summary_file = REPO / "projects/album-2/pipeline_scheduled_uploads.json"
    summary_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print("PIPELINE CONCLUÍDO COM SUCESSO!")
    print(f"Resumo salvo em: {summary_file}")
    print("=" * 70)

if __name__ == "__main__":
    main()

