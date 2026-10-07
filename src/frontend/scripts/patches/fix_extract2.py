with open('extracted_events_page.txt', 'r') as f:
    lines = f.readlines()

content = "".join(lines)
body = content.split('<truncated 1 lines>')[1].split('====================')[0].strip()

header = """"use client";

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchEvent, fetchMatrix, fetchBlindspots } from '../../../lib/api';
import Header from '../../../components/Header';
import PerspectiveMatrix from '../../../components/PerspectiveMatrix';
import OrientationBar from '../../../components/OrientationBar';

const strings = {
  back: "← BACK TO NEWS",
  summary: "SUMMARY",
  loadingSummary: "Loading summary...",
  analysis: "PERSPECTIVE ANALYSIS",
  timeline: "RELATED ARTICLES",
  coverage: "MEDIA COVERAGE",
  articles: "Total Articles",
  sources: "Total Sources",
  blindspots: "KEY ENTITIES",
  noBlindspots: "No entities extracted.",
  level: "LEVEL"
};

function getBias(orientation) {
  if (orientation === 'LEFT') return { label: 'Left', color: '#3b82f6', textColor: '#fff' };
  if (orientation === 'RIGHT') return { label: 'Right', color: '#ef4444', textColor: '#fff' };
  return { label: 'Center', color: '#f3f4f6', textColor: '#374151', border: '#d1d5db' };
}

export default function EventPage({ params, searchParams }) {
  const [event, setEvent] = useState(null);
  const [matrix, setMatrix] = useState(null);
  const [blindspots, setBlindspots] = useState([]);
  const [loading, setLoading] = useState(true);
  
  const id = params.id;
  const lang = searchParams?.lang || 'en';

  useEffect(() => {
    Promise.all([
      fetchEvent(id, lang),
      fetchMatrix(id, lang),
      fetchBlindspots(id, lang)
    ]).then(([eventData, matrixData, blindspotsData]) => {
      setEvent(eventData);
      setMatrix(matrixData);
      setBlindspots(blindspotsData);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, [id, lang]);

  if (loading) return <div style={{ padding: '50px', textAlign: 'center' }}>Loading...</div>;
  if (!event) return <div style={{ padding: '50px', textAlign: 'center' }}>Event not found.</div>;

  return (
    <div style={{ backgroundColor: '#efece4', minHeight: '100vh', fontFamily: 'var(--font-georgia), serif' }}>
      <style jsx global>{`
"""
with open('frontend/src/app/events/[id]/page.jsx', 'w') as out:
    out.write(header + body)
print("Restored!")
