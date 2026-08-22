# Deploy

**Backend** no Cloud Run (dentro do projeto Firebase) e **frontend** na Vercel.

O navegador conversa só com o domínio da Vercel: o `next.config.mjs` reescreve
`/api/*` para o Cloud Run no lado do servidor. Isso evita dois problemas de uma
vez — não há CORS, e o cookie de sessão continua sendo *first-party*. Chamar o
Cloud Run direto do navegador tornaria o cookie de terceiros, e o Safari e o
Firefox bloqueiam isso por padrão, o que quebraria as sessões.

---

## Antes de começar

- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) instalado
- Conta de faturamento ativa no projeto — o Cloud Run exige cartão cadastrado
  mesmo para usar apenas o tier gratuito. Você não é cobrado dentro dos limites.
- Conta na Vercel

---

## 1. Projeto e APIs

```bash
gcloud auth login
gcloud config set project SEU_PROJETO_FIREBASE

gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
```

## 2. Firestore

```bash
gcloud firestore databases create --location=southamerica-east1
```

Depois, no console do Firestore, crie uma **política de TTL** no campo
`expires_at` da coleção `prospector_sessions`. Sem ela as sessões antigas ficam
ocupando espaço para sempre; com ela o Google apaga sozinho.

## 3. Segredo de criptografia

As chaves dos usuários são cifradas antes de chegar ao banco. Gere um segredo
longo e guarde no Secret Manager:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```bash
echo -n "COLE_O_SEGREDO_AQUI" | \
  gcloud secrets create prospector-secret --data-file=-
```

> Trocar esse segredo depois torna todas as chaves guardadas ilegíveis. O app
> não quebra — ele descarta o que não consegue ler e os usuários recadastram —
> mas evite trocar sem necessidade.

## 4. Backend no Cloud Run

```bash
cd backend

gcloud run deploy prospector-api \
  --source . \
  --region southamerica-east1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars PROSPECTOR_ENV=production,PROSPECTOR_STORE=firestore \
  --set-secrets PROSPECTOR_SECRET=prospector-secret:latest
```

Por que cada opção importa:

| Opção | Motivo |
| --- | --- |
| `--min-instances 0` | escala a zero; instância parada não é cobrada. É isto que mantém a conta em R$ 0. |
| `--max-instances 3` | teto contra fatura surpresa num pico de tráfego. |
| `--timeout 300` | uma busca intensiva leva ~20s; 300 dá folga sem permitir requisição pendurada. |
| `PROSPECTOR_STORE=firestore` | sem isto o app usa memória, e a escala a zero apagaria as chaves. |
| `PROSPECTOR_ENV=production` | marca o cookie de sessão como `Secure`. |

Anote a URL que o comando imprime, algo como
`https://prospector-api-xxxx.southamerica-east1.run.app`.

Confirme:

```bash
curl https://SUA-URL.run.app/api/health
# {"status":"ok","quota_day":"..."}
```

## 5. Frontend na Vercel

Importe o repositório na Vercel e configure:

- **Root Directory:** `frontend`
- **Environment Variable:** `BACKEND_URL` = a URL do Cloud Run (sem barra no fim)

Ou por linha de comando:

```bash
cd frontend
vercel env add BACKEND_URL production   # cole a URL do Cloud Run
vercel --prod
```

## 6. Conferir

1. Abra o domínio da Vercel
2. **Abrir o app → Chaves de API**, cadastre sua chave do YouTube
3. Recarregue a página — a chave deve continuar lá (é o Firestore funcionando)
4. Faça uma busca

Se o passo 3 falhar, o backend está usando memória: confira se
`PROSPECTOR_STORE=firestore` chegou ao serviço.

---

## Custo

| Serviço | Gratuito por mês | Uso esperado |
| --- | --- | --- |
| Cloud Run | 2M requisições, 180.000 vCPU-s | ~9.000 buscas |
| Firestore | 1 GiB, 50k leituras/dia, 20k escritas/dia | 1 leitura + 1 escrita por requisição |
| Vercel Hobby | 100 GB de banda | site estático leve |

Uma requisição custa **uma** leitura e **uma** escrita no Firestore, mesmo que a
busca cobre quota 500 vezes — o keyring é carregado uma vez, usado em memória e
gravado uma vez ao final. Persistir a cada cobrança esgotaria a cota diária de
escrita em menos de 40 buscas.

## Recomendado

Crie um alerta de orçamento em **Faturamento → Orçamentos e alertas** com um
teto baixo (R$ 5, por exemplo). O `--max-instances 3` já limita o pior caso,
mas o alerta avisa antes de virar dinheiro.
