# baia-vision-poc

Prova de conceito (POC) de **visão computacional** aplicada a uma **baia de
carregamento/descarga**. A partir de um vídeo, o sistema detecta caminhão e
pessoas, delimita a zona da baia, roda uma máquina de estados que cronometra a
operação e emite alertas configuráveis — gerando um **vídeo anotado**, um
**log de eventos em JSON** e um **resumo no console**.

> ⚠️ **POC para demonstração pública.** Feita para rodar sobre *footage*
> royalty-free (banco de imagens livre de direitos). **Nunca** sobre câmeras
> ou vídeos reais de qualquer empresa. Leia a seção
> [Limitações e uso responsável](#limitações-e-uso-responsável).

---

## O que é

Uma camada auxiliar que, quadro a quadro:

1. **Detecta** caminhão (`truck`) e pessoas (`person`) com YOLO.
2. **Delimita** a zona da baia (polígono configurável em coordenadas 0..1).
3. **Cronometra** a operação com uma **máquina de estados** `IDLE`/`ACTIVE`
   e histerese (debounce) para não "piscar".
4. **Alerta** com base em regras booleanas simples (ex.: *pessoa a pé na zona
   sem operação ativa*).
5. **Gera saídas**: `annotated.mp4`, `events.json` e uma tabela no console.

## Para que serve

Demonstrar, de forma tangível (inclusive em posts de LinkedIn), como uma
pipeline enxuta de visão computacional pode **medir tempo de operação** e
**sinalizar condições de risco** numa baia — sem hardware especial, rodando
por linha de comando sobre um vídeo qualquer de banco de imagens.

## Stack

- Python 3.11+
- [`ultralytics`](https://docs.ultralytics.com/) (YOLO — padrão `yolo11n.pt`)
- `opencv-python`
- `numpy`
- `pyyaml`

Sem framework web. Sem dependências desnecessárias. Roda via CLI.

---

## Estrutura

```
baia-vision-poc/
├── config/config.yaml       # zona, classes, thresholds, regras de alerta
├── src/baia_vision/
│   ├── detector.py          # wrapper do YOLO (inferência + tracking)
│   ├── zones.py             # geometria: ponto-em-polígono, frac->pixels
│   ├── operation.py         # máquina de estados IDLE/ACTIVE + debounce
│   ├── alerts.py            # avaliador de regras de alerta
│   ├── annotator.py         # caixas, zona, HUD, cronômetro, alertas
│   └── pipeline.py          # orquestra tudo
├── scripts/run.py           # entrypoint CLI
├── tests/test_zones.py      # testes de geometria (pytest)
├── docs/                    # ARQUITETURA.md e FINE_TUNING.md
└── data/{input,output}/     # vídeos e saídas (gitignored)
```

Detalhe das camadas em [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

---

## Instalação

### Local

```bash
git clone <este-repo> baia-vision-poc
cd baia-vision-poc

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Na primeira execução, o `ultralytics` baixa automaticamente os pesos
(`yolo11n.pt`). É preciso conexão de internet nesse primeiro run.

### Google Colab

```python
!pip install ultralytics opencv-python numpy pyyaml
!git clone <este-repo> baia-vision-poc
%cd baia-vision-poc

# Suba um vídeo royalty-free para data/input/ (menu de arquivos do Colab)
!python scripts/run.py --input data/input/video.mp4 --output data/output/
```

No Colab, use um runtime com **GPU** (Ambiente de execução → Alterar tipo de
ambiente → GPU) para acelerar a inferência.

### Onde baixar *footage* royalty-free

Use **apenas** vídeos livres de direitos, por exemplo:

- [Pexels Videos](https://www.pexels.com/videos/)
- [Pixabay Videos](https://pixabay.com/videos/)
- [Mixkit](https://mixkit.co/free-stock-video/)

Busque por termos como *truck loading dock*, *warehouse forklift*,
*loading bay*. Salve o arquivo em `data/input/` (essa pasta é *gitignored*).

---

## Como rodar

```bash
python scripts/run.py --input data/input/video.mp4 \
                      --output data/output/ \
                      --config config/config.yaml
```

Opções (`--help` para o texto completo):

| Flag | Descrição | Padrão |
|------|-----------|--------|
| `--input`, `-i`  | Vídeo de entrada (.mp4) | *(obrigatório)* |
| `--output`, `-o` | Diretório de saída | `data/output/` |
| `--config`, `-c` | Arquivo YAML de config | `config/config.yaml` |

Ajuste a **zona da baia**, os **thresholds** e as **regras de alerta** em
`config/config.yaml` — nada é hardcoded no código.

---

## Exemplo de saída

**Console:**

```
=== LOG DE EVENTOS ===
 TEMPO(s)  TIPO     DURACAO(s)  DESCRICAO
------------------------------------------------------
     0.96  INICIO            -  Operação de carregamento iniciada
     6.00  FIM            5.04  Operação de carregamento finalizada

=== SAÍDAS ===
Frames processados : 220
FPS do vídeo       : 25.00
Vídeo anotado      : data/output/annotated.mp4
Log de eventos     : data/output/events.json
```

**`events.json`:**

```json
{
  "video": "video.mp4",
  "fps": 25.0,
  "frames": 220,
  "zone": "BAIA 01",
  "events": [
    { "timestamp_s": 0.96, "tipo": "INICIO", "descricao": "Operação de carregamento iniciada" },
    { "timestamp_s": 6.0,  "tipo": "FIM",    "descricao": "Operação de carregamento finalizada", "duracao_s": 5.04 }
  ]
}
```

**Vídeo anotado:** caixas coloridas por classe, polígono da zona (cinza em
`IDLE`, verde em `ACTIVE`), HUD com nome da baia + status + cronômetro, e uma
faixa vermelha quando um alerta dispara.

---

## Configuração

Todo o comportamento vem de `config/config.yaml`. Resumo:

- `model` — pesos, confiança mínima e classes COCO (`0=person`, `7=truck`).
- `zone` — nome e polígono da baia em coordenadas fracionárias (0..1).
- `operation` — condições de início/fim e **debounce** (frames sustentados).
- `alerts` — regras booleanas sobre flags nomeadas (`person_in_zone`,
  `truck_in_zone`, `operation_active`, `person_count`).
- `output` — habilita vídeo anotado e/ou `events.json`.

Detalhes de cada flag e de como adicionar uma regra: veja
[`CLAUDE.md`](CLAUDE.md).

---

## Front de teste (opcional)

Além do CLI, há um front web mínimo (Flask) em [`webapp/`](webapp/) só para
**testar pelo navegador**: você sobe um vídeo por um campo de upload e vê a
tabela de eventos, o vídeo anotado e o `events.json`. É uma camada isolada — o
núcleo da POC continua rodável por CLI, sem framework web.

```bash
pip install -r requirements.txt -r webapp/requirements.txt
python webapp/app.py
# abra http://127.0.0.1:5000 e jogue o vídeo no campo de upload
```

Notas:

- O processamento roda em **background** com **barra de progresso** (o upload
  dispara um job e a página acompanha o status); para um vídeo longo pode levar
  alguns minutos. Rode em vídeos curtos para demonstrar.
- Custo ajustável em `config.yaml` (bloco `processing`: `max_width`,
  `frame_stride`) — útil para hosts pequenos; ver `deploy/RENDER.md`.
- O vídeo anotado é gravado com codec `mp4v`, que nem todo navegador toca
  inline. Se houver `ffmpeg` instalado, o front gera automaticamente uma versão
  H.264 para o preview; caso contrário, use o botão de download.
- Vale o mesmo aviso de uso responsável: **somente footage royalty-free**.

### Deploy público (Render, free)

Dá para publicar esse front no [Render](https://render.com) no plano free — o
[`render.yaml`](render.yaml) na raiz já descreve o serviço. Passo a passo,
limites do free tier (RAM de 512 MB, spin-down, vídeos curtos) e alternativas
em [`deploy/RENDER.md`](deploy/RENDER.md).

> Observação: **não** funciona no Vercel — é serverless e essa carga (ML +
> vídeo) não cabe lá (tamanho da função, limite de upload e timeout). Use
> Render, Hugging Face Spaces ou similar.

---

## Testes

```bash
pip install pytest
pytest -q
```

Cobrem a geometria da zona (ponto dentro/fora do polígono e conversão de
coordenadas fracionárias para pixels).

---

## Limitações e uso responsável

Leia isto antes de tirar qualquer conclusão a partir das saídas.

- **Não é um sistema de segurança de vida.** É uma **camada auxiliar de
  alerta** que sinaliza condições para **verificação humana**. Não deve ser
  usada como único mecanismo de proteção de pessoas.
- **Não identifica pessoas individualmente.** Detecta apenas a classe
  genérica `person`. Não há biometria, reconhecimento facial nem
  re-identificação de indivíduos.
- **Não é reconhecimento de placa (ANPR).** Não há OCR de placa nem qualquer
  leitura de identificação do veículo.
- **Não usa dados reais de trabalhadores nem *footage* corporativo.** Use
  somente vídeo **royalty-free** (Pexels/Pixabay/Mixkit). Não aponte para
  câmeras ou gravações reais de qualquer empresa.
- **Empilhadeira e braço de carregamento NÃO são detectados.** O modelo
  pré-treinado em COCO conhece `person` e `truck`, mas **não** conhece
  "empilhadeira" nem "braço de carregamento" — esses objetos não serão
  rotulados sem *fine-tuning*. Por isso, o **gatilho de operação apoia-se em
  `pessoa + caminhão na zona`**, e não na presença de empilhadeira. O caminho
  para treinar esses detectores está em
  [`docs/FINE_TUNING.md`](docs/FINE_TUNING.md).
- **Precisão depende do vídeo.** Ângulo de câmera, oclusão, iluminação e
  resolução afetam diretamente a detecção. Ajuste `conf`, a zona e o debounce
  para o seu material.

Esta POC é para fins de **demonstração e educação**. Qualquer uso além disso
exige avaliação de privacidade, segurança e conformidade apropriada ao
contexto.

---

## Licença

[MIT](LICENSE).
