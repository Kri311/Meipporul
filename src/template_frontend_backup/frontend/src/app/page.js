import { Inter } from 'next/font/google';
import { fetchEvents, fetchBlindspots } from '@/lib/api';
import Link from 'next/link';
import Header from '@/components/Header';

const inter = Inter({ subsets: ['latin'], weight: ['400', '500', '600', '700', '800'] });

const t = {
  en: {
    home: "Home",
    blindspot: "Blindspot",
    sources: "Sources",
    search: "Search...",
    date: "Date",
    location: "Tamil Nadu, India",
    trending: "Trending Topics",
    noTrending: "No trending tags found",
    dailyBriefing: "Daily Briefing",
    stories: "stories",
    articles: "articles",
    noEvents: "No events",
    breakingNews: "Breaking News",
    noBreaking: "No breaking news",
    blindspotTitle: "Blindspot",
    blindspotDesc: "Stories disproportionately covered by one side of the political spectrum.",
    noBlindspots: "No active blindspots",
    maxGap: "Max gap",
    latestStories: "Latest Stories",
    topStories: "Top Stories",
    sourceLabel: "sources",
    dravidian: "Dravidian",
    aiadmk: "AIADMK",
    conservative: "Conservative",
    independent: "Independent",
  },
  ta: {
    home: "முகப்பு",
    blindspot: "கண்பார்வைக்கு அப்பால்",
    sources: "ஆதாரங்கள்",
    search: "தேடல்...",
    date: "தேதி",
    location: "தமிழ்நாடு, இந்தியா",
    trending: "டிரெண்டிங்",
    noTrending: "டிரெண்டிங் இல்லை",
    dailyBriefing: "தினசரி சுருக்கம்",
    stories: "செய்திகள்",
    articles: "கட்டுரைகள்",
    noEvents: "செய்திகள் இல்லை",
    breakingNews: "முக்கிய செய்திகள்",
    noBreaking: "முக்கிய செய்திகள் இல்லை",
    blindspotTitle: "தவறவிடப்பட்ட செய்தி",
    blindspotDesc: "அரசியல் களத்தின் ஒரு தரப்பினரால் மட்டுமே அதிக முக்கியத்துவம் கொடுத்து செய்தியாக்கப்பட்டவை.",
    noBlindspots: "கண்பார்வைக்கு எட்டாத பகுதி இல்லை",
    maxGap: "அதிகபட்ச இடைவெளி",
    latestStories: "சமீபத்திய செய்திகள்",
    topStories: "முன்னணி செய்திகள்",
    sourceLabel: "ஆதாரங்கள்",
    dravidian: "திராவிட",
    aiadmk: "அதிமுக",
    conservative: "பழமைவாத",
    independent: "சுயாதீன",
  }
};

