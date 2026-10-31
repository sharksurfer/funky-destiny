---
name: music-mix-compilation
description: >-
  Monta o vídeo longo (1 hora ou mais) para canal de música com todas as
  faixas masterizadas concatenadas: ordem configurável (shuffle/alfabética/arquivo),
  gap ou crossfade, garantia de duração mínima, loop visual rápido (stream copy)
  e geração de capítulos para a descrição do YouTube.
---

# Music Mix Compilation (1h+)

Leia antes: [`music-channel`](../music-channel/SKILL.md).
Pré-requisito: áudios masterizados em `projects/audio-masters/` ([`music-audio-mastering`](../music-audio-mastering/SKILL.md)).

## Como usar

```bash
S=.agents/skills/music-channel/scripts

# 1. Simulação: ver ordem, duração total e lista de capítulos
python3 $S/build_mix.py --dry-run --order shuffle --seed 42

# 2. Renderização do vídeo completo
python3 $S/build_mix.py --order shuffle --seed 42
```

| Flag | Padrão | Uso |
|---|---|---|
| `--order` | `shuffle` | `shuffle` · `catalog` · `file` (`--order-file`, 1 slug por linha) |
| `--seed` | — | Semente aleatória (reproduzível) |
| `--gap` | `1.0` | Segundos de silêncio entre faixas |
| `--crossfade` | `0` | Segundos de transição sobreposta (se > 0 substitui o gap) |
| `--min-duration` | `3660` | Duração mínima em segundos (1h01) |
| `--fill` | `fail` | Se menor que a meta: `repeat` (estende) · `fail` · `allow-short` |
| `--clips` | todos em `project-assets/videos` | Clipes para compor o loop visual |
| `--project` | `mix-<data>` | Nome da pasta do projeto em `projects/` |

Saídas em `projects/<project>/`:
- `renders/<project>.mp4` — vídeo final para upload
- `artifacts/chapters.txt` — texto com os timestamps pronto para copiar na descrição do YouTube
- `artifacts/tracklist.json` — manifesto técnico com durações e dados de cada faixa
