---
name: music-audio-mastering
description: >-
  Masterização das faixas do canal de música: detecta finais abruptos via análise
  de RMS nos últimos 0.5s, aplica fade-out gradual nos últimos 5 segundos, normaliza
  para -14 LUFS (two-pass loudnorm) e gera FLAC 48 kHz/24-bit + manifesto masters.json.
  Use antes de qualquer render de vídeo (single ou mix), ou quando novas músicas forem adicionadas.
---

# Music Audio Mastering

Leia antes: [`music-channel`](../music-channel/SKILL.md).

## Por que masterizar

- Faixas geradas por IA muitas vezes **terminam abruptamente** sem cauda natural → fade-out de 5 s.
- Faixas têm volumes e dinâmicas desiguais → normalização em −14 LUFS (padrão YouTube) garante consistência sem distorção.

## Comandos

```bash
S=.agents/skills/music-channel/scripts

python3 $S/master_tracks.py --dry-run     # 1. Análise prévia: duração, RMS final, quem precisa de fade
python3 $S/master_tracks.py               # 2. Processamento e geração dos masters
```

Opções principais:

| Flag | Padrão | Uso |
|---|---|---|
| `--fade` | `5` | Duração do fade-out (s) |
| `--fade-policy` | `auto` | `auto` = apenas finais abruptos · `all` = todas · `none` |
| `--abrupt-threshold-db` | `-35` | RMS dos últimos 0,5 s acima disso = abrupto |
| `--lufs` / `--tp` | `-14` / `-1` | Alvo de loudness / teto de true-peak |
| `--only "<texto>"` | — | Processa apenas arquivos com o texto no nome |
| `--force` | — | Re-processa mesmo se o master já existir |

Saídas:
- `projects/audio-masters/assets/audio/<slug>.flac`
- `projects/audio-masters/artifacts/masters.json` — lido pelos renderizadores de vídeo.
