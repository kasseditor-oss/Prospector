# Prospector

Aplicativo de desktop para achar canais do YouTube que provavelmente precisam
de um editor de vídeo. Busca por nicho, país e faixa de inscritos; lê o e-mail
e as redes sociais que o criador publicou; pontua a oportunidade; e guarda tudo
numa base local que cresce a cada busca.

Roda inteiro na sua máquina, com a **sua** chave da YouTube Data API, dentro da
quota diária que o Google já concede sem custo. Não há servidor, conta ou
mensalidade.

---

## Instalar

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

Em nenhum dos dois a sua base de canais é apagada junto.

### Sua chave da API

1. <https://console.cloud.google.com> → crie um projeto
2. **APIs e serviços → Biblioteca** → **YouTube Data API v3** → **Ativar**
3. **Credenciais → Criar credenciais → Chave de API** → copie
4. No app, aba **Chaves de API**, cole

Não precisa de cartão. Cada projeto rende 10.000 unidades por dia.

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
│   │   ├── schemas.py          validação dos filtros (Pydantic)
│   │   ├── youtube.py          cliente da API, e-mail e cadência
│   │   ├── socials.py          redes sociais publicadas pelo criador
│   │   ├── scoring.py          score de oportunidade
│   │   ├── keyring.py          pool de chaves, quota e rodízio
│   │   ├── store.py            onde as chaves ficam entre execuções
│   │   ├── secretbox.py        cifragem (DPAPI no Windows, Chaveiro no Mac)
│   │   ├── leads.py            a base de canais (SQLite)
│   │   └── paths.py            onde ficam os dados do usuário
│   ├── desktop.py            ponto de entrada do aplicativo
│   ├── packaging/            receitas do PyInstaller (Win/Mac), instalador, ícones
│   └── tests/                93 testes
├── frontend/                 Next.js 16 + React 19 (TypeScript)
│   ├── app/                    a interface (uma página só)
│   ├── components/
│   └── lib/api.ts              cliente tipado do backend
├── installer/                instalador e desinstalador
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
| `leads.db` | a base de canais (SQLite) |
| `keys.json` | suas chaves da API, cifradas |

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

## Desenvolvimento

```bash
# testes
cd backend && .venv/Scripts/python -m pytest -q        # 93 testes

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

A busca usa a YouTube Data API v3 oficial, com a chave do próprio usuário e
dentro da quota — o uso previsto pelos termos.

O envio de e-mail comercial é responsabilidade de quem envia. No Brasil vale a
LGPD: identifique-se, informe como chegou ao contato e respeite pedidos de
descadastramento.

Não afiliado ao YouTube nem ao Google.
