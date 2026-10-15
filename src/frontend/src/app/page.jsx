"use client";

import { use, useEffect, useMemo, useState } from "react";
import { fetchEvents } from "../lib/api";
import Header from "../components/Header";
import EventCard from "../components/EventCard";
import styles from "./page.module.css";

const copy = {
  en: { eyebrow: "THE NEWS, IN CONTEXT", heading: "Follow the story, not just the headline.", intro: "Coverage from multiple newsrooms, brought together into one evolving event timeline.", loading: "Loading the latest event coverage…", empty: "No events are available in this language yet.", noMatches: "No news matches these filters.", search: "Search events or article headlines", date: "Published between", clear: "Clear filters", result: "matching events", failed: "We couldn’t load the news right now. Check that the backend API is running, then try again." },
  ta: { eyebrow: "செய்திகளைப் பின்னணியுடன் அறியுங்கள்", heading: "தலைப்பை மட்டும் அல்ல, நிகழ்வையும் தொடருங்கள்.", intro: "பல செய்தி நிறுவனங்களின் செய்திகளை ஒரே நிகழ்வு காலவரிசையில் காணுங்கள்.", loading: "சமீபத்திய நிகழ்வுகள் ஏற்றப்படுகின்றன…", empty: "இந்த மொழியில் நிகழ்வுகள் இன்னும் இல்லை.", noMatches: "இந்த வடிகட்டிகளுக்குப் பொருந்தும் செய்திகள் இல்லை.", search: "நிகழ்வு அல்லது செய்தித் தலைப்பைத் தேடுங்கள்", date: "வெளியிடப்பட்ட நாள்", clear: "வடிகட்டிகளை நீக்கு", result: "பொருந்தும் நிகழ்வுகள்", failed: "செய்திகளை ஏற்ற முடியவில்லை. பின்தள API இயங்குகிறதா எனச் சரிபார்த்து மீண்டும் முயலுங்கள்." },
};

const eventCache = new Map();
const EVENT_REFRESH_INTERVAL_MS = 60 * 1000;

function newestArticleTime(event) {
  return (event.articles || []).reduce((newest, article) => {
    const timestamp = Date.parse(article.published_at || "");
    return Number.isFinite(timestamp) ? Math.max(newest, timestamp) : newest;
  }, 0);
}

function isOtherTopic(topic, lang) {
  const normalized = String(topic || "").trim().toLocaleLowerCase(lang === "ta" ? "ta-IN" : "en-IN");
  return lang === "ta"
    ? normalized === "பிற செய்திகள்" || normalized === "மற்றவை"
    : normalized === "other" || normalized === "other current affairs";
}

function compareTopics(left, right, lang) {
  const leftIsOther = isOtherTopic(left, lang);
  const rightIsOther = isOtherTopic(right, lang);
  if (leftIsOther !== rightIsOther) return leftIsOther ? 1 : -1;
  return left.localeCompare(right, lang);
}

function getCachedEvents(lang) {
  const cached = eventCache.get(lang);
  return Array.isArray(cached) ? cached : null;
}

