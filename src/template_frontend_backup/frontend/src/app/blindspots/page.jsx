import { fetchBlindspots } from '@/lib/api';
import Link from 'next/link';
import { Inter } from 'next/font/google';
import Header from '@/components/Header';

const inter = Inter({ subsets: ['latin'], weight: ['400', '500', '600', '700', '800'] });

const t = {
  en: {
    home: "Home",
    blindspot: "Blindspot",
    sources: "Sources",
    title: "Blindspot",
    desc: "Stories disproportionately covered by one side of the political spectrum.",
    noData: "No blindspots detected currently. Check back later!",
    missing: "Missing",
    severity: "Severity",
    viewEvent: "View Event →",
    dravidian: "Dravidian",
    aiadmk: "AIADMK",
    conservative: "Conservative",
    independent: "Independent",
    detected: "Detected blindspots",
    coverageGap: "Coverage gap",
  },
  ta: {
    home: "முகப்பு",
    blindspot: "தவறவிடப்பட்ட செய்தி",
    sources: "ஆதாரங்கள்",
    title: "தவறவிடப்பட்ட செய்திகள்",
    desc: "அரசியல் களத்தின் ஒரு தரப்பினரால் அதிகமாக செய்தியாக்கப்பட்ட செய்திகள்.",
    noData: "தற்போது தவறவிடப்பட்ட செய்திகள் எதுவும் கண்டறியப்படவில்லை. பின்னர் மீண்டும் பார்க்கவும்!",
    missing: "குறைவாக செய்தியாக்கப்பட்டது",
    severity: "தீவிரம்",
    viewEvent: "நிகழ்வைக் காண்க",
    dravidian: "திராவிட",
    aiadmk: "அதிமுக",
    conservative: "பழமைவாத",
    independent: "சுயாதீன",
    detected: "கண்டறியப்பட்டவை",
    coverageGap: "செய்தி இடைவெளி",
  }
};

