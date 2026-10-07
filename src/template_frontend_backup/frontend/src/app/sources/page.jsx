import { fetchSources } from '@/lib/api';
import Link from 'next/link';
import { Inter } from 'next/font/google';
import Header from '@/components/Header';

const inter = Inter({ subsets: ['latin'], weight: ['400', '500', '600', '700', '800'] });

const t = {
  en: {
    home: "Home",
    blindspot: "Blindspot",
    sources: "Sources",
    title: "Source Directory",
    desc: "Transparency, ownership, and historical editorial profiles of Tamil news publishers.",
    noData: "No sources available. Check database connection.",
    viewProfile: "View Profile →",
    unknown: "Unknown"
  },
  ta: {
    home: "முகப்பு",
    blindspot: "பார்வைக்குறைபாடு",
    sources: "ஆதாரங்கள்",
    title: "ஆதாரங்கள் அடைவு",
    desc: "தமிழ் செய்தி வெளியீட்டாளர்களின் வெளிப்படைத்தன்மை, உரிமை மற்றும் வரலாற்று தலையங்க விவரங்கள்.",
    noData: "ஆதாரங்கள் கிடைக்கவில்லை.",
    viewProfile: "விவரம் காண் →",
    unknown: "தெரியவில்லை"
  }
};

export default async function SourcesPage(props) {
  const searchParams = await props.searchParams;
  const lang = searchParams?.lang === 'ta' ? 'ta' : 'en';
  const strings = t[lang];
  let data = { sources: [] };
  
  try {
    data = await fetchSources();
  } catch (err) {
    console.error(err);
  }
  
  const sources = data.sources || [];

  return (
    <div className={inter.className} style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#f7f5ef', color: '#171717', fontFamily: 'Inter, sans-serif', fontWeight: 600 }}>
      <Header lang={lang} activePage="sources" />

      <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '32px', width: '100%' }}>
        <header style={{ marginBottom: '40px' }}>
          <h1 style={{ fontSize: '2.5rem', fontWeight: 800, color: '#111', letterSpacing: '-0.02em', marginBottom: '8px' }}>
            {strings.title}
          </h1>
          <p style={{ color: '#6b7280', fontSize: '1.1rem' }}>
            {strings.desc}
          </p>
        </header>
        
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '24px' }}>
          {sources.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#6b7280', gridColumn: '1 / -1', border: '1px solid #e5e7eb', borderRadius: '8px', backgroundColor: '#fff' }}>
              {strings.noData}
            </div>
          ) : (
            sources.map((source) => (
              <Link key={source.id} href={`/sources/${source.id}?lang=${lang}`} style={{ textDecoration: 'none' }}>
                <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', height: '100%', backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
                  <div>
                    <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#111', marginBottom: '4px' }}>
                      {source.name}
                    </h2>
                    <div style={{ color: '#6b7280', fontSize: '0.9rem' }}>
                      {source.domain}
                    </div>
                  </div>
                  
                  <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ 
                      backgroundColor: '#f3f4f6',
                      color: '#374151',
                      border: '1px solid #d1d5db',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      fontSize: '0.8rem',
                      fontWeight: 'bold'
                    }}>
                      {source.orientation?.replace('_ORIENTED', '') || strings.unknown}
                    </span>
                    <span style={{ color: '#111', fontSize: '0.85rem', fontWeight: 600 }}>
                      {strings.viewProfile}
                    </span>
                  </div>
                </div>
              </Link>
            ))
          )}
        </section>
      </main>
    </div>
  );
}
