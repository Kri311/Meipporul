"use client";

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchEvent } from '../../../lib/api';
import Header from '../../../components/Header';

export default function EventPage({ params, searchParams }) {
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  
  const id = params.id;
  const lang = searchParams?.lang || 'en';

  useEffect(() => {
    fetchEvent(id, lang).then(data => {
      setEvent(data);
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
      <Header lang={lang} activePage="home" />

      <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '32px', width: '100%', boxSizing: 'border-box' }}>
        <header style={{ marginBottom: '32px', paddingBottom: '24px', borderBottom: '1px solid #171717' }}>
          <Link href={`/?lang=${lang}`} style={{ color: '#555', fontWeight: 600, fontSize: '0.78rem', marginBottom: '18px', display: 'inline-block', textDecoration: 'none' }}>
            ← BACK TO NEWS
          </Link>
          <h1 style={{ fontSize: '2.5rem', fontWeight: 600, lineHeight: 1.15, margin: 0, color: '#111', letterSpacing: '-0.04em' }}>
            {event.title}
          </h1>
        </header>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: '40px' }}>
          {/* Left Column: Timeline & Perspectives */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
            <section>
              <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '16px', color: '#111' }}>Articles in this Event</h2>
              <div style={{ padding: '24px', backgroundColor: 'transparent', borderTop: '1px solid #bdb9b0', borderBottom: '1px solid #bdb9b0' }}>
                {event.articles?.map((article, idx) => (
                  <div key={article.id} style={{
                    display: 'flex', gap: '16px', marginBottom: idx < event.articles.length - 1 ? '24px' : '0',
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
                      <div style={{ marginTop: '8px', fontSize: '0.85rem', color: '#6b7280' }}>
                        <span style={{ fontWeight: 'bold' }}>{article.source?.name}</span>
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
                <span style={{ fontWeight: 600, color: '#111' }}>{event.tags?.[0] || 'News'}</span>
              </div>
              <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', color: '#4b5563' }}>
                <span>Articles</span>
                <span style={{ fontWeight: 600, color: '#111' }}>{event.articles?.length || 0}</span>
              </div>
            </div>

            <div style={{ padding: '24px', backgroundColor: 'transparent', borderTop: '1px solid #bdb9b0', borderBottom: '1px solid #bdb9b0' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '16px', color: '#dc2626' }}>Key Entities</h3>
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
                <p style={{ color: '#6b7280', fontSize: '0.95rem' }}>No entities extracted.</p>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