export default async function BlindspotPage(props) {
  const searchParams = await props.searchParams;
  const lang = searchParams?.lang === 'ta' ? 'ta' : 'en';
  const strings = t[lang];

  let data = { blindspots: [] };

  try {
    data = await fetchBlindspots(null, lang);
  } catch (err) {
    console.error(err);
  }

  const blindspots = data.blindspots || [];

  return (
    <div
      className={inter.className}
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: '#f7f5ef',
        color: '#171717',
        fontFamily: 'Inter, sans-serif',
        fontWeight: 600,
      }}
    >


      <style>{`
        @media (max-width: 900px) {
          .blindspot-row {
            grid-template-columns: 150px minmax(0, 1fr) 110px !important;
          }
        }

        @media (max-width: 700px) {
          .perspective-nav {
            flex-wrap: wrap;
            gap: 14px !important;
          }

          .perspective-nav-links {
            order: 3;
            width: 100%;
            height: auto !important;
            padding-bottom: 4px;
          }

          .blindspot-page-main {
            padding: 24px 18px 48px !important;
          }

          .blindspot-header-row {
            flex-direction: column;
            align-items: flex-start !important;
          }

          .blindspot-row {
            grid-template-columns: 1fr !important;
            min-height: 0 !important;
          }

          .blindspot-meta {
            border-right: none !important;
            border-bottom: 1px solid #b8b5ae;
            padding: 18px 0 !important;
            flex-direction: row !important;
            gap: 28px;
          }

          .blindspot-story {
            padding: 24px 0 !important;
          }

          .blindspot-action {
            border-left: none !important;
            border-top: 1px solid #d1d5db;
            padding: 14px 0 !important;
            justify-content: flex-start !important;
          }
        }
      `}</style>

      <Header lang={lang} activePage="blindspots" />


      {/*PAGE HEADER*/}
      <main
        className="blindspot-page-main"
        style={{
          maxWidth: '1200px',
          margin: '0 auto',
          padding: '32px',
          width: '100%',
          boxSizing: 'border-box',
        }}
      >
        <header
          style={{
            paddingTop: '0',
            paddingBottom: '24px',
            borderBottom: '1px solid #171717',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-end',
              justifyContent: 'space-between',
              gap: '24px',
            }}
          >
            <div>
              <h1
                style={{
                  margin: 0,
                  fontSize: '2.5rem',
                  lineHeight: 1.1,
                  fontWeight: 600,
                  letterSpacing: '-0.04em',
                  color: '#111',
                }}
              >
                {strings.title}
              </h1>

              <p
                style={{
                  margin: '14px 0 0',
                  maxWidth: '680px',
                  fontSize: '0.95rem',
                  lineHeight: 1.55,
                  fontWeight: 400,
                  color: '#666',
                }}
              >
                {strings.desc}
              </p>
            </div>

            <div
              style={{
                fontSize: '0.78rem',
                fontWeight: 600,
                color: '#555',
                whiteSpace: 'nowrap',
              }}
            >
              {blindspots.length} {strings.detected}
            </div>
          </div>
        </header>


        {/*BLINDSPOT FEED*/}
        <section style={{ marginTop: '0' }}>

          {blindspots.length === 0 ? (
            <div
              style={{
                padding: '70px 20px',
                textAlign: 'center',
                borderBottom: '1px solid #171717',
                color: '#666',
                fontSize: '0.9rem',
              }}
            >
              {strings.noData}
            </div>
          ) : (
            blindspots.map((bs, idx) => {

              const sourceGroup =
                bs.source_group?.replace('_ORIENTED', '') || 'Unknown';

              const score =
                typeof bs.score === 'number'
                  ? bs.score.toFixed(2)
                  : 'N/A';

              /*
               * We use the source group to determine the visual
               * location of the missing coverage indicator.
               *
               * This does NOT invent political percentages.
               */
              const isLeft =
                sourceGroup.toLowerCase().includes('dravidian');

              const isRight =
                sourceGroup.toLowerCase().includes('conservative');

              const isCenter =
                sourceGroup.toLowerCase().includes('aiadmk');

              return (
                <article
                  key={idx}
                  className="blindspot-row"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '190px minmax(0, 1fr) 150px',
                    minHeight: '190px',
                    borderBottom: '1px solid #b8b5ae',
                  }}
                >

                  {/* LEFT METADATA*/}
                  <div
                    className="blindspot-meta"
                    style={{
                      padding: '28px 24px 28px 0',
                      borderRight: '1px solid #b8b5ae',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>

                      <div
                        style={{
                          fontSize: '0.68rem',
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                          fontWeight: 600,
                          color: '#777',
                          marginBottom: '10px',
                        }}
                      >
                        {strings.missing}
                      </div>

                      <div
                        style={{
                          fontSize: '1rem',
                          fontWeight: 600,
                          color: '#111',
                          marginBottom: '22px',
                        }}
                      >
                        {sourceGroup}
                      </div>

                    </div>

                    <div>
                      <div
                        style={{
                          fontSize: '0.68rem',
                          textTransform: 'uppercase',
                          letterSpacing: '0.08em',
                          fontWeight: 600,
                          color: '#777',
                          marginBottom: '6px',
                        }}
                      >
                        {strings.severity}
                      </div>

                      <div
                        style={{
                          fontSize: '1.25rem',
                          fontWeight: 600,
                          color: '#b42318',
                        }}
                      >
                        {score}
                      </div>
                    </div>
                  </div>


                  {/*MAIN STORY*/}
                  <div
                    className="blindspot-story"
                    style={{
                      padding: '28px 32px',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'center',
                    }}
                  >

                    <div
                      style={{
                        fontSize: '0.68rem',
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                        color: '#888',
                        fontWeight: 600,
                        marginBottom: '12px',
                      }}
                    >
                      {strings.coverageGap}
                    </div>

                    <Link
                      href={`/events/${bs.event_id}?lang=${lang}`}
                      style={{
                        textDecoration: 'none',
                        color: '#111',
                      }}
                    >
                      <h2
                        style={{
                          margin: 0,
                          maxWidth: '760px',
                          fontSize: '1.45rem',
                          lineHeight: 1.25,
                          fontWeight: 600,
                          letterSpacing: '-0.025em',
                        }}
                      >
                        {bs.event_title || bs.description}
                      </h2>
                    </Link>

                    {/* Political spectrum */}
                    <div
                      style={{
                        marginTop: '24px',
                        maxWidth: '650px',
                      }}
                    >

                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '1fr 1fr 1fr',
                          height: '5px',
                          width: '100%',
                          borderRadius: '1px',
                          overflow: 'hidden',
                          backgroundColor: '#ddd',
                        }}
                      >
                        <div
                          style={{
                            backgroundColor: isLeft ? '#c9362b' : '#d7d4ce',
                          }}
                        />

                        <div
                          style={{
                            backgroundColor: isCenter ? '#f4f1e9' : '#d7d4ce',
                          }}
                        />

                        <div
                          style={{
                            backgroundColor: isRight ? '#3567b7' : '#d7d4ce',
                          }}
                        />
                      </div>

                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          marginTop: '7px',
                          fontSize: '0.65rem',
                          color: '#777',
                          fontWeight: 500,
                        }}
                      >
                        <span>{strings.dravidian}</span>
                        <span>{strings.aiadmk}</span>
                        <span>{strings.conservative}</span>
                      </div>

                    </div>
                  </div>


                  {/*RIGHT ACTION*/}
                  <div
                    className="blindspot-action"
                    style={{
                      padding: '28px 0 28px 24px',
                      borderLeft: '1px solid #b8b5ae',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'flex-end',
                    }}
                  >
                    <Link
                      href={`/events/${bs.event_id}?lang=${lang}`}
                      style={{
                        color: '#111',
                        textDecoration: 'none',
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {strings.viewEvent}
                    </Link>
                  </div>

                </article>
              );
            })
          )}

        </section>


        {/*FOOTER RULE*/}
        <div
          style={{
            marginTop: '32px',
            borderTop: '3px solid #111',
            paddingTop: '10px',
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: '0.65rem',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            fontWeight: 600,
            color: '#777',
          }}
        >
          <span>PERSPECTIVE LENS</span>
          <span>{strings.blindspot}</span>
        </div>

      </main>
    </div>
  );
}