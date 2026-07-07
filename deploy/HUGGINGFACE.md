# Deploy no Hugging Face Spaces (grátis, rápido)

O HF Spaces free dá **2 vCPUs + 16 GB de RAM** — ~40× mais CPU que o Render
free. O mesmo vídeo que levava minutos roda em segundos. Usamos um **Docker
Space** que reaproveita o front Flask deste repo (o [`Dockerfile`](../Dockerfile)
na raiz faz tudo: instala deps, pré-baixa os pesos YOLO e sobe o gunicorn na
porta 7860).

## Passo a passo

### 1. Criar o Space
1. Em https://huggingface.co/new-space:
   - **Owner:** sua conta.
   - **Space name:** `baia-vision-poc` (ou o que quiser).
   - **License:** MIT.
   - **SDK:** selecione **Docker** → **Blank**.
   - **Hardware:** *CPU basic (free)*.
2. Crie. O HF já cria um repositório git com um `README.md`.

### 2. Enviar os arquivos
No seu computador, com o [git-lfs](https://git-lfs.com) e login feito
(`huggingface-cli login`):

```bash
# clone o Space recém-criado
git clone https://huggingface.co/spaces/<SEU_USUARIO>/baia-vision-poc hf-space
cd hf-space

# copie o conteúdo deste repositório para dentro (menos a pasta .git)
#   (ajuste o caminho de origem para onde está o ReconhecimentoPy)
rsync -av --exclude='.git' /caminho/para/ReconhecimentoPy/ ./

# use o README com frontmatter do Space (senão o HF não configura a porta)
cp deploy/huggingface/README.md ./README.md

git add -A
git commit -m "deploy baia-vision-poc no Spaces"
git push
```

> O `README.md` do Space **precisa** do bloco de frontmatter YAML (título,
> `sdk: docker`, `app_port: 7860`). Por isso copiamos o de
> `deploy/huggingface/README.md` por cima. O README do projeto continua
> intacto no GitHub.

### 3. Aguardar o build
O HF constrói a imagem (instala torch, baixa os pesos — alguns minutos na
primeira vez) e sobe o Space. Quando ficar **Running**, abra a URL
(`https://<seu_usuario>-baia-vision-poc.hf.space`) e suba um vídeo.

## Alternativa: sem terminal (upload pela web)

Se preferir não usar git: no Space criado, aba **Files** → **Add file** →
**Upload files**, e suba o `Dockerfile`, as pastas `src/`, `webapp/`, `config/`,
`deploy/` e o `deploy/requirements-render.txt`. Depois edite o `README.md` do
Space colando o frontmatter de `deploy/huggingface/README.md`.

## Ajustes (opcional)

O `Dockerfile` já vem com valores folgados para o hardware do HF:

| Env | Valor | Efeito |
|-----|-------|--------|
| `PROC_MAX_WIDTH`   | `1280` | processa em até 1280px (720p passa inteiro) |
| `PROC_FRAME_STRIDE`| `1`    | detecta todos os frames (vídeo mais fluido) |
| `MAX_UPLOAD_MB`    | `200`  | upload maior (tem RAM sobrando) |
| `OMP_NUM_THREADS`  | `2`    | usa os 2 vCPUs na inferência |

Para acelerar em vídeos maiores, aumente `PROC_FRAME_STRIDE` (ex.: 2) ou reduza
`PROC_MAX_WIDTH` (ex.: 960) — edite os `ENV` no `Dockerfile` e faça push.

## Notas

- **Preview inline funciona:** a imagem inclui `ffmpeg`, então o vídeo anotado é
  transcodificado para H.264 e toca direto no navegador.
- **Sleep:** o Space free "dorme" após ~48h sem uso; acorda no próximo acesso.
- Continua valendo o uso responsável: só **footage royalty-free**.
