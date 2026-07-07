# Deploy no Render (free tier)

Guia para publicar o **front de teste** (`webapp/`) no [Render](https://render.com)
usando o plano **Free**. O Render serve porque é um container com servidor de
longa duração — ao contrário do Vercel (serverless), que não roda esse tipo de
carga (ML pesado + processamento de vídeo).

## Passo a passo (via Blueprint)

1. Faça o push deste repositório para o GitHub (branch `main`) — o
   [`render.yaml`](../render.yaml) na raiz já descreve o serviço.
2. No Render: **New +** → **Blueprint**.
3. Conecte a conta do GitHub e selecione este repositório.
4. O Render lê o `render.yaml`, mostra o serviço `baia-vision-poc` (plano
   **Free**) e você confirma em **Apply**.
5. Aguarde o build (instala `torch` CPU + `ultralytics` — pode levar alguns
   minutos na primeira vez).
6. Ao terminar, acesse a URL pública (algo como
   `https://baia-vision-poc.onrender.com`) e suba um vídeo.

### Alternativa (sem Blueprint)

**New +** → **Web Service** → conecte o repo e preencha manualmente:

- **Runtime:** Python
- **Build Command:** `pip install -r deploy/requirements-render.txt`
- **Start Command:**
  `gunicorn webapp.app:app --bind 0.0.0.0:$PORT --workers 1 --worker-class gthread --threads 2 --timeout 600`
- **Environment:** `PYTHON_VERSION=3.11.9`, `OMP_NUM_THREADS=1`,
  `OPENBLAS_NUM_THREADS=1`, `MAX_UPLOAD_MB=40`, `PROC_MAX_WIDTH=480`,
  `PROC_FRAME_STRIDE=3`

## O que muda em relação ao rodar local

| Item | Local | Render (deploy) |
|------|-------|-----------------|
| Servidor | Flask dev server | `gunicorn` (ver Start Command) |
| OpenCV | `opencv-python` | `opencv-python-headless` (sem `libGL`) |
| Torch | o que estiver instalado | wheel **CPU** (menor, sem GPU) |
| Upload máx. | 300 MB | **40 MB** (`MAX_UPLOAD_MB`) |

## Ajustes de custo (o que faz caber no free tier)

O free tier tem **512 MB de RAM** e **0.1 de CPU** — apertado para `torch` +
vídeo. Para caber, o deploy usa:

- **Processamento assíncrono:** o upload dispara um job em background e a página
  mostra uma **barra de progresso** consultando o status. Assim o request HTTP
  não fica pendurado minutos (o que causava o **502** — proxy derruba request
  longo).
- **`PROC_MAX_WIDTH=480`:** redimensiona os frames antes da inferência → menos
  RAM e menos CPU (o vídeo anotado sai em 480px de largura).
- **`PROC_FRAME_STRIDE=3`:** detecta 1 a cada 3 frames e reaproveita as caixas
  nos intermediários. O vídeo e a máquina de estados seguem quadro a quadro, e o
  debounce continua em frames reais — os **tempos dos eventos não mudam**.
- torch **CPU**, **1 worker**, threads das libs numéricas limitadas, upload
  capado em **40 MB**.

Para acelerar mais, aumente `PROC_FRAME_STRIDE` (ex.: 5) ou reduza
`PROC_MAX_WIDTH` (ex.: 384). Localmente, esses valores vêm do
`config/config.yaml` (bloco `processing`) e ficam mais folgados.

## Limitações reais do free tier (leia antes de demonstrar)

- **RAM de 512 MB é apertada para o `torch`.** Mesmo com os ajustes acima,
  vídeos maiores/mais longos **podem dar OOM** (o serviço reinicia). Se precisar
  de folga garantida, suba para o plano **Standard** (2 GB de RAM).
- **0.1 de CPU é lento.** Um clipe de ~10–15 s ainda leva alguns minutos; a
  barra de progresso mostra o andamento. Prefira **clipes curtos** na demo.
- **Spin-down por inatividade:** após ~15 min sem tráfego o serviço "dorme"; a
  primeira requisição seguinte demora ~30–60 s para acordar. Normal no free.
- **Filesystem efêmero:** as saídas (`data/output/`) e os jobs em memória somem
  em cada restart/deploy. O front mostra o resultado logo após o processamento,
  então isso não atrapalha o teste; só não conte com persistência.
- **Sem GPU no free.** A inferência é em CPU e é mais lenta.
- **Pesos do modelo** (`yolo11n.pt`, ~5 MB) são baixados pelo `ultralytics` no
  primeiro uso após cada boot. Precisa de rede de saída (o Render tem).

## Recomendação

Para uma demo pública de LinkedIn que "sempre funciona", vídeos de **5–15 s** em
resolução moderada (720p) no free tier são o ponto seguro. Se for demonstrar
com material mais pesado, use o plano Standard ou o **Hugging Face Spaces**
(tem tier de GPU e é feito para demos de ML).
