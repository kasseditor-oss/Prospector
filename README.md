# Prospector

Aplicativo de desktop para achar quem precisa de um editor de vídeo. Duas
fontes, cada uma respondendo a uma pergunta diferente:

| Fonte | Acha | A pergunta que responde |
| --- | --- | --- |
| **Canais do YouTube** | quem *provavelmente* vai precisar | quem publica muito e ainda edita sozinho |
| **Pedidos no X** | quem está pedindo *agora* | quem escreveu "procuro editor" esta semana |

O YouTube dá volume e permanência: um canal continua sendo um bom lead daqui a
três meses. O X dá urgência: um pedido de contratação vira notícia velha em um
dia. As duas bases ficam **separadas** dentro do app, porque envelhecem em
ritmos diferentes.

Roda inteiro na sua máquina, com as **suas** credenciais. Não há servidor,
conta nem mensalidade.

---

## Instalar

### Pronto para baixar

Cada versão publicada tem os dois instaladores prontos em
**[Releases](../../releases)** — não é preciso compilar nada:

| Sistema | Arquivo | O que fazer |
| --- | --- | --- |
| Windows | `ProspectorSetup.exe` | dois cliques |
| macOS | `Prospector.dmg` | abrir e arrastar para Aplicativos |

Os dois saem do mesmo commit, compilados pelo GitHub Actions — o `.exe` num
Windows e o `.dmg` num Mac, porque o PyInstaller empacota o interpretador da
máquina que faz o build.

### Ou compilar você mesmo

São **dois aplicativos independentes**, do mesmo código: cada sistema tem o
seu, e cada um é um arquivo só para entregar.

| Sistema | Compila com | Entrega |
| --- | --- | --- |
| Windows | `compilar.bat` | `backend\dist\ProspectorSetup.exe` (~36 MB) |
| macOS | `./compilar-mac.command` | `backend/dist/Prospector.dmg` |

Cada build tem de rodar no sistema de destino — o PyInstaller não compila para
outro sistema operacional.

### No Windows

1. `compilar.bat` — compila tudo
2. `backend\dist\ProspectorSetup.exe` — dois cliques

`ProspectorSetup.exe` é **um arquivo só** com o programa inteiro dentro: é o
que você entrega para outra pessoa. Aceita `/S` para instalar sem abrir a
janela.

A instalação é **por usuário** (`%LOCALAPPDATA%\Programs\Prospector`): não pede
administrador e não toca em nada do sistema. Depois disso, abra pelo ícone no
Menu Iniciar.

O Windows vai mostrar *"O Windows protegeu o seu PC"* porque o executável não
tem assinatura digital — assinar exige certificado pago. Clique em **Mais
informações → Executar assim mesmo**.

### No macOS

```bash
chmod +x compilar-mac.command   # só na primeira vez
./compilar-mac.command          # ou dois cliques no Finder
```

Resultado: `backend/dist/Prospector.dmg` — o arquivo para entregar. Quem
recebe abre o `.dmg` e arrasta o Prospector para a pasta Aplicativos.

**Precisa rodar num Mac.** O PyInstaller empacota o interpretador e os módulos
compilados da máquina que faz o build, então um PC com Windows não consegue
gerar um `.app` que funcione — do mesmo jeito que um Mac não gera o `.exe`. Não
existe truque para contornar isso; é preciso um Mac (ou um runner macOS no
GitHub Actions).

Na primeira abertura o macOS diz que o app é de um desenvolvedor não
identificado: **botão direito no app → Abrir**, uma vez só.

### Desinstalar

- **Windows:** Configurações → Aplicativos → Prospector
- **macOS:** arraste o `Prospector.app` para o Lixo

Em nenhum dos dois as suas bases são apagadas junto — buscas custam
dinheiro e quota.

### Suas credenciais

O app tem **um campo só**. Cole a credencial e ele reconhece de qual serviço
ela é pelo formato — chave do YouTube começa com `AIza`, token do Apify com
`apify_api_`. Aba **Chaves de API**.

