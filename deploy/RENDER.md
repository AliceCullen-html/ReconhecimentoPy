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
  `OPENBLAS_NUM_THREADS=1`, `MAX_UPLOAD_MB=40`

## O que muda em relação ao rodar local

| Item | Local | Render (deploy) |
|------|-------|-----------------|
| Servidor | Flask dev server | `gunicorn` (ver Start Command) |
| OpenCV | `opencv-python` | `opencv-python-headless` (sem `libGL`) |
| Torch | o que estiver instalado | wheel **CPU** (menor, sem GPU) |
| Upload máx. | 300 MB | **40 MB** (`MAX_UPLOAD_MB`) |

## Limitações reais do free tier (leia antes de demonstrar)

- **RAM de 512 MB é apertada para o `torch`.** Com vídeo curto e leve costuma
  rodar, mas **pode dar OOM** (o serviço reinicia) em vídeos maiores ou frames
  grandes. Mitigações já aplicadas: torch CPU, 1 worker, threads limitadas,
  upload capado em 40 MB. Se precisar de folga, suba para o plano **Standard**
  (2 GB de RAM) — aí fica confortável.
- **Spin-down por inatividade:** após ~15 min sem tráfego o serviço "dorme"; a
  primeira requisição seguinte demora ~30–60 s para acordar. Normal no free.
- **Processamento é síncrono:** a página espera o pipeline terminar. Use
  **clipes curtos** (poucos segundos) para a demo não estourar tempo/memória.
- **Filesystem efêmero:** as saídas geradas (`data/output/`) somem em cada
  restart/deploy. Como o front mostra o resultado logo após o upload, isso não
  atrapalha o teste; só não conte com persistência.
- **Sem GPU no free.** A inferência é em CPU e é mais lenta.
- **Pesos do modelo** (`yolo11n.pt`, ~5 MB) são baixados pelo `ultralytics` no
  primeiro uso após cada boot. Precisa de rede de saída (o Render tem).

## Recomendação

Para uma demo pública de LinkedIn que "sempre funciona", vídeos de **5–15 s** em
resolução moderada (720p) no free tier são o ponto seguro. Se for demonstrar
com material mais pesado, use o plano Standard ou o **Hugging Face Spaces**
(tem tier de GPU e é feito para demos de ML).
