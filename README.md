Client script functions

- performSearch(): POSTs to `/api/search` with `{ query, platform, limit }` and renders results.
- initiateDownload(): Starts a download for a URL via `/api/download` and polls progress.
- startDownload(url): Helper to start from a listed search result.
- pollProgress(downloadId): Polls `/api/progress/{id}` until complete or error.
- downloadFile(downloadId): GETs `/api/download/{id}` and triggers browser download.
- getLyrics(): Informational message; lyrics are saved server-side as `.lrc` if available.
