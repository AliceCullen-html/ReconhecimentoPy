# Fine-tuning: detectar empilhadeira e braço de carregamento

**Contexto.** O modelo pré-treinado em COCO (`yolo11n.pt`) conhece `person` e
`truck`, mas **não** conhece "empilhadeira" nem "braço de carregamento". Por
isso, nesta POC, o gatilho de operação apoia-se em `pessoa + caminhão na zona`.
Para detectar esses objetos específicos, é preciso *fine-tuning* — treinar um
detector customizado por cima do pré-treinado.

Este é um roteiro de **próximos passos**, não um tutorial exaustivo.

## Visão geral do processo

```
coletar frames → rotular → configurar dataset → treinar → avaliar → integrar
```

## 1. Coletar frames

- Extraia quadros de vídeos royalty-free que contenham empilhadeiras / braços
  de carga (ex.: buscas por *forklift warehouse*, *loading arm* em
  Pexels/Pixabay/Mixkit).
- Priorize **diversidade**: ângulos, iluminação, oclusão, distância, modelos
  diferentes de empilhadeira. 300–1000 imagens por classe é um ponto de partida
  razoável para uma POC; mais dados → melhor generalização.
- Dica: use `cv2` para amostrar 1 frame a cada N do vídeo, evitando quadros
  quase idênticos.

## 2. Rotular

- Ferramentas: [Roboflow](https://roboflow.com/),
  [CVAT](https://www.cvat.ai/), [Label Studio](https://labelstud.io/), ou o
  próprio ecossistema do Ultralytics.
- Formato **YOLO**: um `.txt` por imagem, uma linha por objeto:
  `class_id cx cy w h` (todos normalizados 0..1).
- Defina classes novas, por exemplo: `0: forklift`, `1: loading_arm`.
- Mantenha um split **treino/val** (ex.: 80/20) desde o começo.

## 3. Configurar o dataset (`data.yaml`)

```yaml
path: ./dataset
train: images/train
val: images/val
names:
  0: forklift
  1: loading_arm
```

Estrutura esperada:

```
dataset/
├── images/{train,val}/*.jpg
└── labels/{train,val}/*.txt
```

## 4. Treinar (por cima do pré-treinado)

Transfer learning a partir dos pesos COCO acelera a convergência:

```bash
yolo detect train \
  model=yolo11n.pt \
  data=data.yaml \
  epochs=100 \
  imgsz=640 \
  batch=16 \
  name=baia_forklift
```

Ou via Python:

```python
from ultralytics import YOLO
model = YOLO("yolo11n.pt")           # começa do pré-treinado
model.train(data="data.yaml", epochs=100, imgsz=640, batch=16)
```

Use **GPU** (Colab com runtime de GPU serve). Os melhores pesos ficam em
`runs/detect/baia_forklift/weights/best.pt`.

## 5. Avaliar

- Métricas: **mAP@0.5** e **mAP@0.5:0.95**, além de precisão/recall por classe.
  ```bash
  yolo detect val model=runs/detect/baia_forklift/weights/best.pt data=data.yaml
  ```
- Inspecione visualmente falsos positivos/negativos. Se o recall de
  `loading_arm` for baixo, geralmente falta **dado** (mais imagens variadas)
  ou os rótulos estão inconsistentes.
- Itere: colete/rerotule os casos difíceis e re-treine.

## 6. Integrar na POC

1. Aponte `model.weights` no `config/config.yaml` para o novo `best.pt`.
2. Atualize `model.classes` para os novos índices (ex.: incluir `forklift`).
3. Se quiser que a empilhadeira participe do gatilho de operação, crie a flag
   correspondente (ex.: `forklift_in_zone`) em:
   - `_compute_zone_flags` (`pipeline.py`),
   - `SUPPORTED_FLAGS` (`alerts.py`),
   - e ajuste `operation.start_requires` no config.
   Consulte "Como adicionar uma nova flag/regra" no `CLAUDE.md`.

## Notas

- *Fine-tuning* não apaga o conhecimento de `person`/`truck` **se** o novo
  dataset também rotular essas classes; caso contrário, treine um modelo
  separado só para os objetos novos e combine as detecções, ou inclua
  `person`/`truck` no dataset novo.
- Para uma POC de LinkedIn, um detector razoável de `forklift` já é um forte
  incremento — o `loading_arm` costuma exigir mais dados por ser visualmente
  mais variável.
