# Prospector

Prospecção de canais do YouTube para editores de vídeo, thumbnail designers e
agências de edição. Busca canais por nicho, país e faixa de inscritos, lê o
e-mail público publicado na descrição do canal e organiza os contatos num
pipeline de leads.

É gratuito porque a busca roda na **sua** chave da YouTube Data API, dentro da
quota diária que o Google já concede sem custo. A plataforma nunca paga essa
conta, então não há o que cobrar.

---

## Arquitetura

```
Prospector/
├── backend/          FastAPI (Python) — fala com a YouTube Data API v3
│   ├── app/
│   │   ├── main.py       rotas HTTP
│   │   ├── schemas.py    validação dos filtros (Pydantic)
│   │   ├── youtube.py    cliente da API + extração de e-mail
│   │   ├── keyring.py    pool de chaves, quota e rodízio
│   │   └── scoring.py    score de oportunidade
│   └── tests/            23 testes
└── frontend/         Next.js 16 + React 19 (TypeScript)
    ├── app/              landing (/) e dashboard (/app)
    ├── components/
    └── lib/api.ts        cliente tipado do backend
```

A chave da API fica **apenas no backend**. O navegador conversa com
`/api/*` na própria origem, e o Next reescreve para o serviço Python — assim a
chave nunca aparece na aba de rede do usuário.

---

## Cada usuário usa a própria chave

Isto é o coração do modelo gratuito, então vale ser explícito: **a plataforma
não tem uma chave própria e não paga a conta de ninguém.** Cada pessoa cadastra
a chave dela, e cada chave tem a sua quota de 10.000 unidades por dia.

Uma chave única para todos não fecha na aritmética: uma busca custa 302–604
unidades, então 10.000 unidades dariam **16 a 33 buscas por dia na plataforma
inteira** — somando todos os usuários, não por pessoa.

O isolamento é feito por sessão (`app/sessions.py`):

- cada navegador recebe um id opaco num cookie `httpOnly`, `SameSite=lax`
- cada id de sessão aponta para o seu próprio pool de chaves
- não há conta, senha nem dado pessoal — o cookie identifica um pool e nada mais
- sessões ociosas por 8 horas são descartadas, com teto de 5.000 simultâneas

`tests/test_sessions.py` trava esse comportamento: um visitante não enxerga as
chaves de outro, não gasta a quota de outro, não consegue apagar a chave de
outro (mesmo sabendo os 4 últimos dígitos), e o cookie nunca contém a chave.
Há inclusive um teste de regressão garantindo que não volte a existir um
keyring global no módulo — foi assim que a primeira versão estava escrita.

### Limites do armazenamento atual

O pool vive **em memória**, o que tem duas consequências que importam na hora
de publicar:

1. **Reiniciar o servidor apaga as chaves.** Os usuários recadastram. Aceitável
   num MVP, irritante em produção.
2. **Só funciona num processo.** Com mais de uma réplica atrás de um load
   balancer, a sessão precisa de sticky sessions ou de um store compartilhado.

Quando isso incomodar, o caminho é substituir `InMemoryKeyring` por uma
implementação persistente atrás da mesma interface, com as chaves cifradas em
repouso. O resto do código não muda.

---

## Rodando localmente

Você precisa dos dois processos no ar.

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # Linux/macOS

.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

Documentação interativa em <http://127.0.0.1:8000/docs>.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Abra <http://localhost:3000>.

### 3. Sua API key

1. Entre em <https://console.cloud.google.com> e crie um projeto.
2. **APIs e serviços → Biblioteca** → procure **YouTube Data API v3** → Ativar.
3. **Credenciais → Criar credenciais → Chave de API** → copie.
4. No app, aba **Chaves de API**, cole a chave.

Não é preciso cartão de crédito. Cada projeto rende 10.000 unidades por dia.

---

## Custo de quota

A API do YouTube cobra em *unidades*, não em requisições. Os custos estão
centralizados em `backend/app/keyring.py` e são os mesmos usados pelo
estimador que aparece na tela antes de rodar a busca:

| Chamada              | Unidades | Uso                                  |
| -------------------- | -------- | ------------------------------------ |
| `search.list`        | 100      | encontrar canais candidatos          |
| `channels.list`      | 1        | hidratar até 50 canais por chamada   |
| `playlistItems.list` | 1        | data do último upload, por canal     |

A estimativa é um **teto**: a filtragem por inscritos e por e-mail acontece
antes do enriquecimento de recência, então o gasto real costuma ser menor.

Quando uma chave esgota, o pool rotaciona para a próxima automaticamente. A
quota zera à meia-noite no horário do Pacífico.

---

## Score de oportunidade

Ordenar por inscritos não responde à pergunta que importa — canais gigantes já
têm editor contratado. O score (1–99) soma quatro sinais de 25 pontos:

| Sinal            | O que mede                                                |
| ---------------- | --------------------------------------------------------- |
| **reachability** | existe e-mail público para escrever                        |
| **rhythm**       | frequência de publicação (mais vídeos, mais dor de edição) |
| **recency**      | há quanto tempo publicou (canal parado não contrata)       |
| **fit**          | faixa de porte onde um editor é viável mas não é fixo      |

A faixa-doce é 10k–300k inscritos. Acima de 800k a pontuação cai, porque a
chance de já haver equipe interna é alta.

Os pesos estão isolados em `scoring.py` como heurística inicial, prontos para
serem recalibrados quando houver dados reais de taxa de resposta.

---

## Sobre a extração de e-mail

A API do YouTube **não** expõe o botão "E-mail" da aba Sobre — aquele endereço
fica atrás de um captcha e não é campo de nenhuma resposta da API. O que está
disponível é a **descrição do canal**, onde boa parte dos criadores publica um
contato comercial por conta própria. É de lá, e só de lá, que o e-mail sai.

Quando não há endereço na descrição, o campo volta `null`. O sistema nunca
adivinha padrões como `contato@nomedocanal.com`: endereços inventados quicam e
queimam a reputação do domínio de quem envia.

---

## Testes

```bash
cd backend
.venv/Scripts/python -m pytest -q      # 23 testes
```

```bash
cd frontend
npm run typecheck
npm run build
```

---

## Conformidade

A busca usa a YouTube Data API v3 oficial, com a chave do próprio usuário e
dentro da quota — o uso previsto pelos termos.

O envio de e-mail comercial é responsabilidade de quem envia. No Brasil vale a
LGPD: identifique-se, informe como chegou ao contato e respeite pedidos de
descadastramento. A lista de bloqueio existe para isso.

Não afiliado ao YouTube nem ao Google.
