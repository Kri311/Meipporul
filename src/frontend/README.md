# Meiporul — Eye of Truth web client

The Next.js 16 / React 19 app presents event clusters in separate English and
Tamil lanes. Language selection is passed to the API and retained when opening
an event. The API returns native-language articles only; the UI does not claim
that sentence embeddings are translations.

## Start

From this directory:

```bash
bun run dev
```

The default web URL is http://localhost:3000. Start the FastAPI service
separately from the repository root (see the root README).

## API configuration

The frontend API client is src/lib/api.js. Set NEXT_PUBLIC_API_URL in the
frontend environment when the API is not at its configured local default.

## Main routes

- /?lang=en and /?lang=ta: language-specific event overview.
- /events/{id}?lang=en|ta: event summary, source timeline, and entities for the
  selected language.

The feed and event detail pages refresh data every 60 seconds while visible,
and refresh stale data when a hidden tab becomes visible again. This is an API
refresh only: RSS fetching and model enrichment run on the backend pipeline
schedule. Event pages read persisted article/event bullets, so opening a page
does not require a new summarizer generation.

The App Router page props are promises in this installed Next.js version;
follow the local Next.js API reference when changing route components.
