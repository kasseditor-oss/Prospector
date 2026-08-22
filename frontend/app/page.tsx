import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Icons } from "@/components/Icons";
import { CadenceStrip, TrendTag } from "@/components/CadenceStrip";

/**
 * Landing page. A Server Component: static copy, so none of it ships as JS.
 * Only the theme toggle is a Client Component.
 *
 * Kept deliberately short. The page has one job — convince an editor this
 * finds them clients, then get them into the app — so it carries the proof
 * (a real lead row), the four things they get, the three questions that
 * actually block a signup, and nothing else.
 */

/** A representative result. Invented channel, real shape. */
const SPECIMEN = {
  title: "Oficina do Marceneiro",
  handle: "@oficinadomarceneiro",
  country: "Brasil",
  subscribers: "84k",
  email: "contato@oficinadomarceneiro.com.br",
  score: 82,
  cadence: [2, 3, 2, 4, 3, 5, 4, 6, 5, 8, 7, 9],
  trend: 1.6,
  lastUpload: "3 dias",
};

const GETS = [
  {
    icon: "search",
    title: "Canais filtrados",
    body: "Por nicho, país e faixa de inscritos, em doze países.",
  },
  {
    icon: "mail",
    title: "O e-mail de contato",
    body: "O que o criador publicou na descrição do canal. Sem endereço inventado.",
  },
  {
    icon: "spark",
    title: "Quem está acelerando",
    body: "Doze meses de publicações em barras. Canal subindo é canal precisando de editor.",
  },
  {
    icon: "board",
    title: "Um funil para trabalhar",
    body: "Estágios, notas e exportação em CSV.",
  },
] as const;

const FAQ = [
  {
    q: "Por que é grátis?",
    a: "O custo real da prospecção é a chamada à API do YouTube, e ela roda na sua chave, dentro da quota gratuita que o Google já concede. Como não pagamos essa conta, não precisamos cobrar de você. Cada pessoa usa a própria chave e a própria quota.",
  },
  {
    q: "De onde vem o e-mail dos canais?",
    a: "Da descrição pública do canal, onde o criador escolheu publicar um contato comercial. O Prospector não quebra captcha, não adivinha endereço e não compra base de terceiros. Se o canal não publicou e-mail, a coluna fica vazia.",
  },
  {
    q: "Isso é permitido pelos termos do YouTube?",
    a: "A busca usa a YouTube Data API v3 oficial, com a sua chave e dentro da quota — o uso previsto. Do outro lado, quem envia e-mail comercial responde pela LGPD: identifique-se, diga como chegou ao contato e respeite pedidos de descadastramento.",
  },
];

export default function LandingPage() {
  return (
    <>
      <a className="skip" href="#conteudo">Pular para o conteúdo</a>

      <header className="transport">
        <div className="transport-in">
          <Link className="brand" href="/">
            <Icons.Logo />
            <span>Prospector</span>
          </Link>
          <div className="transport-tools" style={{ marginLeft: "auto" }}>
            <ThemeToggle />
            <Link className="btn btn-primary btn-sm" href="/app">
              Abrir o app
            </Link>
          </div>
        </div>
      </header>

      <main id="conteudo">
        <div className="wrap">
          <section className="hero">
            <div className="hero-copy">
              <p className="binlabel" style={{ marginBottom: "var(--s4)" }}>
                Prospecção para quem edita
              </p>
              <h1>
                Ache canais que já estão <em>afogados em vídeo</em>.
              </h1>
              <p className="lede">
                Busque canais do YouTube por nicho, país e faixa de inscritos. Você recebe
                o e-mail público de contato e vê quem está acelerando agora — que é quando
                um editor vira necessidade.
              </p>
              <div className="hero-cta">
                <Link className="btn btn-primary" href="/app">
                  Abrir o app
                </Link>
              </div>
              <p className="hero-note">
                <Icons.Shield size={15} />
                Grátis, sem cadastro. Você usa a sua própria chave da API do YouTube.
              </p>
            </div>

            {/* The proof: the product's actual output, at full size. */}
            <div className="thesis">
              <div className="thesis-head">
                <span className="binlabel">Um resultado, como ele chega</span>
                <span className="pill st-reply" style={{ marginLeft: "auto" }}>
                  e-mail público
                </span>
              </div>
              <div className="thesis-body">
                <div>
                  <p className="thesis-name">{SPECIMEN.title}</p>
                  <p className="ch-sub">
                    {SPECIMEN.handle} · {SPECIMEN.country} · {SPECIMEN.subscribers} inscritos
                  </p>
                  <p className="mailcell" style={{ marginTop: "var(--s3)", color: "var(--signal)" }}>
                    {SPECIMEN.email}
                  </p>
                  <div className="thesis-meta">
                    <div className="thesis-stat">
                      <p className="k">Score</p>
                      <p className="v">{SPECIMEN.score}</p>
                    </div>
                    <div className="thesis-stat">
                      <p className="k">Tendência</p>
                      <p className="v">
                        <TrendTag trend={SPECIMEN.trend} />
                      </p>
                    </div>
                    <div className="thesis-stat">
                      <p className="k">Último vídeo</p>
                      <p className="v">{SPECIMEN.lastUpload}</p>
                    </div>
                  </div>
                </div>
                <div>
                  <p className="binlabel" style={{ marginBottom: "var(--s3)" }}>
                    Cadência · 12 meses
                  </p>
                  <CadenceStrip
                    cadence={SPECIMEN.cadence}
                    trend={SPECIMEN.trend}
                    size="lg"
                    animate
                  />
                  <p style={{ marginTop: "var(--s3)", fontSize: 13, color: "var(--ink-2)" }}>
                    Dobrou o ritmo no último trimestre.
                  </p>
                </div>
              </div>
            </div>
          </section>

          <section className="sect">
            <p className="binlabel" style={{ marginBottom: "var(--s5)" }}>
              O que você recebe
            </p>
            <ul className="gets">
              {GETS.map((item) => (
                <li key={item.title}>
                  <Icons.ByName name={item.icon} size={18} />
                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section className="sect" id="faq">
            <p className="binlabel" style={{ marginBottom: "var(--s5)" }}>
              Antes de começar
            </p>
            <div className="faq">
              {FAQ.map((item, i) => (
                <details key={item.q} open={i === 0}>
                  <summary>{item.q}</summary>
                  <div className="ans">{item.a}</div>
                </details>
              ))}
            </div>
          </section>

          <section className="sect">
            <div className="closing">
              <div>
                <h2>Grátis, e continua grátis.</h2>
                <p>
                  Sem cartão e sem cadastro. O teto das suas buscas é a quota da sua
                  própria chave.
                </p>
              </div>
              <Link className="btn btn-primary" href="/app">
                Abrir o app
              </Link>
            </div>
          </section>
        </div>

        <footer>
          <div className="wrap foot-in">
            <span>Prospector — prospecção de canais do YouTube, de graça.</span>
            <span>Não afiliado ao YouTube nem ao Google.</span>
          </div>
        </footer>
      </main>
    </>
  );
}
