# Arquitetura

O `baia-vision-poc` é uma pipeline linear de camadas, cada uma com uma
responsabilidade única. Os dados fluem em um sentido só, frame a frame.

## Diagrama de camadas

```
        ┌─────────────┐
        │    VÍDEO     │  data/input/*.mp4  (cv2.VideoCapture)
        └──────┬──────┘
               │ frame BGR (numpy)
               ▼
        ┌─────────────┐
        │  DETECTOR    │  detector.py — YOLO (ultralytics) + tracking
        └──────┬──────┘
               │ list[Detection]  (cls, conf, xyxy, track_id, foot_point)
               ▼
        ┌─────────────┐
        │    ZONAS     │  zones.py — polígono em pixels + ponto-em-polígono
        └──────┬──────┘
               │ flags: person_in_zone, truck_in_zone, truck_absent, person_count
               ▼
        ┌─────────────┐
        │  MÁQUINA DE  │  operation.py — IDLE/ACTIVE + debounce (histerese)
        │   ESTADOS    │  → Event(INICIO/FIM, timestamp, duração)
        └──────┬──────┘
               │ estado + operation_active
               ▼
        ┌─────────────┐
        │   ALERTAS    │  alerts.py — avaliador booleano AND/OR/NOT
        └──────┬──────┘
               │ list[FiredAlert]
               ▼
        ┌─────────────┐
        │  ANOTADOR    │  annotator.py — caixas, zona, HUD, cronômetro, alertas
        └──────┬──────┘
               │ frame anotado
               ▼
        ┌─────────────┐
        │    SAÍDA     │  pipeline.py — annotated.mp4 + events.json + console
        └─────────────┘
```

A orquestração (o laço que lê cada frame e passa os dados por essas camadas)
vive em `pipeline.py`. A CLI (`scripts/run.py`) apenas valida argumentos,
carrega o config e chama a pipeline.

## Responsabilidade de cada módulo

### `detector.py`
Isola o resto do código da API do ultralytics. Carrega os pesos, roda
`model.track(persist=True)` (tracking com IDs estáveis) e normaliza cada
resultado em um `Detection` — incluindo `foot_point` (centro-x, base-y da
caixa), o ponto usado para decidir presença na zona. Import do ultralytics é
preguiçoso, então o pacote é importável sem torch.

### `zones.py`
Geometria pura (só numpy), portanto totalmente testável sem vídeo. Converte o
polígono de coordenadas fracionárias (0..1) para pixels e implementa
ponto-em-polígono por *ray casting* próprio. A classe `Zone` encapsula nome +
polígono em pixels e expõe `contains(point)`.

### `operation.py`
A máquina de estados `IDLE`/`ACTIVE`. Consome apenas flags booleanas — não sabe
nada de YOLO ou geometria. A **histerese (debounce)** é o núcleo: uma transição
só ocorre após N frames consecutivos satisfazendo a condição
(`debounce_frames_start` / `debounce_frames_end`), o que elimina eventos falsos
por "piscar" da detecção. Emite `Event` com timestamp em segundos e, no `FIM`,
a duração.

### `alerts.py`
Um avaliador booleano **mínimo** (`AND`/`OR`/`NOT`, sem parênteses) sobre flags
nomeadas. Cada regra do config vira um `AlertRule`; o `AlertEngine` avalia
todas contra as flags do frame e devolve os `FiredAlert`. Flags desconhecidas
geram erro — para pegar erros de config cedo.

### `annotator.py`
Camada de apresentação (OpenCV). Desenha, nesta ordem: zona (fundo translúcido,
cor por estado) → caixas por classe → HUD (nome + status + cronômetro) → faixa
de alerta. Cores/estilos são constantes locais — detalhes de renderização, não
de negócio.

### `pipeline.py`
O maestro. Abre o vídeo, instancia cada camada a partir do config, roda o laço
frame a frame, escreve o vídeo anotado e o `events.json`, e devolve um
`PipelineResult`. É a única camada acoplada a todas as outras — de propósito.

## Por que essa separação

- **Testabilidade**: geometria e máquina de estados não dependem de GPU/vídeo.
- **Troca de peças**: dá para trocar o modelo (config) ou o backend de
  detecção (só `detector.py`) sem tocar no resto.
- **Config sobre código**: o comportamento muda pelo YAML, não por edição de
  código — ver `CLAUDE.md`.
