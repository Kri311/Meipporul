'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';

export default function LanguageSwitcher({ currentLang }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const getUrl = (lang) => {
    const params = new URLSearchParams(searchParams);
    params.set('lang', lang);
    // Topic labels are localized (for example, "politics" vs "அரசியல்").
    // Carrying the current language's tag across makes the destination appear
    // empty when that label has no equivalent in the other language.
    params.delete('tag');
    return `${pathname}?${params.toString()}`;
  };

  return (
    <div style={{ display: 'flex', gap: '8px' }}>
      <Link
        href={getUrl('en')}
        style={{
          color: currentLang === 'en' ? 'var(--ink)' : 'var(--muted)',
          fontWeight: 700,
          textDecoration: 'none',
        }}
      >
        EN
      </Link>
      <Link
        href={getUrl('ta')}
        style={{
          color: currentLang === 'ta' ? 'var(--ink)' : 'var(--muted)',
          fontWeight: 700,
          textDecoration: 'none',
        }}
      >
        தமிழ்
      </Link>
    </div>
  );
}