**YouTube** (para buscar canais):

1. <https://console.cloud.google.com> → crie um projeto
2. **APIs e serviços → Biblioteca** → **YouTube Data API v3** → **Ativar**
3. **Credenciais → Criar credenciais → Chave de API** → copie

Não precisa de cartão. Cada projeto rende 10.000 unidades por dia.

**Apify** (para buscar pedidos no X):

1. <https://console.apify.com> → crie a conta
2. **Settings → API & Integrations** → copie o *Personal API token*

A conta gratuita vem com US$ 5 de crédito por mês, e o app mostra quanto
sobrou. Cada busca custa uns centavos — o teto aparece na tela **antes** de
você rodar.

Nenhuma das duas é obrigatória: sem a chave do YouTube a busca de canais fica
indisponível e a de pedidos continua funcionando, e vice-versa. O app diz qual
está faltando em vez de falhar em silêncio.

---

## Estrutura

```
Prospector/
├── compilar.bat              compila tudo no Windows
├── compilar-mac.command      compila tudo no macOS (rode num Mac)
├── iniciar.bat               abre o app (atalho para quem roda da pasta)
├── backend/                  FastAPI + o executável de desktop
│   ├── app/
│   │   ├── main.py             rotas HTTP e o serviço dos arquivos da interface
│   │   ├── localonly.py        recusa quem chega em nome de outro domínio
│   │   ├── schemas.py          validação dos filtros (Pydantic)
│   │   ├── status.py           as quatro etapas do funil, para as duas bases
│   │   ├── paths.py            onde ficam os dados do usuário
│   │   │
│   │   ├── youtube.py          cliente da API, e-mail e cadência
│   │   ├── socials.py          redes sociais publicadas pelo criador
│   │   ├── scoring.py          score de oportunidade
│   │   ├── keyring.py          pool de chaves, quota e rodízio
│   │   ├── leads.py            a base de canais (SQLite)
│   │   ├── mailer.py           envio de e-mail pela conta do usuário (SMTP)
│   │   │
│   │   ├── xsearch.py          busca no X via Apify, e o teto de custo
│   │   ├── hiring.py           separa quem contrata de quem se oferece
│   │   ├── posts.py            a base de pedidos (SQLite, à parte)
│   │   │
│   │   ├── store.py            onde as credenciais ficam entre execuções
│   │   └── secretbox.py        cifragem (DPAPI no Windows, Chaveiro no Mac)
│   ├── desktop.py            ponto de entrada do aplicativo
│   ├── packaging/            receitas do PyInstaller (Win/Mac), ícones,
│   │                         instalador e desinstalador
│   └── tests/                257 testes
├── frontend/                 Next.js 16 + React 19 (TypeScript)
│   ├── app/                    a interface (uma página só)
│   ├── components/
│   └── lib/
│       ├── api.ts              cliente tipado do backend
│       └── links.ts            só http e https viram link clicável
└── tools/                    check-contrast.py
```

### Um processo só

No aplicativo de desktop o Python serve **a interface e a API na mesma
origem**: o Next exporta páginas estáticas e o FastAPI as entrega. Isso apaga
de uma vez o proxy, o CORS e o problema de cookie de terceiros — não existe
segunda origem para conflitar. Não há Node rodando na sua máquina.

A janela é um Chromium já instalado, aberto em modo aplicativo (sem abas, sem
barra de endereço). Fechar a janela encerra o processo.

---

## Onde ficam os seus dados

**Fora** da pasta do programa — reinstalar ou atualizar nunca encosta neles.

