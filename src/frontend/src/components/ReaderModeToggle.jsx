"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "veritasium-reader-theme";

export default function ReaderModeToggle({ lang = "en" }) {
  const [dark, setDark] = useState(false);
  const label = lang === "ta" ? (dark ? "ஒளி வாசிப்பு" : "இருள் வாசிப்பு") : (dark ? "Light reader" : "Dark reader");

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY) === "dark";
    setDark(saved);
    document.documentElement.dataset.readerTheme = saved ? "dark" : "light";
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.dataset.readerTheme = next ? "dark" : "light";
    window.localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
  };

  return (
    <button
      type="button"
      className="reader-mode-toggle"
      onClick={toggle}
      aria-pressed={dark}
      aria-label={label}
      title={label}
    >
      <span aria-hidden="true">{dark ? "☼" : "◐"}</span>
      <span>{label}</span>
    </button>
  );
}
