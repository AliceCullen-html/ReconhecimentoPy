# CLAUDE.md — guia para futuras sessões de IA neste repositório

Este arquivo orienta agentes de IA (e humanos) a trabalhar no `baia-vision-poc`
sem quebrar as premissas do projeto. Leia antes de editar.

## Regra de ouro

**Configuração vive em `config/config.yaml`, NUNCA hardcoded no código.**
Threshold de confiança, classes, polígono da zona, debounce, regras de alerta
e flags de saída são todos parâmetros de negócio → YAML. Se você sentir vontade
de escrever um número mágico no código, ele provavelmente pertence ao config.

Exceção deliberada: constantes de **apresentação** do `annotator.py` (cores
BGR, espessura de linha, altura da barra do HUD) são detalhes de renderização,
não de negócio, e ficam como constantes locais nessa camada.

## Arquitetura em uma linha

```
vídeo → detector → zonas → máquina de estados → alertas → anotador → saída
```

Cada seta é um módulo com responsabilidade única. A `pipeline.py` é a única
camada que conhece todas as outras; as demais são isoladas e testáveis.
Veja `docs/ARQUITETURA.md` para o detalhamento.

## Módulos

| Módulo | Responsabilidade | Depende de |
|--------|------------------|-----------|
| `detector.py`  | Carrega YOLO, roda inferência + tracking, normaliza em `Detection` | ultralytics (import preguiçoso) |
| `zones.py`     | Geometria: frac→pixels, ponto-em-polígono, `Zone` | numpy |
| `operation.py` | Máquina de estados `IDLE`/`ACTIVE` + debounce + cronômetro | — |
| `alerts.py`    | Avaliador booleano mínimo (`AND`/`OR`/`NOT`) sobre flags | — |
| `annotator.py` | Desenha caixas, zona, HUD, alertas | opencv, numpy |
| `pipeline.py`  | Orquestra o fluxo frame a frame e escreve as saídas | todos acima + opencv |

## Fluxo de dados frame a frame (o que a `pipeline` faz)

1. Lê o frame BGR do `cv2.VideoCapture`.
2. `Detector.detect(frame)` → `list[Detection]` (com `track_id` e `foot_point`).
3. `_compute_zone_flags(detections, zone)` calcula as flags do frame usando o
   `foot_point` (base da caixa) para decidir presença na zona:
   - `person_in_zone`, `truck_in_zone`, `truck_absent`, `person_count`.
4. `OperationStateMachine.update(flags, frame_idx, timestamp_s)` avança a
   máquina com **debounce** e devolve um `Event` (`INICIO`/`FIM`) se houve
   transição.
5. `AlertEngine.evaluate({**zone_flags, "operation_active": ...})` retorna os
   `FiredAlert` do frame.
6. `annotator.annotate(...)` desenha tudo; `VideoWriter` grava o frame.
7. Ao final, serializa `events.json` e devolve `PipelineResult`.

Timestamp de vídeo = `frame_idx / fps`.

## Flags disponíveis (vocabulário compartilhado)

Calculadas por frame e consumidas por `operation` e `alerts`:

- `person_in_zone` — há ≥1 pessoa na zona.
- `truck_in_zone` — há caminhão na zona.
- `truck_absent` — negação de `truck_in_zone` (usada pelo `end_when`).
- `operation_active` — máquina em `ACTIVE` (só nas regras de alerta).
- `person_count` — nº de pessoas na zona (inteiro; `>0` é verdadeiro).

Ao adicionar uma flag nova, atualize:
`SUPPORTED_FLAGS` em `alerts.py`, `_compute_zone_flags` em `pipeline.py`,
e esta lista.

## Como adicionar uma nova regra de alerta

1. Edite `config/config.yaml`, na lista `alerts`:
   ```yaml
   - name: "duas_pessoas_na_zona"
     description: "Mais de uma pessoa na baia durante a operação"
     when: "person_count AND operation_active"
     severity: "warning"
   ```
2. `when` só pode usar as flags de `SUPPORTED_FLAGS` e os operadores
   `AND` / `OR` / `NOT` (sem parênteses; precedência `NOT > AND > OR`).
3. Se precisar de uma flag inexistente, crie-a primeiro (ver seção acima). O
   avaliador **rejeita** flags desconhecidas com `ValueError` — de propósito,
   para pegar erros de digitação cedo.
4. Nada de código novo é necessário para regras que usem flags existentes.

## Como trocar o modelo

Edite `model.weights` no config (ex.: `yolo11n.pt` → `yolo11s.pt` para mais
precisão, ao custo de velocidade). Ajuste `model.conf` e `model.classes`
(índices COCO) conforme necessário. O `Detector` é agnóstico ao arquivo de
pesos — o ultralytics baixa automaticamente se não existir localmente.

Para detectar objetos que o COCO **não** conhece (empilhadeira, braço de
carga), é preciso *fine-tuning* — ver `docs/FINE_TUNING.md`.

## Convenções de código

- **Docstrings** em toda função/classe pública; **type hints** onde ajudam.
- Português nas mensagens de usuário, docstrings e comentários.
- Imports pesados (ultralytics/torch) são **preguiçosos** para manter o pacote
  e os testes de geometria importáveis sem GPU/torch.
- Sem estado global; passe dependências explicitamente.
- Ao decidir por algo ambíguo, escolha o **mais simples** e comente a decisão
  no código (padrão já usado neste repo).

## Testes

`pytest -q`. Cobrem `zones.py` (geometria pura). Ao mexer em geometria, rode-os.
O `conftest.py` na raiz coloca `src/` no `sys.path`, então `pytest` funciona
sem instalar o pacote.

## Não-objetivos (não implemente)

Sem ANPR/OCR de placa; sem identificação individual de pessoas; sem framework
web; sem dependências além das de `requirements.txt`. Esta é uma POC de
demonstração sobre *footage* royalty-free — ver seção "Limitações" do README.
