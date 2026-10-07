"use client";

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { fetchEvent } from '../../../lib/api';
import Header from '../../../components/Header';

const strings = {
  back: "← BACK TO NEWS",
  summary: "SUMMARY",
  loadingSummary: "Loading summary...",
  timeline: "RELATED ARTICLES",
  articles: "Total Articles",
  entities: "KEY ENTITIES",
  noEntities: "No entities extracted."
};

export default function EventPage(props) {
  const params = use(props.params);
  const searchParams = use(props.searchParams);
  
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  
  const id = params.id;
  const lang = searchParams?.lang || 'en';

  useEffect(() => {
    fetchEvent(id, lang).then(eventData => {
      setEvent(eventData);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, [id, lang]);

  if (loading) return <div style={{ padding: '50px', textAlign: 'center' }}>Loading...</div>;
  if (!event) return <div style={{ padding: '50px', textAlign: 'center' }}>Event not found.</div>;

  return (
    <div style={{ backgroundColor: '#efece4', minHeight: '100vh', fontFamily: 'var(--font-georgia), serif' }}>
      <style jsx global>{`
        .text-gradient {
          background: linear-gradient(90deg, #111, #444);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        @media (max-width: 900px) {
          .event-layout {
            grid-template-columns: 1fr !important;
          }
        }

        @media (max-width: 620px) {
          .event-main {
            padding: 24px 18px 48px !important;
          }

          .event-title {
            font-size: 2rem !important;
          }
        }
      `}</style>

      <Header lang={lang} activePage="home" tags={event?.tags || []} />

      <main className="event-main" style={{ maxWidth: '1200px', margin: '0 auto', padding: '32px', width: '100%', boxSizing: 'border-box' }}>
        <header
          style={{
            marginBottom: '32px',
            paddingBottom: '24px',
            borderBottom: '1px solid #171717',
          }}
        >
          <Link
            href={`/?lang=${lang}`}
            style={{
              color: '#555',
              fontWeight: 600,
              fontSize: '0.78rem',
              marginBottom: '18px',
              display: 'inline-block',
              textDecoration: 'none',
            }}
          >
            {strings.back}
          </Link>

          <h1
            className="event-title"
            style={{
              fontSize: '2.5rem',
              fontWeight: 600,
              lineHeight: 1.15,
              margin: 0,
              color: '#111',
              letterSpacing: '-0.04em',
            }}
          >
            {event.title}
          </h1>

          <div style={{ marginTop: '20px', maxWidth: '900px' }}>
            <div
              style={{
                fontSize: '0.72rem',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                fontWeight: 600,
                color: '#777',
                marginBottom: '8px',
              }}
            >
              {strings.summary}
            </div>

            {event.summary ? (
              <p style={{
                margin: 0,
                color: '#444',
                lineHeight: 1.65,
                fontSize: '1rem',
                wordBreak: 'break-word',
              }}>
                {event.summary.replace(/<[^>]*>?/gm, '')}
              </p>
            ) : (
              <p style={{ margin: 0, color: '#777', lineHeight: 1.65, fontSize: '1rem' }}>
                {strings.loadingSummary}
              </p>
            )}
          </div>
        </header>

        <div className="event-layout" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: '40px' }}>
          {/* Left Column: Articles */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
            <section>
              <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '16px', color: '#111' }}>{strings.timeline}</h2>
              <div style={{ padding: '24px', backgroundColor: 'transparent', borderTop: '1px solid #bdb9b0', borderBottom: '1px solid #bdb9b0' }}>
                {event.articles?.map((article, idx) => (
                  <div key={article.id} style={{
                    display: 'flex',
                    gap: '16px',
                    marginBottom: idx < event.articles.length - 1 ? '24px' : '0',
                    paddingBottom: idx < event.articles.length - 1 ? '24px' : '0',
                    borderBottom: idx < event.articles.length - 1 ? '1px solid #d1cec6' : 'none'
                  }}>
                    {article.image_url && (
                        <div style={{ width: '80px', height: '80px', flexShrink: 0, backgroundColor: '#dedbd4' }}>
                            <img src={article.image_url} alt="" style={{ objectFit: 'cover', width: '100%', height: '100%' }} />
                        </div>
                    )}
                    <div>
                      <a href={article.url} target="_blank" rel="noreferrer" style={{ fontFamily: 'var(--font-inter), sans-serif', fontWeight: 600, fontSize: '1rem', color: '#111', textDecoration: 'none' }}>
                        {article.title}
                      </a>
                      <div style={{ display: 'flex', gap: '12px', marginTop: '8px', fontSize: '0.85rem', color: '#6b7280', alignItems: 'center' }}>
                        <span style={{ fontWeight: '600' }}>{article.source_id}</span>
                        <span style={{ fontWeight: 'normal' }}>•</span>
                        <span style={{ fontWeight: 'normal' }}>{new Date(article.published_at).toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>

          {/* Right Column: Context & Metadata */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ padding: '24px', backgroundColor: 'transparent', borderTop: '1px solid #bdb9b0', borderBottom: '1px solid #bdb9b0' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '16px', color: '#111' }}>Overview</h3>
              <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', color: '#4b5563' }}>
                <span>Topic</span>
                <span style={{ fontWeight: 600, color: '#111', textTransform: 'capitalize' }}>{event.tags?.[0]?.replace(/_/g, ' ') || 'News'}</span>
              </div>
              <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', color: '#4b5563' }}>
                <span>{strings.articles}</span>
                <span style={{ fontWeight: 600, color: '#111' }}>{event.article_count}</span>
              </div>
            </div>

            <div style={{ padding: '24px', backgroundColor: 'transparent', borderTop: '1px solid #bdb9b0', borderBottom: '1px solid #bdb9b0' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '16px', color: '#111' }}>{strings.entities}</h3>
              {event.entities ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {event.entities.people?.length > 0 && (
                    <div>
                        <strong style={{ display: 'block', fontSize: '0.8rem', textTransform: 'uppercase', color: '#555', marginBottom: '8px' }}>People</strong>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                            {event.entities.people.map(p => (
                                <span key={p} style={{ backgroundColor: '#dedbd4', padding: '4px 8px', borderRadius: '4px', fontSize: '0.85rem' }}>{p}</span>
                            ))}
                        </div>
                    </div>
                  )}
                  {event.entities.locations?.length > 0 && (
                    <div>
                        <strong style={{ display: 'block', fontSize: '0.8rem', textTransform: 'uppercase', color: '#555', marginBottom: '8px' }}>Locations</strong>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                            {event.entities.locations.map(l => (
                                <span key={l} style={{ backgroundColor: '#dedbd4', padding: '4px 8px', borderRadius: '4px', fontSize: '0.85rem' }}>{l}</span>
                            ))}
                        </div>
                    </div>
                  )}
                </div>
              ) : (
                <p style={{ color: '#6b7280', fontSize: '0.95rem' }}>{strings.noEntities}</p>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
