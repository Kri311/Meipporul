'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';

export default function LanguageSwitcher({ currentLang }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const getUrl = (lang) => {
    const params = new URLSearchParams(searchParams);
    params.set('lang', lang);
    return `${pathname}?${params.toString()}`;
  };

  return (
    <div style={{ display: 'flex', gap: '8px' }}>
      <Link
        href={getUrl('en')}
        style={{
          color: currentLang === 'en' ? '#171717' : '#9b9892',
          fontWeight: 700,
          textDecoration: 'none',
        }}
      >
        EN
      </Link>
      <Link
        href={getUrl('ta')}
        style={{
          color: currentLang === 'ta' ? '#171717' : '#9b9892',
          fontWeight: 700,
          textDecoration: 'none',
        }}
      >
        தமிழ்
      </Link>
    </div>
  );
}
