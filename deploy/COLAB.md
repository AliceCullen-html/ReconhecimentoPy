# Rodar no Google Colab (grátis, com link público)

Jeito mais rápido e **grátis** de colocar o front no ar com CPU/GPU de verdade.
O Colab roda o app e um túnel público (cloudflared) te dá uma URL
`trycloudflare.com` temporária — perfeita para demonstrar ou gravar um vídeo de
LinkedIn.

## Abrir com um clique

👉 **[Abrir o notebook no Colab](https://colab.research.google.com/github/AliceCullen-html/ReconhecimentoPy/blob/main/deploy/colab/baia_vision_colab.ipynb)**

(equivale a: `colab.research.google.com/github/AliceCullen-html/ReconhecimentoPy/blob/main/deploy/colab/baia_vision_colab.ipynb`)

## Passos no notebook

1. **(Opcional, recomendado)** `Ambiente de execução` → `Alterar o tipo de
   ambiente` → **T4 GPU**. Deixa a inferência YOLO muito mais rápida.
2. Rode as 3 células de código em ordem (▶️):
   - clona o repositório,
   - instala `ultralytics` + `flask` + `gunicorn` e baixa o `cloudflared`,
   - sobe o app e imprime a **URL pública**.
3. Abra o link `https://....trycloudflare.com` e suba um vídeo royalty-free.

## Observações

- **URL temporária:** o link vale enquanto o notebook estiver aberto/rodando.
  Fechou o Colab, o link morre. Para uma demo pontual (ou gravar um vídeo), é
  ideal; para algo 24/7, use Cloud Run ou um plano pago.
- **Sem conta/token:** o cloudflared quick tunnel não exige login.
- **Velocidade:** com GPU T4, processa em segundos. Em CPU, prefira clipes
  curtos ou aumente `PROC_FRAME_STRIDE` na célula 3.
- **Uso responsável:** só footage royalty-free; não é sistema de segurança de
  vida (ver README principal).

## Se algo falhar

- Erro de import logo após instalar deps: `Ambiente de execução` → `Reiniciar
  ambiente` e rode as células de novo (o Colab às vezes precisa reiniciar após
  atualizar pacotes).
- URL não apareceu: rode a última célula novamente (o túnel reconecta).
