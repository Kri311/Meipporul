import React from 'react';
import Link from 'next/link';

export default function EventCard({ event }) {
  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', backgroundColor: '#fff', border: '1px solid #d2cec6' }}>
      {event.image_url && (
        <div style={{ width: '100%', height: '180px', position: 'relative', backgroundColor: '#dedbd4', marginBottom: '8px' }}>
          <img
            src={event.image_url}
            alt={event.title}
            style={{ objectFit: 'cover', width: '100%', height: '100%' }}
          />
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, lineHeight: 1.4, margin: 0 }}>
          <Link href={`/events/${event.id}`} style={{ transition: 'color 0.2s', textDecoration: 'none', color: '#171717' }}>
            <span>{event.title || 'Untitled Event'}</span>
          </Link>
        </h2>
      </div>
      
      {event.summary && (
        <p style={{ color: '#444', lineHeight: 1.6, fontSize: '0.95rem', margin: 0 }}>
          {event.summary}
        </p>
      )}
      
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px', alignItems: 'center' }}>
        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#77736c', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {event.article_count || 0} Articles
        </div>
        <Link href={`/events/${event.id}`}>
          <button style={{
            background: 'transparent',
            color: '#171717',
            border: '1px solid #171717',
            padding: '8px 16px',
            borderRadius: '4px',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem',
            transition: 'all 0.2s'
          }}>
            View Details →
          </button>
        </Link>
      </div>
    </div>
  );
}
