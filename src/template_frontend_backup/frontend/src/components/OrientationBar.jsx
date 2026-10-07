import React from 'react';

const BIAS_CONFIG = {
  DRAVIDIAN_ORIENTED: { id: 'Dravidian', label: 'Dravidian', color: '#c9362b', textColor: '#fff' },
  AIADMK_ORIENTED: { id: 'AIADMK', label: 'AIADMK', color: '#f4f1e9', textColor: '#111', border: '#e5e7eb' },
  CONSERVATIVE: { id: 'Conservative', label: 'Conservative', color: '#3567b7', textColor: '#fff' },
  POPULIST: { id: 'Independent', label: 'Independent', color: '#171717', textColor: '#fff' },
  OTHER_UNKNOWN: { id: 'Independent', label: 'Independent', color: '#171717', textColor: '#fff' }
};

export function getBias(orientation) {
  return BIAS_CONFIG[orientation] || BIAS_CONFIG.OTHER_UNKNOWN;
}

export default function OrientationBar({ coverage = {} }) {
  const total = Object.values(coverage).reduce((sum, count) => sum + count, 0);
  
  if (total === 0) {
    return <div style={{ fontSize: '0.85rem', color: '#6b7280' }}>No bias data available</div>;
  }

  // Group by Dravidian / AIADMK / Conservative / Independent
  const grouped = {
    Dravidian: { count: 0, config: BIAS_CONFIG.DRAVIDIAN_ORIENTED },
    AIADMK: { count: 0, config: BIAS_CONFIG.AIADMK_ORIENTED },
    Conservative: { count: 0, config: BIAS_CONFIG.CONSERVATIVE },
    Independent: { count: 0, config: BIAS_CONFIG.OTHER_UNKNOWN }
  };

  Object.entries(coverage).forEach(([key, count]) => {
    const bias = getBias(key);
    grouped[bias.id].count += count;
  });

  const orderedKeys = ['Dravidian', 'AIADMK', 'Conservative', 'Independent'];
  
  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', border: '1px solid #e5e7eb', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
      {/* Visual Bar */}
      <div style={{ display: 'flex', width: '100%', height: '12px' }}>
        {orderedKeys.map(key => {
          const item = grouped[key];
          if (item.count === 0) return null;
          const percent = (item.count / total) * 100;
          return (
            <div key={key} style={{ 
              width: `${percent}%`, 
              backgroundColor: item.config.color,
              borderTop: item.config.border ? `1px solid ${item.config.border}` : 'none',
              borderBottom: item.config.border ? `1px solid ${item.config.border}` : 'none',
              boxSizing: 'border-box'
            }} title={`${item.config.label}: ${Math.round(percent)}%`} />
          );
        })}
      </div>
      
      {/* Stats Legend Box */}
      <div style={{ display: 'flex', backgroundColor: '#f9fafb', padding: '16px 0' }}>
        {orderedKeys.map(key => {
          const item = grouped[key];
          const percent = Math.round((item.count / total) * 100);
          return (
            <div key={key} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', borderRight: key !== 'Others' ? '1px solid #e5e7eb' : 'none' }}>
              <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#111' }}>{percent}%</span>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', marginTop: '2px' }}>{item.config.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