| Sistema | Pasta |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Prospector` |
| macOS | `~/Library/Application Support/Prospector` |
| Linux | `$XDG_DATA_HOME/Prospector` |

| Arquivo | O que é |
| --- | --- |
| `leads.db` | a base de canais do YouTube (SQLite) |
| `posts.db` | a base de pedidos do X (SQLite, separada de propósito) |
| `keys.json` | suas credenciais, cifradas |

A chave de criptografia fica no cofre do próprio sistema, nunca ao lado do
arquivo cifrado:

- **Windows — DPAPI.** Só a sua conta de usuário, nesta máquina, abre.
- **macOS — Chaveiro.** O arquivo é Fernet, mas a chave Fernet mora no
  Chaveiro do login. Mesma garantia: copiar a pasta para outro Mac não serve.

Onde nenhum dos dois existe, a alternativa é Fernet com um segredo em arquivo —
mais fraco, e `secretbox.describe()` diz isso na tela em vez de prometer o que
não entrega.

O desinstalador **não apaga** a base sem perguntar: buscas custam quota.

---

## A base cresce, não é substituída

Cada busca grava o que encontrou. Buscar um segundo nicho **soma** ao que já
existe, e um canal encontrado duas vezes continua sendo um lead — os números
dele são atualizados, mas a data de entrada na base é preservada. Reencontrar
não é descobrir.

Na aba **Base**: filtro por nome, `@handle` ou nicho, filtro "só com e-mail",
ordenação, exportação CSV e remoção.

### Duas bases, não uma

`leads.db` e `posts.db` nunca se misturam. É uma decisão sobre validade: um
canal continua sendo um bom lead daqui a três meses, um pedido de contratação
morre em um dia. Juntá-los faria a lista inteira envelhecer no ritmo da parte
mais perecível. O seletor no topo troca a fonte inteira — rótulos, filtros,
base e o medidor de crédito mudam junto.

### Em que pé está cada lead

Quatro etapas, iguais nas duas bases: **Não contatado → Contatado → Respondeu
→ Parceria**. A etapa se muda direto na tabela e dá para filtrar por ela.

Uma busca posterior **nunca** reescreve essa marca. Os números do canal são
atualizados, a sua anotação não — perder o registro de quem já respondeu por
causa de uma busca de rotina seria pior do que não ter o campo.

---

## Custo de quota

A API do YouTube cobra em *unidades*, não em requisições. Os custos ficam em
`backend/app/keyring.py`, e são os mesmos que alimentam o estimador mostrado na
tela **antes** de você rodar a busca.

| Chamada | Unidades | Uso |
| --- | --- | --- |
| `search.list` | 100 | encontrar canais candidatos |
| `channels.list` | 1 | hidratar até 50 canais por chamada |
| `playlistItems.list` | 1 | histórico de uploads, por canal |

| Busca | Sem filtro de atividade | Com |
| --- | --- | --- |
| 1 nicho, normal | 202 | 302 |
| 1 nicho, intensivo | 505 | 755 |
| 3 nichos, intensivo | 1.515 | 2.265 |

A estimativa é um **teto**: os filtros de inscritos e de e-mail rodam antes do
enriquecimento de recência, então o gasto real costuma ser menor. Quando uma
chave esgota, o pool rotaciona sozinho. A quota zera à meia-noite no Pacífico.

---

## Pedidos no X

A busca roda por um ator do Apify, porque a API oficial do X cobra US$ 200 por
mês para o mesmo acesso. Sete frases prontas (`"procuro editor"`, `"preciso de
um editor de vídeo"`, e por aí) saíram de uma busca real, não de um palpite.

**O teto de custo é um teto de verdade.** O limite vai na URL da execução, não
no corpo do pedido — foi o que a medição mostrou: pedindo 50 tweets, o ator
lia 422 e cobrava US$ 0,0955 contra um "custo máximo" anunciado de US$ 0,02.
Corrigido, pedir 50 lê 60 e cobra US$ 0,0050. O preço na tela é o medido
(US$ 0,25 por mil), não o da tabela.

