"use client";

import { use, useEffect, useMemo, useState } from "react";
import { fetchEvents } from "../lib/api";
import Header from "../components/Header";
import EventCard from "../components/EventCard";
import styles from "./page.module.css";

const copy = {
  en: { eyebrow: "THE NEWS, IN CONTEXT", heading: "Follow the story, not just the headline.", intro: "Coverage from multiple newsrooms, brought together into one evolving event timeline.", loading: "Loading the latest event coverage…", empty: "No events are available in this language yet.", failed: "We couldn’t load the news right now. Check that the backend API is running, then try again." },
  ta: { eyebrow: "செய்திகளைப் பின்னணியுடன் அறியுங்கள்", heading: "தலைப்பை மட்டும் அல்ல, நிகழ்வையும் தொடருங்கள்.", intro: "பல செய்தி நிறுவனங்களின் செய்திகளை ஒரே நிகழ்வு காலவரிசையில் காணுங்கள்.", loading: "சமீபத்திய நிகழ்வுகள் ஏற்றப்படுகின்றன…", empty: "இந்த மொழியில் நிகழ்வுகள் இன்னும் இல்லை.", failed: "செய்திகளை ஏற்ற முடியவில்லை. பின்தள API இயங்குகிறதா எனச் சரிபார்த்து மீண்டும் முயலுங்கள்." },
};

export default function Home({ searchParams }) {
  const query = use(searchParams);
  const lang = query?.lang === "ta" ? "ta" : "en";
  const selectedTag = query?.tag || "";
  const strings = copy[lang];
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    let active = true;
    setStatus("loading");
    fetchEvents(lang)
      .then((data) => { if (active) { setEvents(Array.isArray(data) ? data : []); setStatus("ready"); } })
      .catch((error) => { console.error(error); if (active) setStatus("error"); });
    return () => { active = false; };
  }, [lang]);

  const topics = useMemo(() => {
    const grouped = new Map();
    for (const event of events) {
      const topic = event.topic || (lang === "ta" ? "பொது செய்திகள்" : "General");
      if (selectedTag && topic !== selectedTag) continue;
      grouped.set(topic, [...(grouped.get(topic) || []), event]);
    }
    return [...grouped.entries()].sort((a, b) => a[0].localeCompare(b[0], lang));
  }, [events, lang, selectedTag]);

  return (
    <div className={styles.shell}>
      <Header lang={lang} activePage="home" tags={[...new Set(events.map((item) => item.topic).filter(Boolean))].slice(0, 8)} selectedTag={selectedTag} />
      <main className={styles.main}>
        <section className={styles.hero}>
          <p className={styles.eyebrow}>{strings.eyebrow}</p>
          <h1>{strings.heading}</h1>
          <p className={styles.intro}>{strings.intro}</p>
          <div className={styles.heroMeta}><span>{lang === "ta" ? "தமிழ் / English" : "ENGLISH / தமிழ்"}</span><span>•</span><span>{events.length} {lang === "ta" ? "நிகழ்வுகள்" : "EVENTS"}</span></div>
        </section>

        {status === "loading" && <div className={styles.state} role="status">{strings.loading}</div>}
        {status === "error" && <div className={styles.state} role="alert">{strings.failed}</div>}
        {status === "ready" && events.length === 0 && <div className={styles.state}>{strings.empty}</div>}
        {status === "ready" && events.length > 0 && topics.length === 0 && <div className={styles.state}>{lang === "ta" ? "இந்தத் தலைப்பில் நிகழ்வுகள் இல்லை." : "No events match this topic."}</div>}

        {topics.map(([topic, topicEvents]) => (
          <section className={styles.topicSection} key={topic}>
            <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>{lang === "ta" ? "தலைப்பு" : "COVERAGE TOPIC"}</p><h2>{topic.replace(/_/g, " ")}</h2></div><span>{topicEvents.length} {lang === "ta" ? "நிகழ்வுகள்" : "EVENTS"}</span></div>
            <div className={styles.grid}>{topicEvents.map((event) => <EventCard key={event.id} event={event} lang={lang} />)}</div>
          </section>
        ))}
      </main>
    </div>
  );
}
