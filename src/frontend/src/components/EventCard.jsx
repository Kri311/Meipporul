import Link from "next/link";
import styles from "../app/page.module.css";

export default function EventCard({ event, lang = "en" }) {
  const query = "?lang=" + lang;
  return (
    <article className={styles.card}>
      {event.image_url && <Link href={"/events/" + event.id + query} className={styles.cardImageLink} aria-label={event.title || "Open event"}>
        <img className={styles.cardImage} src={event.image_url} alt="" loading="lazy" />
      </Link>}
      <div className={styles.cardTop}>
        <span className={styles.topicPill}>{(event.topic || "News").replace(/_/g, " ")}</span>
        <span className={styles.sourceCount}>{event.source_count || 0} {lang === "ta" ? "ஆதாரங்கள்" : "SOURCES"}</span>
      </div>
      <h3><Link href={"/events/" + event.id + query}>{event.title || (lang === "ta" ? "தலைப்பு இல்லை" : "Untitled event")}</Link></h3>
      {event.summary && <p className={styles.summary}>{event.summary}</p>}
      <div className={styles.cardBottom}>
        <span>{event.article_count || 0} {lang === "ta" ? "செய்திகள்" : "ARTICLES"}</span>
        <Link className={styles.readMore} href={"/events/" + event.id + query}>{lang === "ta" ? "நிகழ்வைப் பார்க்க" : "Explore event"} <span aria-hidden="true">↗</span></Link>
      </div>
    </article>
  );
}