export default async function Home(props) {
  const searchParams = await props.searchParams;
  const lang = searchParams?.lang === 'ta' ? 'ta' : 'en';
  const selectedTag = searchParams?.tag || null;
  const strings = t[lang];

  let events = [];
  let blindspotsData = { blindspots: [] };

  try {
    events = await fetchEvents(lang);
    if (selectedTag) {
      events = events.filter(e => e.tags && e.tags.includes(selectedTag));
    }
  } catch (err) {
    console.error("Error fetching events:", err);
  }

  try {
    blindspotsData = await fetchBlindspots(null, lang);
  } catch (err) {
    console.error("Error fetching blindspots:", err);
  }

  const blindspots = blindspotsData.blindspots || [];

  // Separate events for middle (hero) and left (daily briefings)
  const heroEvent = events.length > 0 ? events[0] : null;
  const briefingEvents = events.length > 1 ? events.slice(1, 15) : []; // Show up to 14 events

  // Extract trending tags from all events
  const allTags = events.flatMap(e => e.tags || []);
  const uniqueTags = [...new Set(allTags)].slice(0, 8);

  // Use a stable string for the date to prevent Hydration Error
  const formattedDate = "Today's Edition";

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
      <Header lang={lang} activePage="home" selectedTag={selectedTag} />

      {/* Main newspaper-style grid */}
      <main
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(240px, 1fr) minmax(420px, 2.05fr) minmax(250px, 1fr)',
          maxWidth: '1440px',
          width: '100%',
          margin: '0 auto',
          padding: '30px 32px 48px',
          flex: 1,
          alignItems: 'start',
          boxSizing: 'border-box',
        }}
      >
        {/* LEFT — Daily Briefing */}
        <section
          style={{
            paddingRight: '28px',
            borderRight: '1px solid #d2cec6',
            minWidth: 0,
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              borderBottom: '2px solid #171717',
              paddingBottom: '10px',
              marginBottom: '4px',
            }}
          >
            <h2
              style={{
                fontSize: '1.05rem',
                fontWeight: 800,
                margin: 0,
                letterSpacing: '-0.02em',
              }}
            >
              {strings.dailyBriefing}
            </h2>
            <span style={{ fontSize: '0.7rem', color: '#77736c', fontWeight: 600 }}>
              {events.length} {strings.stories}
            </span>
          </div>

          <div
            style={{
              fontSize: '0.7rem',
              color: '#77736c',
              padding: '9px 0 15px',
              borderBottom: '1px solid #d8d5ce',
            }}
          >
            {events.length} {strings.stories} · {events.length * 3} {strings.articles}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px', marginTop: '18px' }}>
            {briefingEvents.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#77736c', padding: '32px 0' }}>
                {strings.noEvents}
              </div>
            ) : (
            briefingEvents.map((evt, idx) => (
              <article
                key={evt.id}
                style={{
                  display: 'flex',
                  gap: '14px',
                  borderBottom: idx !== briefingEvents.length - 1 ? '1px solid #d2cec6' : 'none',
                  paddingBottom: idx !== briefingEvents.length - 1 ? '18px' : '0',
                }}
              >
                <div
                  style={{
                    width: '72px',
                    height: '72px',
                    position: 'relative',
                    flexShrink: 0,
                    backgroundColor: '#dedbd4',
                    overflow: 'hidden',
                  }}
                >
                  <img
                    src={evt.image_url || 'https://images.unsplash.com/photo-1572949645841-094f3a9c4c94?q=80&w=200&auto=format&fit=crop'}
                    alt={evt.title}
                    style={{ objectFit: 'cover', width: '100%', height: '100%' }}
                  />
                </div>
                <div>
                  <div style={{ fontSize: '0.68rem', color: '#77736c', marginBottom: '6px', fontWeight: 600 }}>
                    {evt.tags?.[0] || 'Local News'}
                  </div>
                  <Link href={`/events/${evt.id}?lang=${lang}`} style={{ textDecoration: 'none' }}>
                    <h3
                      style={{
                        fontSize: '0.92rem',
                        fontWeight: 700,
                        margin: 0,
                        color: '#171717',
                        lineHeight: 1.35,
                        letterSpacing: '-0.015em',
                      }}
                    >
                      {evt.title}
                    </h3>
                  </Link>
                  <div style={{ fontSize: '0.75rem', color: '#77736c', marginTop: '6px' }}>
                    {evt.source_count || 0} {strings.sourceLabel}
                  </div>
                </div>
              </article>
            ))
          )}
          </div>
        </section>

        {/* CENTER — Breaking / Top Story */}
        <section
          style={{
            padding: '0 30px',
            minWidth: 0,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '2px solid #171717',
              paddingBottom: '10px',
              marginBottom: '18px',
            }}
          >
            <h2
              style={{
                fontSize: '1.05rem',
                fontWeight: 800,
                margin: 0,
                letterSpacing: '-0.02em',
              }}
            >
              {strings.breakingNews}
            </h2>
            <span
              style={{
                fontSize: '0.68rem',
                color: '#77736c',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
              }}
            >
              {strings.topStories}
            </span>
          </div>

          {events.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
              {/* BREAKING NEWS: Render top 3 events here */}
              {events.slice(0, 3).map((breakingEvent) => (
                <article key={`breaking-${breakingEvent.id}`}>
                  <div
                    style={{
                      width: '100%',
                      height: '340px',
                      position: 'relative',
                      overflow: 'hidden',
                      backgroundColor: '#dedbd4',
                    }}
                  >
                    <img
                      src={breakingEvent.image_url || 'https://images.unsplash.com/photo-1572949645841-094f3a9c4c94?q=80&w=1200&auto=format&fit=crop'}
                      alt={breakingEvent.title}
                      style={{ objectFit: 'cover', width: '100%', height: '100%' }}
                    />

                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        background: 'linear-gradient(180deg, transparent 40%, rgba(0,0,0,0.82) 100%)',
                      }}
                    />

                    <div
                      style={{
                        position: 'absolute',
                        left: 0,
                        right: 0,
                        bottom: 0,
                        padding: '34px 28px 24px',
                      }}
                    >
                      <Link href={`/events/${breakingEvent.id}?lang=${lang}`} style={{ textDecoration: 'none' }}>
                        <h1
                          style={{
                            fontSize: 'clamp(1.3rem, 2.5vw, 1.8rem)',
                            fontWeight: 800,
                            color: '#fff',
                            margin: '0 0 16px',
                            lineHeight: 1.15,
                            letterSpacing: '-0.035em',
                          }}
                        >
                          {breakingEvent.title}
                        </h1>
                      </Link>

                      {/* Ground News-style bias bar */}
                      <div
                        style={{
                          display: 'flex',
                          width: '100%',
                          height: '7px',
                          overflow: 'hidden',
                          marginBottom: '9px',
                          backgroundColor: 'rgba(255,255,255,0.25)',
                        }}
                        aria-label="Coverage distribution"
                      >
                        {breakingEvent.bias?.dravidian > 0 && <div style={{ width: `${breakingEvent.bias.dravidian}%`, backgroundColor: '#c9362b' }} title={`${strings.dravidian} ${breakingEvent.bias.dravidian}%`} />}
                        {breakingEvent.bias?.aiadmk > 0 && <div style={{ width: `${breakingEvent.bias.aiadmk}%`, backgroundColor: '#f4f1e9' }} title={`${strings.aiadmk} ${breakingEvent.bias.aiadmk}%`} />}
                        {breakingEvent.bias?.conservative > 0 && <div style={{ width: `${breakingEvent.bias.conservative}%`, backgroundColor: '#3567b7' }} title={`${strings.conservative} ${breakingEvent.bias.conservative}%`} />}
                        {breakingEvent.bias?.independent > 0 && <div style={{ width: `${breakingEvent.bias.independent}%`, backgroundColor: '#171717' }} title={`${strings.independent} ${breakingEvent.bias.independent}%`} />}
                      </div>

                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(4, 1fr)',
                          fontSize: '0.72rem',
                          color: '#fff',
                          lineHeight: 1.2,
                        }}
                      >
                        <span>{strings.dravidian} {breakingEvent.bias?.dravidian || 0}%</span>
                        <span style={{ textAlign: 'center' }}>{strings.aiadmk} {breakingEvent.bias?.aiadmk || 0}%</span>
                        <span style={{ textAlign: 'center' }}>{strings.conservative} {breakingEvent.bias?.conservative || 0}%</span>
                        <span style={{ textAlign: 'right' }}>{strings.independent} {breakingEvent.bias?.independent || 0}%</span>
                      </div>
                    </div>
                  </div>

                  {/* Perspective labels — separated like Ground's comparison UI */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(4, 1fr)',
                      borderBottom: '1px solid #d2cec6',
                      borderLeft: '1px solid #d2cec6',
                      marginTop: '12px',
                    }}
                  >
                    {[
                      [strings.dravidian, '#c9362b'],
                      [strings.aiadmk, '#f4f1e9'],
                      [strings.conservative, '#3567b7'],
                      [strings.independent, '#171717'],
                    ].map(([label, color]) => (
                      <div
                        key={label}
                        style={{
                          padding: '11px 10px',
                          borderRight: '1px solid #d2cec6',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          color: '#3f3c37',
                          textAlign: 'center',
                        }}
                      >
                        <span
                          style={{
                            display: 'inline-block',
                            width: '7px',
                            height: '7px',
                            borderRadius: '50%',
                            backgroundColor: color,
                            marginRight: '6px',
                          }}
                        />
                        {label}
                      </div>
                    ))}
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      gap: '12px',
                      padding: '13px 0',
                      fontSize: '0.7rem',
                      color: '#77736c',
                      borderBottom: '1px solid #d2cec6',
                    }}
                  >
                    <span>{breakingEvent.tags?.[0] || 'Tamil Nadu'}</span>
                    <span>{breakingEvent.source_count || 0} {strings.sourceLabel}</span>
                  </div>
                </article>
              ))}

              {/* LATEST STORIES SECTION */}
              {events.length > 3 && (
                <div style={{ marginTop: '24px' }}>
                  <div
                    style={{
                      borderBottom: '2px solid #171717',
                      paddingBottom: '10px',
                      marginBottom: '18px',
                    }}
                  >
                    <h2
                      style={{
                        fontSize: '1.05rem',
                        fontWeight: 800,
                        margin: 0,
                        letterSpacing: '-0.02em',
                      }}
                    >
                      {strings.latestStories}
                    </h2>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    {events.slice(3, 10).map((latestEvent, idx) => (
                      <article
                        key={`latest-${latestEvent.id}`}
                        style={{
                          display: 'flex',
                          gap: '16px',
                          borderBottom: idx !== events.slice(3, 10).length - 1 ? '1px solid #d2cec6' : 'none',
                          paddingBottom: idx !== events.slice(3, 10).length - 1 ? '20px' : '0',
                        }}
                      >
                        <div
                          style={{
                            width: '120px',
                            height: '100px',
                            position: 'relative',
                            flexShrink: 0,
                            backgroundColor: '#dedbd4',
                            overflow: 'hidden',
                          }}
                        >
                          <img
                            src={latestEvent.image_url || 'https://images.unsplash.com/photo-1572949645841-094f3a9c4c94?q=80&w=400&auto=format&fit=crop'}
                            alt={latestEvent.title}
                            style={{ objectFit: 'cover', width: '100%', height: '100%' }}
                          />
                        </div>
                        <div>
                          <div style={{ fontSize: '0.68rem', color: '#77736c', marginBottom: '8px', fontWeight: 600 }}>
                            {latestEvent.tags?.[0] || 'Local News'}
                          </div>
                          <Link href={`/events/${latestEvent.id}?lang=${lang}`} style={{ textDecoration: 'none' }}>
                            <h3
                              style={{
                                fontSize: '1rem',
                                fontWeight: 700,
                                margin: 0,
                                color: '#171717',
                                lineHeight: 1.35,
                                letterSpacing: '-0.015em',
                              }}
                            >
                              {latestEvent.title}
                            </h3>
                          </Link>
                          <div style={{ fontSize: '0.75rem', color: '#77736c', marginTop: '8px' }}>
                            {latestEvent.source_count || 0} {strings.sourceLabel}
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div
              style={{
                color: '#77736c',
                padding: '50px 20px',
                textAlign: 'center',
                border: '1px solid #d2cec6',
                backgroundColor: '#f7f5ef',
              }}
            >
              {strings.noBreaking}
            </div>
          )}
        </section>

        {/* RIGHT — Blindspot */}
        <section
          style={{
            paddingLeft: '28px',
            borderLeft: '1px solid #d2cec6',
            minWidth: 0,
          }}
        >
          <div
            style={{
              borderBottom: '2px solid #171717',
              paddingBottom: '10px',
              marginBottom: '12px',
            }}
          >
            <h2
              style={{
                fontSize: '1.05rem',
                fontWeight: 800,
                color: '#171717',
                margin: 0,
                letterSpacing: '-0.02em',
              }}
            >
              {strings.blindspotTitle}
            </h2>
          </div>

          <p
            style={{
              fontSize: '0.73rem',
              color: '#77736c',
              margin: '0 0 18px',
              lineHeight: 1.45,
              fontWeight: 600,
            }}
          >
            {strings.blindspotDesc}
          </p>

          {blindspots.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                color: '#77736c',
                padding: '24px 12px',
                border: '1px solid #d2cec6',
              }}
            >
              {strings.noBlindspots}
            </div>
          ) : (
            blindspots.slice(0, 2).map((bs, i) => {
              const relatedEvent = events.find(e => e.id === bs.event_id);
              return (
                <article
                  key={i}
                  style={{
                    borderBottom: '1px solid #d2cec6',
                    paddingBottom: '18px',
                    marginBottom: '18px',
                  }}
                >
                  <div
                    style={{
                      position: 'relative',
                      width: '100%',
                      height: '145px',
                      overflow: 'hidden',
                      backgroundColor: '#dedbd4',
                    }}
                  >
                    <img
                      src={bs.image_url || 'https://images.unsplash.com/photo-1585829365295-ab7cd400c167?q=80&w=800&auto=format&fit=crop'}
                      alt={bs.event_title || 'Blindspot'}
                      style={{ objectFit: 'cover', width: '100%', height: '100%' }}
                    />
                  </div>

                  <div style={{ paddingTop: '12px' }}>
                    <div
                      style={{
                        display: 'inline-block',
                        color: '#77736c',
                        fontSize: '0.65rem',
                        fontWeight: 800,
                        textTransform: 'uppercase',
                        letterSpacing: '0.08em',
                        marginBottom: '8px',
                      }}
                    >
                      {strings.blindspotTitle}
                    </div>

                    <Link href={`/events/${bs.event_id}?lang=${lang}`} style={{ textDecoration: 'none' }}>
                      <h3
                        style={{
                          fontSize: '0.92rem',
                          fontWeight: 700,
                          color: '#171717',
                          margin: 0,
                          lineHeight: 1.3,
                          letterSpacing: '-0.015em',
                        }}
                      >
                        {bs.event_title || bs.description}
                      </h3>
                    </Link>

                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginTop: '11px',
                      }}
                    >
                      <div
                        style={{
                          fontSize: '0.68rem',
                          color: '#9a342d',
                          fontWeight: 700,
                        }}
                      >
                        {strings.maxGap}: {bs.source_group?.replace('_ORIENTED', '')}
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#77736c', fontWeight: 600 }}>
                        {relatedEvent?.source_count || 0} {strings.sourceLabel}
                      </div>
                    </div>
                  </div>
                </article>
              );
            })
          )}
        </section>
      </main>
    </div>
  );
}