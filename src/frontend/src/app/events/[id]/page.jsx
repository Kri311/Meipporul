"use client";

import { useEffect, useMemo, useState, use } from 'react';
import Link from 'next/link';
import { fetchEvent } from '../../../lib/api';
import Header from '../../../components/Header';

const strings = {
  en: { back: "← BACK TO NEWS", summary: "EVENT SUMMARY", loadingSummary: "Preparing summary…", timeline: "COVERAGE TIMELINE", articles: "Total articles", noArticles: "No articles match the selected search and publication dates.", clearTimelineFilters: "Show the full event timeline", overview: "Event overview", topic: "Topic", entities: "Named entities", noEntities: "No named entities were extracted for this event.", people: "People", organizations: "Organizations", locations: "Locations", events: "Events", dates: "Dates" },
  ta: { back: "← செய்திகளுக்குத் திரும்பு", summary: "நிகழ்வு சுருக்கம்", loadingSummary: "சுருக்கம் தயாராகிறது…", timeline: "செய்தி காலவரிசை", articles: "மொத்தச் செய்திகள்", noArticles: "தேர்ந்தெடுத்த தேடலுக்கும் வெளியீட்டு நாட்களுக்கும் பொருந்தும் செய்திகள் இல்லை.", clearTimelineFilters: "முழு நிகழ்வு காலவரிசையைக் காண்க", overview: "நிகழ்வு விவரம்", topic: "தலைப்பு", entities: "பெயரிடப்பட்ட உருப்படிகள்", noEntities: "இந்த நிகழ்வில் பெயரிடப்பட்ட உருப்படிகள் எதுவும் கண்டறியப்படவில்லை.", people: "நபர்கள்", organizations: "நிறுவனங்கள்", locations: "இடங்கள்", events: "நிகழ்வுகள்", dates: "தேதிகள்" }
};

const ENTITY_CATEGORIES = ['people', 'organizations', 'locations', 'events', 'dates'];

const EVENT_REFRESH_INTERVAL_MS = 60 * 1000;

