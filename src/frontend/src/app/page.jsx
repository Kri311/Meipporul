"use client";

import { useEffect, useState, use } from 'react';
import { fetchEvents, fetchMetadata } from '../lib/api';
import Header from '../components/Header';
import EventCard from '../components/EventCard';

export default function Home(props) {
  const searchParams = use(props.searchParams);
  const [events, setEvents] = useState([]);
  const [metadata, setMetadata] = useState(null);
  const lang = searchParams?.lang || 'en';

  useEffect(() => {
    fetchEvents(lang).then(data => setEvents(data)).catch(console.error);
    fetchMetadata().then(data => setMetadata(data)).catch(console.error);
  }, [lang]);

  const uniqueTags = [...new Set(events.flatMap(e => e.tags || []))].slice(0, 8);
  const selectedTag = searchParams?.tag || null;

  // Group events by topic
  const groupedEvents = events.reduce((acc, event) => {
    const t = event.topic || 'General';
    if (!acc[t]) acc[t] = [];
    acc[t].push(event);
    return acc;
  }, {});

  const PRIORITY = {
    'world_news': 1, 'world news': 1, 'உலக செய்திகள்': 1,
    'politics': 2, 'அரசியல்': 2,
    'economy': 3, 'பொருளாதாரம்': 3,
    'science_health': 4, 'அறிவியல் & சுகாதாரம்': 4,
    'education': 5, 'கல்வி': 5,
    'sports': 6, 'விளையாட்டு': 6,
    'crime_law': 7, 'குற்றம் & சட்டம்': 7,
    'general': 8, 'பொது செய்திகள்': 8,
    'news': 8, 'செய்திகள்': 8
  };

  const sortedTopics = Object.entries(groupedEvents)
    .filter(([topic]) => !selectedTag || topic === selectedTag)
    .sort(([a], [b]) => {
      const pA = PRIORITY[a] || 99;
      const pB = PRIORITY[b] || 99;
      return pA - pB;
    });

  return (
    <div style={{ backgroundColor: '#efece4', minHeight: '100vh', fontFamily: 'var(--font-georgia), serif' }}>
      <Header lang={lang} activePage="home" tags={uniqueTags} />

      <main style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: '32px',
        display: 'flex',
        flexDirection: 'column',
        gap: '48px',
        boxSizing: 'border-box'
      }}>
        {metadata && (
          <div style={{ padding: '16px', backgroundColor: '#e2dfd8', border: '1px solid #d2cec6', fontSize: '0.85rem', color: '#555', display: 'flex', justifyContent: 'space-between', borderRadius: '4px' }}>
            <div><strong>Version:</strong> {metadata.version}</div>
            <div><strong>NER Model:</strong> {metadata.models.ner}</div>
            <div><strong>Embeddings:</strong> {metadata.models.embeddings}</div>
            <div><strong>Status:</strong> {metadata.pipeline_status}</div>
          </div>
        )}

        {events.length > 0 ? (
          sortedTopics.map(([topic, topicEvents]) => (
            <section key={topic} style={{ minWidth: 0 }}>
              <div style={{
                borderBottom: '3px solid #171717',
                paddingBottom: '12px',
                marginBottom: '24px',
              }}>
                <h2 style={{ fontSize: '2.2rem', fontWeight: 800, margin: 0, letterSpacing: '-0.02em', color: '#171717', textTransform: 'capitalize' }}>
                  {topic.replace(/_/g, ' ')}
                </h2>
                <div style={{ fontSize: '0.9rem', color: '#777', marginTop: '8px' }}>
                  {topicEvents.length} Clustered Events
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '30px' }}>
                {topicEvents.map((event) => (
                  <EventCard key={event.id} event={event} />
                ))}
              </div>
            </section>
          ))
        ) : (
          <div style={{ color: '#77736c', padding: '100px 20px', textAlign: 'center', fontSize: '1.2rem' }}>
            Loading vast knowledge base...
          </div>
        )}
      </main>
    </div>
  );
}
