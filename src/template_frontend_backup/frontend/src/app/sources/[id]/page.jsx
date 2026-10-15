import { fetchSource } from '@/lib/api';
import Link from 'next/link';
import { Inter } from 'next/font/google';
import Header from '@/components/Header';

const inter = Inter({ subsets: ['latin'], weight: ['400', '500', '600', '700', '800'] });

const t = {
  en: {
    back: "← Back to Sources",
    profile: "Editorial Profile",
    orientation: "Primary Orientation",
    confidence: "Orientation Confidence",
    evidence: "Classification Evidence",
    transparency: "Transparency & Ownership",
    owner: "Parent Company / Owner",
    affiliation: "Political Affiliation",
    reliability: "Reliability Rating",
    unknown: "Unknown",
    unknownOwner: "Unknown / Independent",
    noneDeclared: "None declared",
    unrated: "Unrated",
    noData: "Algorithmically derived from historical framing analysis.",
    noRelData: "Insufficient data to compute reliability profile."
  },
  ta: {
    back: "← ஆதாரங்களுக்குத் திரும்புக",
    profile: "தலையங்கப் சுயவிவரம்",
    orientation: "முதன்மை சார்பு",
    confidence: "சார்பு துல்லியம்",
    evidence: "வகைப்பாடு சான்று",
    transparency: "வெளிப்படைத்தன்மை & உரிமை",
    owner: "தாய் நிறுவனம் / உரிமையாளர்",
    affiliation: "அரசியல் சார்பு",
    reliability: "நம்பகத்தன்மை மதிப்பீடு",
    unknown: "தெரியவில்லை",
    unknownOwner: "தெரியவில்லை / சுயாதீன",
    noneDeclared: "எதுவும் இல்லை",
    unrated: "மதிப்பிடப்படவில்லை",
    noData: "வரலாற்றுச் செய்தி ஆய்விலிருந்து அல்காரிதம் மூலம் பெறப்பட்டது.",
    noRelData: "நம்பகத்தன்மை சுயவிவரத்தை கணக்கிட போதுமான தரவு இல்லை."
  }
};

export default async function SourcePage(props) {
  const { id } = await props.params;
  const searchParams = await props.searchParams;
  const lang = searchParams?.lang === 'ta' ? 'ta' : 'en';
  const strings = t[lang];
  let source = null;

  try {
    source = await fetchSource(id);
  } catch (err) {
    console.error(err);
    return <div style={{ color: '#dc2626', padding: '2rem' }}>Failed to load source details.</div>;
  }

  return (
    <div className={inter.className} style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#f7f5ef', color: '#171717', fontFamily: 'Inter, sans-serif', fontWeight: 600 }}>
      <Header lang={lang} activePage="sources" />
      <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '32px', width: '100%' }}>
        <header style={{ marginBottom: '32px' }}>
          <Link href={`/sources?lang=${lang}`} style={{ color: '#555', fontWeight: 600, fontSize: '0.78rem', marginBottom: '16px', display: 'inline-block', textDecoration: 'none' }}>
            {strings.back}
          </Link>
          <h1 style={{ fontSize: '2.5rem', fontWeight: 800, lineHeight: 1.3, marginBottom: '8px', color: '#111' }}>
            {source.name}
          </h1>
          <p style={{ color: '#666', fontSize: '1.1rem' }}>
            {source.domain}
          </p>
        </header>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '32px' }}>
          <div style={{ padding: '32px', backgroundColor: '#fff', border: '1px solid #d8d5ce', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '24px', color: '#111' }}>
              {strings.profile}
            </h2>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div>
                <div style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                  {strings.orientation}
                </div>
                <div style={{ display: 'inline-block' }}>
                  <span style={{
                    color: '#111',
                    fontWeight: 700,
                    fontSize: '1.1rem'
                  }}>
                    {source.orientation?.replace('_ORIENTED', '') || strings.unknown}
                  </span>
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                  {strings.confidence}
                </div>
                <div style={{
                  width: '100%',
                  height: '8px',
                  background: '#e5e7eb',
                  borderRadius: '4px',
                  overflow: 'hidden'
                }}>
                  <div style={{
                    width: `${(source.orientation_confidence || 0) * 100}%`,
                    height: '100%',
                    background: '#111'
                  }} />
                </div>
                <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '4px', textAlign: 'right' }}>
                  {Math.round((source.orientation_confidence || 0) * 100)}%
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                  {strings.evidence}
                </div>
                <p style={{ fontSize: '0.95rem', color: '#444', fontStyle: 'italic' }}>
                  "{source.orientation_evidence || strings.noData}"
                </p>
              </div>
            </div>
          </div>

          <div style={{ padding: '32px', backgroundColor: '#fff', border: '1px solid #d8d5ce', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '24px', color: '#111' }}>
              {strings.transparency}
            </h2>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              <div>
                <div style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                  {strings.owner}
                </div>
                <p style={{ fontSize: '1.05rem', color: '#111', fontWeight: 500 }}>
                  {source.ownership?.parent_company || strings.unknownOwner}
                </p>
              </div>

              <div>
                <div style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                  {strings.affiliation}
                </div>
                <p style={{ fontSize: '1.05rem', color: '#111' }}>
                  {source.ownership?.political_affiliation || strings.noneDeclared}
                </p>
              </div>

              <div>
                <div style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                  {strings.reliability}
                </div>
                <div style={{ display: 'inline-block', backgroundColor: '#f3f4f6', color: '#111', padding: '4px 8px', borderRadius: '4px', fontSize: '0.9rem', fontWeight: 'bold' }}>
                  {source.reliability?.rating || strings.unrated}
                </div>
                <p style={{ fontSize: '0.9rem', color: '#666', marginTop: '8px' }}>
                  {source.reliability?.notes || strings.noRelData}
                </p>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