export default function Home({ searchParams }) {
  const query = use(searchParams);
  const lang = query?.lang === "ta" ? "ta" : "en";
  const selectedTag = query?.tag || "";
  const initialSearch = query?.q || "";
  const initialFrom = query?.from || "";
  const initialTo = query?.to || "";
  const strings = copy[lang];
  const [events, setEvents] = useState(() => getCachedEvents(lang) || []);
  const [status, setStatus] = useState(() => getCachedEvents(lang) === null ? "loading" : "ready");
  const [searchText, setSearchText] = useState(initialSearch);
  const [dateFrom, setDateFrom] = useState(initialFrom);
  const [dateTo, setDateTo] = useState(initialTo);

  useEffect(() => {
    setSearchText(initialSearch);
    setDateFrom(initialFrom);
    setDateTo(initialTo);
  }, [lang, selectedTag, initialSearch, initialFrom, initialTo]);

  const updateUrlFilters = (next) => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(next)) {
      if (value) params.set(key, value);
      else params.delete(key);
    }
    const queryString = params.toString();
    window.history.replaceState(null, "", queryString ? `/?${queryString}` : "/");
  };

  useEffect(() => {
    let active = true;
    const cached = getCachedEvents(lang);
    if (cached !== null) {
      setEvents(cached);
      setStatus("ready");
    }

    let refreshing = false;
    let lastSuccessAt = 0;
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        const data = await fetchEvents(lang);
        const freshEvents = Array.isArray(data) ? data : [];
        const previousEvents = eventCache.get(lang);
        const hasChanged = JSON.stringify(previousEvents) !== JSON.stringify(freshEvents);
        eventCache.set(lang, freshEvents);
        lastSuccessAt = Date.now();
        if (active) {
          if (hasChanged) setEvents(freshEvents);
          setStatus("ready");
        }
      } catch (error) {
        console.error(error);
        if (active && getCachedEvents(lang) === null) setStatus("error");
      } finally {
        refreshing = false;
      }
    };

    // Refresh on entry and then every minute. Hidden tabs may throttle
    // timers, so also refresh when the reader returns after the interval.
    refresh();
    const timer = window.setInterval(refresh, EVENT_REFRESH_INTERVAL_MS);
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible" && Date.now() - lastSuccessAt >= EVENT_REFRESH_INTERVAL_MS) {
        refresh();
      }
    };
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [lang]);

  const availableTopics = useMemo(
    () => new Set(events.map((event) => event.topic || (lang === "ta" ? "பொது செய்திகள்" : "General"))),
    [events, lang],
  );
  // Ignore stale/deep-linked filters when a topic is absent in this language.
  const activeTag = availableTopics.has(selectedTag) ? selectedTag : "";

  const topicScopedEvents = useMemo(
    () => events.filter((event) => !activeTag || event.topic === activeTag),
    [events, activeTag],
  );
  const availableDates = useMemo(() => {
    const dates = new Set();
    for (const event of topicScopedEvents) {
      for (const article of event.articles || []) {
        const day = String(article.published_at || "").slice(0, 10);
        if (/^\d{4}-\d{2}-\d{2}$/.test(day)) dates.add(day);
      }
    }
    return [...dates].sort();
  }, [topicScopedEvents]);
  const requestedLowerIndex = dateFrom ? availableDates.findIndex((date) => date >= dateFrom) : 0;
  const requestedUpperIndex = dateTo ? availableDates.findLastIndex((date) => date <= dateTo) : availableDates.length - 1;
  const lowerIndex = Math.max(0, requestedLowerIndex < 0 ? availableDates.length - 1 : requestedLowerIndex);
  const upperIndex = Math.max(lowerIndex, Math.max(0, requestedUpperIndex));
  const rangeStart = availableDates[lowerIndex] || "";
  const rangeEnd = availableDates[upperIndex] || "";
  const rangeSpan = Math.max(1, availableDates.length - 1);
  const dateIsFiltered = Boolean(dateFrom || dateTo);

  const filteredEvents = useMemo(() => {
    const needle = searchText.trim().toLocaleLowerCase(lang === "ta" ? "ta-IN" : "en-IN");
    const eventMatches = (event) => {
      if (!needle) return false;
      const text = [event.title, event.summary, ...(event.summary_bullets || [])]
        .filter(Boolean).join(" ").toLocaleLowerCase(lang === "ta" ? "ta-IN" : "en-IN");
      return text.includes(needle);
    };
    return topicScopedEvents.flatMap((event) => {
      const matchesEventText = eventMatches(event);
      const matchingArticles = (event.articles || []).filter((article) => {
        const publishedDate = String(article.published_at || "").slice(0, 10);
        if (dateIsFiltered && (!publishedDate || (rangeStart && publishedDate < rangeStart) || (rangeEnd && publishedDate > rangeEnd))) return false;
        if (!needle || matchesEventText) return true;
        const articleText = `${article.title || ""} ${article.source_id || ""}`
          .toLocaleLowerCase(lang === "ta" ? "ta-IN" : "en-IN");
        return articleText.includes(needle);
      });
      // A date/search filter must be supported by at least one real source row.
      if (dateIsFiltered || needle) {
        if (!matchingArticles.length) return [];
      }
      const sources = new Set(matchingArticles.map((article) => article.source_id).filter(Boolean));
      return [{
        ...event,
        article_count: matchingArticles.length || event.article_count,
        source_count: sources.size || event.source_count,
        filter_article_count: matchingArticles.length,
      }];
    }).sort((left, right) => newestArticleTime(right) - newestArticleTime(left));
  }, [topicScopedEvents, searchText, rangeStart, rangeEnd, dateIsFiltered, lang]);

  const topics = useMemo(() => {
    const grouped = new Map();
    for (const event of filteredEvents) {
      const topic = event.topic || (lang === "ta" ? "பொது செய்திகள்" : "General");
      grouped.set(topic, [...(grouped.get(topic) || []), event]);
    }
    return [...grouped.entries()]
      .map(([topic, topicEvents]) => [
        topic,
        [...topicEvents].sort((left, right) => newestArticleTime(right) - newestArticleTime(left)),
      ])
      .sort((a, b) => compareTopics(a[0], b[0], lang));
  }, [filteredEvents, lang]);

  const breakingNewsEvents = useMemo(
    () => filteredEvents.filter((event) => event.breaking_news)
      .sort((left, right) => newestArticleTime(right) - newestArticleTime(left)),
    [filteredEvents],
  );

  const headerTopics = useMemo(
    () => [...new Set(events.map((event) => event.topic).filter(Boolean))]
      .sort((left, right) => compareTopics(left, right, lang)),
    [events, lang],
  );

  const updateDateRange = (nextFromIndex, nextToIndex) => {
    if (!availableDates.length) return;
    const fromIndex = Math.max(0, Math.min(nextFromIndex, nextToIndex));
    const toIndex = Math.min(availableDates.length - 1, Math.max(nextFromIndex, nextToIndex));
    const nextFrom = availableDates[fromIndex];
    const nextTo = availableDates[toIndex];
    setDateFrom(nextFrom === availableDates[0] ? "" : nextFrom);
    setDateTo(nextTo === availableDates.at(-1) ? "" : nextTo);
    updateUrlFilters({
      from: nextFrom === availableDates[0] ? "" : nextFrom,
      to: nextTo === availableDates.at(-1) ? "" : nextTo,
    });
  };

  const clearFilters = () => {
    setSearchText("");
    setDateFrom("");
    setDateTo("");
    updateUrlFilters({ q: "", from: "", to: "" });
  };

  return (
    <div className={styles.shell} lang={lang}>
      <Header lang={lang} activePage="home" tags={headerTopics} selectedTag={activeTag} filters={{ q: searchText.trim(), from: dateFrom, to: dateTo }} />
      <main className={styles.main}>
        <section className={styles.hero}>
          <p className={styles.eyebrow}>{strings.eyebrow}</p>
          <h1>{strings.heading}</h1>
          <p className={styles.intro}>{strings.intro}</p>
          <div className={styles.heroMeta}><span>{lang === "ta" ? "தமிழ் / English" : "ENGLISH / தமிழ்"}</span><span>•</span><span>{events.length} {lang === "ta" ? "நிகழ்வுகள்" : "EVENTS"}</span></div>
        </section>

        <section className={styles.filters} aria-label={lang === "ta" ? "செய்தி வடிகட்டிகள்" : "News filters"}>
          <label className={styles.searchLabel}>
            <span className={styles.visuallyHidden}>{strings.search}</span>
            <span className={styles.searchIcon} aria-hidden="true">⌕</span>
            <input
              type="search"
              value={searchText}
              placeholder={strings.search}
              onChange={(event) => {
                const value = event.target.value;
                setSearchText(value);
                updateUrlFilters({ q: value.trim() });
              }}
            />
          </label>
          <div className={styles.dateFilter}>
            <div className={styles.filterHeading}>
              <span>{strings.date}</span>
              <span className={styles.dateReadout}>{rangeStart || "—"} <span aria-hidden="true">→</span> {rangeEnd || "—"}</span>
            </div>
            {availableDates.length ? (
              <div className={styles.rangeControl}>
                <div className={styles.rangeTrack}>
                  <span style={{ left: `${(lowerIndex / rangeSpan) * 100}%`, right: `${100 - (upperIndex / rangeSpan) * 100}%` }} />
                </div>
                <input
                  type="range" min="0" max={availableDates.length - 1} step="1" value={lowerIndex}
                  aria-label={lang === "ta" ? "தொடக்க வெளியீட்டு நாள்" : "Earliest publication date"}
                  disabled={availableDates.length < 2}
                  onChange={(event) => updateDateRange(Number(event.target.value), upperIndex)}
                  className={`${styles.rangeInput} ${lowerIndex > availableDates.length - 2 ? styles.rangeInputTop : ""}`}
                />
                <input
                  type="range" min="0" max={availableDates.length - 1} step="1" value={upperIndex}
                  aria-label={lang === "ta" ? "முடிவு வெளியீட்டு நாள்" : "Latest publication date"}
                  disabled={availableDates.length < 2}
                  onChange={(event) => updateDateRange(lowerIndex, Number(event.target.value))}
                  className={styles.rangeInput}
                />
              </div>
            ) : <span className={styles.noDates}>{lang === "ta" ? "வெளியீட்டு தேதிகள் இல்லை" : "No publication dates available"}</span>}
            <div className={styles.sliderEndpoints}><span>{availableDates[0] || ""}</span><span>{availableDates.at(-1) || ""}</span></div>
          </div>
          {(searchText || dateFrom || dateTo) && <button type="button" className={styles.clearFilters} onClick={clearFilters}>{strings.clear}</button>}
          <span className={styles.filterCount}>{filteredEvents.length} {strings.result}</span>
        </section>

        {status === "loading" && <div className={styles.state} role="status">{strings.loading}</div>}
        {status === "error" && <div className={styles.state} role="alert">{strings.failed}</div>}
        {status === "ready" && events.length === 0 && <div className={styles.state}>{strings.empty}</div>}
        {status === "ready" && events.length > 0 && topics.length === 0 && <div className={styles.state}>{strings.noMatches}</div>}

        {status === "ready" && breakingNewsEvents.length > 0 && (
          <section className={`${styles.topicSection} ${styles.breakingSection}`} id="breaking-news" aria-labelledby="breaking-news-heading">
            <div className={styles.sectionHeading}>
              <div>
                <p className={`${styles.eyebrow} ${styles.breakingEyebrow}`}>{lang === "ta" ? "பல செய்தி நிறுவனங்களின் உடனடி செய்திகள் · புதியது முதல்" : "MULTI-SOURCE COVERAGE · NEWEST FIRST"}</p>
                <h2 id="breaking-news-heading">{lang === "ta" ? "உடனடிச் செய்திகள்" : "Breaking News"}</h2>
              </div>
              <span>{breakingNewsEvents.length} {lang === "ta" ? "நிகழ்வுகள்" : "EVENTS"}</span>
            </div>
            <div className={styles.grid}>
              {breakingNewsEvents.map((event) => <EventCard key={`breaking-${event.id}`} event={event} lang={lang} filters={{ q: searchText.trim(), from: dateFrom, to: dateTo }} />)}
            </div>
          </section>
        )}

        {topics.map(([topic, topicEvents]) => (
          <section className={styles.topicSection} key={topic}>
            <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>{lang === "ta" ? "தலைப்பு" : "COVERAGE TOPIC"}</p><h2>{topic.replace(/_/g, " ")}</h2></div><span>{topicEvents.length} {lang === "ta" ? "நிகழ்வுகள்" : "EVENTS"}</span></div>
            <div className={styles.grid}>{topicEvents.map((event) => <EventCard key={event.id} event={event} lang={lang} filters={{ q: searchText.trim(), from: dateFrom, to: dateTo }} />)}</div>
          </section>
        ))}
      </main>
    </div>
  );
}