**Nem todo mundo que fala em edição está contratando.** O maior ruído são
editores anunciando o próprio trabalho, que usam quase as mesmas palavras de
quem procura. `hiring.py` separa os dois e mostra, destacada na linha, a frase
que fez a classificação — dá para conferir o julgamento em vez de confiar
nele. Medido em 422 tweets reais: **76% de precisão e 100% de cobertura**. Um
em cada quatro "clientes" não é cliente; nenhum cliente de verdade é perdido.
A escolha é deliberada — deixar passar um lead custa mais do que descartar um
falso positivo na leitura.

O período pedido é um pedido, não uma garantia: o ator já devolveu post de duas
semanas numa busca de 7 dias. O score rebaixa esses, mas eles entram.

---

## Segurança

O app serve a interface e a API na mesma origem, em `127.0.0.1`, numa porta
sorteada a cada abertura. Sem senha — é a forma normal de um aplicativo de
desktop, e ela se apoia em garantias que valem a pena dizer em voz alta.

**O que está fechado**, cada item verificado atacando o próprio servidor:

| Ataque | Por que não funciona |
| --- | --- |
| Site qualquer lê a sua base | resposta sem cabeçalho CORS: o navegador segura a leitura |
| Site qualquer apaga a base | `DELETE` exige preflight, que este servidor nunca aprova |
| **Sequestro de DNS** | o Host é conferido: só `127.0.0.1` e `localhost` são respondidos |
| Injeção de SQL | todo valor vai por parâmetro; ordenação sai de lista fixa |
| XSS pelo texto de um tweet | React renderiza como texto; nada usa `innerHTML` |
| `href="javascript:"` vindo do scraper | `lib/links.ts` só deixa passar `http` e `https` |
| Ler arquivo fora da pasta | o servidor de estáticos recusa `..` |
| Chave vazar numa resposta | nenhuma rota devolve credencial inteira, só mascarada |

O sequestro de DNS era real: antes da correção, `DELETE /api/leads` com
`Host: outro-dominio` respondia 200 e apagava a base. O motivo é que a porta
sorteada não é defesa — uma página pode bater de porta em porta até uma
responder. O que ela não consegue é mentir no cabeçalho `Host`, que o navegador
escreve sozinho. Ver `backend/app/localonly.py`.

**As credenciais** ficam cifradas fora da pasta do programa, com a chave de
criptografia no cofre do próprio sistema — nunca ao lado do arquivo cifrado.
Nenhuma credencial entra no pacote distribuído nem no repositório.

**O que continua por sua conta:** o executável não tem assinatura digital
(certificado é pago), então o Windows e o macOS avisam na primeira abertura. E
quem usa a sua máquina com a sua conta de usuário abre o app e a base — a
fronteira aqui é a conta do sistema, não uma senha do Prospector.

---

## Score de oportunidade

Ordenar por inscritos não responde à pergunta que importa — canal gigante já
tem editor. O score (1–99) soma quatro sinais de 25 pontos:

| Sinal | O que mede |
| --- | --- |
| **reachability** | existe e-mail público para escrever |
| **rhythm** | frequência de publicação (mais vídeos, mais dor de edição) |
| **recency** | há quanto tempo publicou (canal parado não contrata) |
| **fit** | faixa de porte onde um editor é viável mas não é fixo |

A faixa-doce é 10k–300k inscritos. Acima de 800k a pontuação cai, porque a
chance de já existir equipe interna é alta.

Os pesos estão isolados em `scoring.py` como heurística inicial, prontos para
recalibrar quando houver dados reais de taxa de resposta.

---

## E-mail e redes: o que é possível de verdade

A API do YouTube **não** expõe o botão "E-mail" da aba Sobre — aquele endereço
fica atrás de um captcha e não é campo de nenhuma resposta. Nem o painel de
links. O que existe é **texto**: a descrição do canal e as descrições dos
vídeos.

- **E-mail** sai da descrição do canal. Sem endereço lá, o campo volta `null`.
  O sistema nunca adivinha padrões como `contato@nomedocanal.com`: endereço
  inventado quica e queima a reputação de quem envia.
