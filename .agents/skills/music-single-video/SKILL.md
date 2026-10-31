---
name: music-single-video
description: >-
  Cria o vídeo individual de uma música para o YouTube: clipe(s) visuais em loop
  pela duração da faixa masterizada, enquadramento 16:9 com fundo desfocado,
  card de título animado, fade in/out e áudio AAC 320k.
  Use quando o usuário pedir o vídeo de uma música específica ou lote de singles.
---

# Music Single Video

Leia antes: [`music-channel`](../music-channel/SKILL.md).
Pré-requisito: áudio masterizado em `projects/audio-masters/` ([`music-audio-mastering`](../music-audio-mastering/SKILL.md)).

## Como usar

```bash
S=.agents/skills/music-channel/scripts

python3 $S/render_single.py --song "nome-da-musica" \
  --clips project-assets/videos/clip1.mp4 project-assets/videos/clip2.mp4
```

| Flag | Padrão | Uso |
|---|---|---|
| `--song` | — | slug, título ou caminho do master |
| `--clips` | — | 1 ou mais vídeos e/ou imagens |
| `--title` / `--subtitle` | título da faixa / `$CHANNEL_NAME` | Texto do card animado |
| `--no-title` | — | Oculta card de título |
| `--title-seconds` | `8` | Duração de exibição do card |
| `--resolution` / `--fps` | `1920x1080` / `30` | Resolução e taxa de quadros |
| `--crf` / `--preset` | `18` / `medium` | Qualidade/velocidade do x264 |

Saídas em `projects/single-<slug>/`:
- `renders/<slug>.mp4` — entregável final
- `assets/video/loop.mp4` — loop visual normalizado
- `artifacts/render_report.json` — relatório do render
