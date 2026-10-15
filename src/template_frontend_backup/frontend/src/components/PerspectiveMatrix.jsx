import React from 'react';

export default function PerspectiveMatrix({ matrix }) {
  if (!matrix || Object.keys(matrix).length === 0) {
    return <div style={{ color: '#6b7280' }}>Matrix data not available</div>;
  }

  // matrix format:
  // {
  //   "DRAVIDIAN_ORIENTED": {
  //     "stance": { "support": 0.8, "oppose": 0.1, "neutral": 0.1 },
  //     "sentiment": { "positive": 0.7, "negative": 0.2, "neutral": 0.1 },
  //     "framing": { "Economic": 0.5, "Political Strategy": 0.4 }
  //   }, ...
  // }

  const orientations = Object.keys(matrix);
  // Collect all unique frames across all orientations
  const allFrames = new Set();
  orientations.forEach(o => {
    Object.keys(matrix[o].framing || {}).forEach(f => allFrames.add(f));
  });
  
  // Sort frames by highest average value across all groups
  const sortedFrames = Array.from(allFrames).sort((a, b) => {
    const avgA = orientations.reduce((sum, o) => sum + (matrix[o].framing?.[a] || 0), 0);
    const avgB = orientations.reduce((sum, o) => sum + (matrix[o].framing?.[b] || 0), 0);
    return avgB - avgA;
  }).slice(0, 5); // Only show top 5 frames for clean UI

  const formatPercent = (val) => `${Math.round((val || 0) * 100)}%`;

  return (
    <div style={{ padding: '24px', overflowX: 'auto', backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
      <h3 style={{ marginBottom: '16px', fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontWeight: 800, color: '#111' }}>Perspective Matrix</span>
      </h3>
      
      <table style={{ width: '100%', minWidth: '600px', borderCollapse: 'collapse', textAlign: 'left' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
            <th style={{ padding: '12px 8px', color: '#6b7280', fontWeight: 600 }}>Source Group</th>
            <th style={{ padding: '12px 8px', color: '#6b7280', fontWeight: 600 }}>Top Stance</th>
            <th style={{ padding: '12px 8px', color: '#6b7280', fontWeight: 600 }}>Top Sentiment</th>
            {sortedFrames.map(frame => (
              <th key={frame} style={{ padding: '12px 8px', color: '#6b7280', fontWeight: 600, fontSize: '0.85rem' }}>
                {frame}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {orientations.map(orientation => {
            const data = matrix[orientation];
            
            // Get top stance
            const stance = data.stance || {};
            const topStance = Object.entries(stance).sort((a, b) => b[1] - a[1])[0] || ['neutral', 1];
            
            // Get top sentiment
            const sentiment = data.sentiment || {};
            const topSentiment = Object.entries(sentiment).sort((a, b) => b[1] - a[1])[0] || ['neutral', 1];
            
            return (
              <tr key={orientation} style={{ borderBottom: '1px solid #e5e7eb' }}>
                <td style={{ padding: '16px 8px', fontWeight: 700, color: '#111' }}>
                  {orientation.replace('_ORIENTED', '')}
                </td>
                
                <td style={{ padding: '16px 8px' }}>
                  <span style={{ 
                    backgroundColor: '#f3f4f6',
                    color: '#374151',
                    border: '1px solid #d1d5db',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    fontSize: '0.8rem',
                    fontWeight: 'bold',
                    textTransform: 'uppercase'
                  }}>
                    {topStance[0]} {formatPercent(topStance[1])}
                  </span>
                </td>
                
                <td style={{ padding: '16px 8px' }}>
                  <span style={{ 
                    backgroundColor: '#f3f4f6',
                    color: '#374151',
                    border: '1px solid #d1d5db',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    fontSize: '0.8rem',
                    fontWeight: 'bold',
                    textTransform: 'uppercase'
                  }}>
                    {topSentiment[0]} {formatPercent(topSentiment[1])}
                  </span>
                </td>

                {sortedFrames.map(frame => {
                  const val = data.framing?.[frame] || 0;
                  const intensity = Math.min(1, val * 1.5); // Boost visual intensity
                  
                  return (
                    <td key={frame} style={{ padding: '16px 8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{ 
                          width: '24px', 
                          height: '24px', 
                          borderRadius: '4px',
                          background: `rgba(59, 130, 246, ${intensity})`,
                          border: '1px solid #93c5fd'
                        }} title={formatPercent(val)} />
                        <span style={{ fontSize: '0.85rem', color: val > 0.3 ? '#111' : '#9ca3af', fontWeight: val > 0.3 ? 600 : 400 }}>
                          {formatPercent(val)}
                        </span>
                      </div>
                    </td>
                  )
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