- **Redes** saem também das descrições dos vídeos, que já são baixadas para
  montar a cadência — custo zero de quota a mais. Isso levou a cobertura de 2%
  para 20%. Um perfil só entra se **repetir em pelo menos 2 vídeos**: link de
  criador se repete em toda postagem, patrocínio pontual não.

Célula vazia significa "o canal não publicou", nunca "não fomos olhar".

---

## Enviar e-mails

A aba **Enviar e-mails** escreve para os canais da base que publicaram um
endereço. A mensagem sai da **sua** conta, por SMTP — não há serviço de envio
no meio, e a resposta volta para a mesma caixa de onde saiu.

**A conta.** Informe o e-mail e uma **senha de app** (não a senha da conta).
No Gmail: ative a verificação em duas etapas e gere a senha em
<https://myaccount.google.com/apppasswords>. Gmail, Outlook, Yahoo, iCloud e
Zoho são reconhecidos pelo endereço; para outro provedor, informe servidor e
porta. A senha fica cifrada em `tokens.json`, no mesmo cofre das chaves de API,
e nenhuma rota a devolve.

**A mensagem.** Um assunto e um texto, com quatro campos trocados por canal:
`{canal}`, `{handle}`, `{nicho}` e `{inscritos}`. A tela mostra a mensagem como
o primeiro destinatário vai receber, e **Enviar um teste para mim** manda a
mesma mensagem para o seu próprio endereço sem gastar um lead.

**O envio.** Você marca os canais, escolhe o intervalo e envia. As regras são
do backend, não da tela:

| Regra | Por quê |
| --- | --- |
| uma mensagem por destinatário | nunca uma lista em cópia: cada canal recebe a sua |
| teto por 24 horas (padrão 40, máximo 300) | muito envio igual de uma vez queima a caixa inteira |
| janela móvel, não dia do calendário | 40 às 23h50 e mais 40 às 00h10 seria a mesma rajada |
| o mesmo canal não recebe duas vezes | a base guarda `emailed_at`, e uma busca nova não apaga |
| falha não marca o lead | marcar esconderia um canal que não recebeu nada |

Cada canal enviado passa sozinho para **Contatado**. Sair da tela no meio
interrompe o envio.

Só a base de canais tem e-mail. Um pedido no X traz um perfil, não um endereço.

---

## Desenvolvimento

```bash
# testes
cd backend && .venv/Scripts/python -m pytest -q        # 257 testes

# interface
cd frontend && npx tsc --noEmit && npm run dev         # http://localhost:3000

# contraste da paleta, depois de mexer em globals.css
python tools/check-contrast.py
```

No modo `npm run dev` o Next sobe na porta 3000 e reescreve `/api/*` para o
Python na 8000 — é preciso subir o backend à parte (`uvicorn app.main:app`).
O modo desktop não usa nada disso.

---

## Conformidade

A busca de canais usa a YouTube Data API v3 oficial, com a chave do próprio
usuário e dentro da quota — o uso previsto pelos termos.

A busca de pedidos passa por um ator do Apify, com o token do próprio usuário.
Ela lê postagens públicas do X. A API oficial do X faria o mesmo por US$ 200
por mês; quem usa esta rota deve saber que ela não é o canal oficial e que os
termos do X são do X, não do Apify.

O contato comercial é responsabilidade de quem contata. No Brasil vale a LGPD:
identifique-se, informe como chegou ao contato e respeite pedidos de
descadastramento. Um e-mail publicado numa descrição de canal foi publicado
para contato — um perfil que pediu editor pediu que falassem com ele. Nenhum
dos dois é permissão para lista de disparo: o envio de e-mails do app manda uma
mensagem individual por canal, com teto diário, e o texto padrão já diz de onde
veio o endereço e como pedir para não receber mais. Tirar esse parágrafo é
decisão de quem envia, e a responsabilidade vai junto.

Não afiliado ao YouTube, ao Google, ao X nem ao Apify.
