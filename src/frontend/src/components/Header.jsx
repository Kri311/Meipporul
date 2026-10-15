import Link from 'next/link';

import LanguageSwitcher from './LanguageSwitcher';
import ReaderModeToggle from './ReaderModeToggle';

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
  }
};

export default function Header({ lang = 'en', activePage = 'home', selectedTag = null, tags = [], filters = {} }) {
  const strings = t[lang] || t['en'];
  
  const uniqueTags = tags || [];
  const formattedDate = "Today's Edition";

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navigation */}
      <nav
        className="header-navigation"
        style={{
          display: 'flex',
          alignItems: 'center',
          minHeight: '64px',
          padding: '0 32px',
          borderBottom: '1px solid var(--line)',
          gap: '28px',
          backgroundColor: 'var(--nav-bg)',
          color: 'var(--ink)',
        }}
      >
        <Link
          href={`/?lang=${lang}`}
          className="site-brand"
          style={{
            color: 'var(--ink)',
            textDecoration: 'none',
            fontSize: '1.25rem',
            fontWeight: 800,
            letterSpacing: '-0.04em',
            whiteSpace: 'nowrap',
            display: 'inline-flex',
            alignItems: 'center',
            lineHeight: 1,
          }}
        >
          <span style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            <span>MEIPORUL</span>
            <span style={{ fontSize: '0.52rem', fontWeight: 700, letterSpacing: '0.12em' }}>EYE OF TRUTH</span>
          </span>
        </Link>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            fontSize: '0.9rem',
            fontWeight: 600,
            height: '64px',
          }}
        >
          <Link
            href={`/?lang=${lang}`}
            style={{
              color: activePage === 'home' ? 'var(--ink)' : 'var(--muted)',
              textDecoration: 'none',
              padding: '22px 18px 20px',
              borderBottom: activePage === 'home' ? '2px solid var(--ink)' : 'none',
            }}
          >
            {strings.home}
          </Link>
        </div>

        <div style={{ flex: 1 }} />

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '22px',
            color: 'var(--muted)',
            fontSize: '0.78rem',
            whiteSpace: 'nowrap',
          }}
        >
          <div style={{ display: 'none' /* hidden on mobile typically but fine here */ }} className="desktop-only">{formattedDate}</div>
          <span style={{ color: 'var(--line-strong)' }} className="desktop-only">|</span>
          <span className="desktop-only">{strings.location}</span>
          <span style={{ color: 'var(--line-strong)' }} className="desktop-only">|</span>
          <LanguageSwitcher currentLang={lang} />
          <ReaderModeToggle lang={lang} />
        </div>
      </nav>

      {/* Trending — Ground News style: restrained row with a rule above and below */}
      <section
        style={{
          borderBottom: '1px solid var(--line)',
          backgroundColor: 'var(--nav-bg)',
          color: 'var(--ink)',
          padding: '18px 32px 17px',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '20px',
            overflowX: 'auto',
            whiteSpace: 'nowrap',
            paddingBottom: '8px',
          }}
        >
          <span
            style={{
              fontSize: '0.78rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: 'var(--ink)',
            }}
          >
            {strings.trending}
          </span>

          <div style={{ width: '1px', height: '18px', backgroundColor: 'var(--line-strong)', flexShrink: 0 }} />

          {uniqueTags.length > 0 ? (
            uniqueTags.map(tag => (
              <Link
                href={(() => {
                  const params = new URLSearchParams({ tag, lang });
                  if (filters.q) params.set('q', filters.q);
                  if (filters.from) params.set('from', filters.from);
                  if (filters.to) params.set('to', filters.to);
                  return `/?${params.toString()}`;
                })()}
                key={tag.replace(/_/g, ' ')}
                style={{
                  textDecoration: 'none',
                  color: selectedTag === tag ? 'var(--ink)' : 'var(--muted)',
                  fontWeight: selectedTag === tag ? 800 : 600,
                  fontSize: '0.82rem',
                }}
              >
                {tag.replace(/_/g, ' ')}
              </Link>
            ))
          ) : (
            <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>{strings.noTrending}</span>
          )}
        </div>
      </section>

      <style>{`
        @media (max-width: 800px) {
          .desktop-only { display: none !important; }
        }
        @media (max-width: 620px) {
          .header-navigation { padding: 0 16px !important; gap: 14px !important; }
        }
      `}</style>
    </div>
  );
}
