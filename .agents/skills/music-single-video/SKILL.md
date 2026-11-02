---
name: music-single-video
description: >-
  Cria o vídeo individual de uma música para o YouTube usando o motor oficial
  de Visualizador Reativo: arte exclusiva da faixa (1080p Full HD) com drift suave,
  animação da personagem em escala nativa 16:9 (blend translúcido com presença),
  distorções reativas de graves (heatwave + chromatic split), equalizador LED de frequência
  e o HUD badge oficial do canal.
---

# Music Single Video

Leia antes: [`music-channel`](../music-channel/SKILL.md).
Pré-requisito: áudio masterizado em `projects/audio-masters/` ([`music-audio-mastering`](../music-audio-mastering/SKILL.md)).

## Como usar

```bash
S=.agents/skills/music-channel/scripts

# Renderiza uma música específica usando o motor visualizer reativo oficial
python3 $S/render_single.py --song "slap-attack"

# Renderiza em lote todas as faixas
python3 $S/render_single.py --all
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
