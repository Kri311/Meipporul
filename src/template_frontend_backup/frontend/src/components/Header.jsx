import Link from 'next/link';
import { fetchEvents } from '@/lib/api';
import LanguageSwitcher from './LanguageSwitcher';

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

export default async function Header({ lang = 'en', activePage = 'home', selectedTag = null }) {
  const strings = t[lang] || t['en'];
  
  let events = [];
  try {
    events = await fetchEvents(lang);
  } catch (err) {
    console.error("Error fetching events for header:", err);
  }
  
  const allTags = events.flatMap(e => e.tags || []);
  const uniqueTags = [...new Set(allTags)].slice(0, 8);
  const formattedDate = "Today's Edition";

  return (
    <div style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Top Navigation */}
      <nav
        style={{
          display: 'flex',
          alignItems: 'center',
          minHeight: '64px',
          padding: '0 32px',
          borderBottom: '1px solid #d8d5ce',
          gap: '28px',
          backgroundColor: '#f7f5ef',
        }}
      >
        <Link
          href={`/?lang=${lang}`}
          style={{
            color: '#171717',
            textDecoration: 'none',
            fontSize: '1.25rem',
            fontWeight: 800,
            letterSpacing: '-0.04em',
            whiteSpace: 'nowrap',
          }}
        >
          PERSPECTIVE LENS
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
              color: activePage === 'home' ? '#171717' : '#66635d',
              textDecoration: 'none',
              padding: '22px 18px 20px',
              borderBottom: activePage === 'home' ? '2px solid #171717' : 'none',
            }}
          >
            {strings.home}
          </Link>
          <Link
            href={`/blindspots?lang=${lang}`}
            style={{
              color: activePage === 'blindspots' ? '#171717' : '#66635d',
              textDecoration: 'none',
              padding: '22px 18px 20px',
              borderBottom: activePage === 'blindspots' ? '2px solid #171717' : 'none',
            }}
          >
            {strings.blindspot}
          </Link>
          <Link
            href={`/sources?lang=${lang}`}
            style={{
              color: activePage === 'sources' ? '#171717' : '#66635d',
              textDecoration: 'none',
              padding: '22px 18px 20px',
              borderBottom: activePage === 'sources' ? '2px solid #171717' : 'none',
            }}
          >
            {strings.sources}
          </Link>
        </div>

        <div style={{ flex: 1 }} />

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '22px',
            color: '#5f5c56',
            fontSize: '0.78rem',
            whiteSpace: 'nowrap',
          }}
        >
          <div style={{ display: 'none' /* hidden on mobile typically but fine here */ }} className="desktop-only">{formattedDate}</div>
          <span style={{ color: '#b9b5ad' }} className="desktop-only">|</span>
          <span className="desktop-only">{strings.location}</span>
          <span style={{ color: '#b9b5ad' }} className="desktop-only">|</span>
          <LanguageSwitcher currentLang={lang} />
        </div>
      </nav>

      {/* Trending — Ground News style: restrained row with a rule above and below */}
      <section
        style={{
          borderBottom: '1px solid #d8d5ce',
          backgroundColor: '#f7f5ef',
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
          }}
        >
          <span
            style={{
              fontSize: '0.78rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: '#171717',
            }}
          >
            {strings.trending}
          </span>

          <div style={{ width: '1px', height: '18px', backgroundColor: '#c9c5bd', flexShrink: 0 }} />

          {uniqueTags.length > 0 ? (
            uniqueTags.map(tag => (
              <Link
                href={`/?tag=${encodeURIComponent(tag)}&lang=${lang}`}
                key={tag}
                style={{
                  textDecoration: 'none',
                  color: selectedTag === tag ? '#171717' : '#625f59',
                  fontWeight: selectedTag === tag ? 800 : 600,
                  fontSize: '0.82rem',
                }}
              >
                {tag}
              </Link>
            ))
          ) : (
            <span style={{ fontSize: '0.8rem', color: '#9b9892' }}>{strings.noTrending}</span>
          )}
        </div>
      </section>

      <style>{`
        @media (max-width: 800px) {
          .desktop-only { display: none !important; }
        }
      `}</style>
    </div>
  );
}
