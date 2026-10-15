import React from 'react';
import Link from 'next/link';
import OrientationBar from './OrientationBar';

export default function EventCard({ event }) {
  // event contains: id, title, summary, source_count, article_count, coverage (matrix dict)
  
  return (
    <div className="glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, lineHeight: 1.4, margin: 0 }}>
          <Link href={`/events/${event.id}`} style={{ transition: 'color 0.2s' }}>
            <span className="text-gradient">{event.title || 'Untitled Event'}</span>
          </Link>
        </h2>
        
        <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
          <div className="badge" style={{ backgroundColor: 'var(--bg-surface-hover)', color: 'var(--text-secondary)' }}>
            {event.source_count || 0} Sources
          </div>
          <div className="badge" style={{ backgroundColor: 'var(--bg-surface-hover)', color: 'var(--text-secondary)' }}>
            {event.article_count || 0} Articles
          </div>
        </div>
      </div>
      
      {event.summary ? (
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '0.95rem' }}>
          {event.summary}
        </p>
      ) : (
        <p style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '0.9rem' }}>
          Summary generation pending...
        </p>
      )}
      
      <div style={{ marginTop: '8px' }}>
        <div style={{ marginBottom: '12px', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Media Coverage Distribution
        </div>
        <OrientationBar coverage={event.coverage} />
      </div>
      
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
        <Link href={`/events/${event.id}`}>
          <button style={{
            background: 'var(--brand-glow)',
            color: 'var(--brand-primary)',
            border: '1px solid var(--border-focus)',
            padding: '8px 16px',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem',
            transition: 'all 0.2s'
          }}>
            Analyze Perspectives →
          </button>
        </Link>
      </div>
    </div>
  );
}
