"use client";

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchEvents } from '../lib/api';
import Header from '../components/Header';

export default function Home({ searchParams }) {
  const [events, setEvents] = useState([]);
  const lang = searchParams?.lang || 'en';

  useEffect(() => {
    fetchEvents(lang).then(data => setEvents(data)).catch(console.error);
  }, [lang]);

  const latestEvent = events.length > 0 ? events[0] : null;

  return (
    <div style={{ backgroundColor: '#efece4', minHeight: '100vh', fontFamily: 'var(--font-georgia), serif' }}>
      <Header lang={lang} activePage="home" />

      <main style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: '32px',
        display: 'grid',
        gridTemplateColumns: '1fr',
        gap: '24px',
        boxSizing: 'border-box'
      }}>
        <section style={{ minWidth: 0 }}>
          <div style={{
            borderBottom: '2px solid #171717',
            paddingBottom: '10px',
            marginBottom: '20px',
          }}>
            <h2 style={{ fontSize: '1.8rem', fontWeight: 800, margin: 0, letterSpacing: '-0.02em', color: '#171717' }}>
              Top Stories
            </h2>
          </div>

          {events.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '30px' }}>
              {events.map((event, idx) => (
                <article key={event.id} style={{
                  display: 'flex',
                  gap: '20px',
                  borderBottom: idx !== events.length - 1 ? '1px solid #d2cec6' : 'none',
                  paddingBottom: idx !== events.length - 1 ? '30px' : '0',
                }}>
                  <div style={{ width: '250px', height: '160px', position: 'relative', flexShrink: 0, backgroundColor: '#dedbd4' }}>
                    <img
                      src={event.image_url || 'https://images.unsplash.com/photo-1572949645841-094f3a9c4c94?q=80&w=400&auto=format&fit=crop'}
                      alt={event.title}
                      style={{ objectFit: 'cover', width: '100%', height: '100%' }}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#77736c', textTransform: 'uppercase' }}>
                      {event.tags?.[0] || 'News'}
                    </span>
                    <Link href={`/events/${event.id}?lang=${lang}`} style={{ textDecoration: 'none' }}>
                      <h3 style={{ fontSize: '1.6rem', fontWeight: 800, margin: '8px 0', lineHeight: 1.2, letterSpacing: '-0.02em', color: '#171717' }}>
                        {event.title}
                      </h3>
                    </Link>
                    <div style={{ fontSize: '0.85rem', color: '#77736c', marginTop: '12px', fontWeight: 600 }}>
                      {event.source_count || 0} Related Articles
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div style={{ color: '#77736c', padding: '50px 20px', textAlign: 'center', border: '1px solid #d2cec6', backgroundColor: '#f7f5ef' }}>
              Loading stories...
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