export default function EventPage(props) {
  const params = use(props.params);
  const searchParams = use(props.searchParams);
  
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  
  const id = params.id;
  const lang = searchParams?.lang || 'en';
  const searchText = String(searchParams?.q || '').trim().toLocaleLowerCase(lang === 'ta' ? 'ta-IN' : 'en-IN');
  const dateFrom = String(searchParams?.from || '');
  const dateTo = String(searchParams?.to || '');
  const activeFilters = { q: searchParams?.q || '', from: dateFrom, to: dateTo };
  const backParams = new URLSearchParams({ lang });
  if (activeFilters.q) backParams.set('q', activeFilters.q);
  if (dateFrom) backParams.set('from', dateFrom);
  if (dateTo) backParams.set('to', dateTo);
  const labels = strings[lang] || strings.en;

  useEffect(() => {
    let active = true;
    let refreshing = false;
    let lastSuccessAt = 0;
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        const eventData = await fetchEvent(id, lang);
        lastSuccessAt = Date.now();
        if (active) {
          setEvent((current) => JSON.stringify(current) === JSON.stringify(eventData) ? current : eventData);
        }
      } catch (err) {
        console.error(err);
      } finally {
        refreshing = false;
        if (active) setLoading(false);
      }
    };
    refresh();
    const timer = window.setInterval(refresh, EVENT_REFRESH_INTERVAL_MS);
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastSuccessAt >= EVENT_REFRESH_INTERVAL_MS) refresh();
    };
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [id, lang]);

  const visibleArticles = useMemo(() => {
    if (!event) return [];
    const eventText = [event.title, event.summary, ...(event.summary_bullets || [])]
      .filter(Boolean).join(' ').toLocaleLowerCase(lang === 'ta' ? 'ta-IN' : 'en-IN');
    const queryMatchesEvent = Boolean(searchText && eventText.includes(searchText));
    return (event.articles || []).filter((article) => {
      const articleDate = String(article.published_at || '').slice(0, 10);
      if (dateFrom && (!articleDate || articleDate < dateFrom)) return false;
      if (dateTo && (!articleDate || articleDate > dateTo)) return false;
      if (!searchText || queryMatchesEvent) return true;
      return `${article.title || ''} ${article.source_id || ''}`
        .toLocaleLowerCase(lang === 'ta' ? 'ta-IN' : 'en-IN').includes(searchText);
    }).sort((left, right) => {
      const leftTime = Date.parse(left.published_at || '') || 0;
      const rightTime = Date.parse(right.published_at || '') || 0;
      return rightTime - leftTime;
    });
  }, [event, searchText, dateFrom, dateTo, lang]);

  if (loading) return <div style={{ padding: '50px', textAlign: 'center' }}>Loading...</div>;
  if (!event) return <div style={{ padding: '50px', textAlign: 'center' }}>Event not found.</div>;

  return (
    <div lang={lang} className="event-page" style={{ backgroundColor: 'var(--paper)', color: 'var(--ink)', minHeight: '100vh', fontFamily: 'var(--font-inter), sans-serif', fontWeight: 600 }}>
      <style jsx global>{`
        .text-gradient {
          background: linear-gradient(90deg, var(--ink), var(--muted));
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

      <Header lang={lang} activePage="home" tags={event?.tags || []} filters={activeFilters} />

      <main className="event-main" style={{ maxWidth: '1200px', margin: '0 auto', padding: '32px', width: '100%', boxSizing: 'border-box' }}>
        <header
          style={{
            marginBottom: '32px',
            paddingBottom: '24px',
            borderBottom: '1px solid var(--ink)',
          }}
        >
          <Link
            href={`/?${backParams.toString()}`}
            style={{
              color: 'var(--muted)',
              fontWeight: 600,
              fontSize: '0.78rem',
              marginBottom: '18px',
              display: 'inline-block',
              textDecoration: 'none',
            }}
          >
            {labels.back}
          </Link>

          {event.breaking_news && (
            <span style={{ display: 'block', width: 'fit-content', marginBottom: '12px', padding: '6px 9px', borderRadius: '2px', background: '#9f3128', color: '#fff', fontSize: '0.7rem', fontWeight: 700 }}>
              {lang === 'ta' ? 'உடனடிச் செய்தி' : 'BREAKING NEWS'}
            </span>
          )}

          <h1
            className="event-title"
            style={{
              fontSize: '2.5rem',
              fontWeight: 700,
              lineHeight: 1.3,
              margin: 0,
              color: 'var(--ink)',
              letterSpacing: '-0.02em',
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
                color: 'var(--muted)',
                marginBottom: '8px',
              }}
            >
              {labels.summary}
            </div>

            {event.summary_bullets?.length ? (
              <ul style={{ margin: 0, paddingLeft: '1.3rem', color: 'var(--summary-ink)', lineHeight: 1.8, fontSize: '1rem', fontWeight: 600 }}>
                {event.summary_bullets.map((bullet, index) => <li key={index} style={{ paddingLeft: '4px', marginBottom: '8px' }}>{bullet.replace(/<[^>]*>?/gm, '')}</li>)}
              </ul>
            ) : event.summary ? (
              <p style={{ margin: 0, color: 'var(--summary-ink)', lineHeight: 1.8, fontSize: '1rem', fontWeight: 600, wordBreak: 'break-word' }}>{event.summary.replace(/<[^>]*>?/gm, '')}</p>
            ) : (
              <p style={{ margin: 0, color: 'var(--muted)', lineHeight: 1.65, fontSize: '1rem' }}>
                {labels.loadingSummary}
              </p>
            )}
          </div>
        </header>

        <div className="event-layout" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: '40px' }}>
          {/* Left Column: Articles */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
            <section>
              <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '16px', color: 'var(--ink)' }}>{labels.timeline}</h2>
              <div style={{ padding: '24px', backgroundColor: 'transparent', borderTop: '1px solid var(--line-strong)', borderBottom: '1px solid var(--line-strong)' }}>
                {visibleArticles.length ? visibleArticles.map((article, idx) => (
                  <div key={article.id} style={{
                    display: 'flex',
                    gap: '16px',
                    marginBottom: idx < visibleArticles.length - 1 ? '24px' : '0',
                    paddingBottom: idx < visibleArticles.length - 1 ? '24px' : '0',
                    borderBottom: idx < visibleArticles.length - 1 ? '1px solid var(--line)' : 'none'
                  }}>
                    {article.image_url && (
                        <div style={{ width: '80px', height: '80px', flexShrink: 0, backgroundColor: 'var(--chip-bg)' }}>
                            <img src={article.image_url} alt="" style={{ objectFit: 'cover', width: '100%', height: '100%' }} />
                        </div>
                    )}
                    <div>
                      <a href={article.url} target="_blank" rel="noreferrer" style={{ fontFamily: 'var(--font-inter), sans-serif', fontWeight: 700, fontSize: '1rem', lineHeight: 1.65, color: 'var(--ink)', textDecoration: 'none' }}>
                        {article.title}
                      </a>
                      <div style={{ display: 'flex', gap: '12px', marginTop: '8px', fontSize: '0.85rem', color: 'var(--muted)', alignItems: 'center' }}>
                        <span style={{ fontWeight: '600' }}>{article.source_id}</span>
                        <span style={{ fontWeight: 'normal' }}>•</span>
                        <span style={{ fontWeight: 'normal' }}>{article.published_at ? new Date(article.published_at).toLocaleString(lang === 'ta' ? 'ta-IN' : 'en-IN') : ''}</span>
                        <span style={{ fontWeight: 'normal' }}>•</span>
                        <span>{article.read_time || '3m'}{lang === 'ta' ? ' வாசிப்பு' : ' read'}</span>
                      </div>
                    </div>
                  </div>
                )) : (
                  <div style={{ margin: 0, color: 'var(--muted)' }}>
                    <p style={{ margin: '0 0 8px' }}>{labels.noArticles}</p>
                    {(searchText || dateFrom || dateTo) && (
                      <Link href={`/events/${id}?lang=${lang}`} style={{ color: 'var(--green)', fontWeight: 700, textDecoration: 'underline' }}>
                        {labels.clearTimelineFilters}
                      </Link>
                    )}
                  </div>
                )}
              </div>
            </section>
          </div>

          {/* Right Column: Context & Metadata */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={{ padding: '24px', backgroundColor: 'transparent' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '16px', color: 'var(--ink)' }}>{labels.overview}</h3>
              <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', color: 'var(--muted)' }}>
                <span>{labels.topic}</span>
                <span style={{ fontWeight: 600, color: 'var(--ink)', textTransform: 'capitalize' }}>{event.tags?.[0]?.replace(/_/g, ' ') || 'News'}</span>
              </div>
            <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', color: 'var(--muted)' }}>
              <span>{labels.articles}</span>
              <span style={{ fontWeight: 600, color: 'var(--ink)' }}>{visibleArticles.length}</span>
            </div>
            </div>

            <section aria-labelledby="event-entities-heading" style={{ padding: '24px', backgroundColor: 'transparent' }}>
              <h3 id="event-entities-heading" style={{ fontSize: '1.2rem', fontWeight: 700, margin: '0 0 16px', color: 'var(--ink)' }}>{labels.entities}</h3>
              {ENTITY_CATEGORIES.some((category) => event.entities?.[category]?.length) ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {ENTITY_CATEGORIES.map((category) => {
                    const values = event.entities?.[category] || [];
                    if (!values.length) return null;
                    return (
                      <div key={category}>
                        <h4 style={{ margin: '0 0 8px', color: 'var(--muted)', fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.07em', textTransform: 'uppercase' }}>{labels[category]}</h4>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '7px' }}>
                          {values.map((value) => (
                            <span key={`${category}-${value}`} style={{ padding: '5px 9px', border: '1px solid var(--line)', borderRadius: '999px', background: 'var(--chip-bg)', color: 'var(--ink)', fontSize: '0.82rem', lineHeight: 1.4, overflowWrap: 'anywhere' }}>{value}</span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p style={{ margin: 0, color: 'var(--muted)', fontSize: '0.9rem', lineHeight: 1.6 }}>{labels.noEntities}</p>
              )}
            </section>

          </div>
        </div>
      </main>
    </div>
  );
}
