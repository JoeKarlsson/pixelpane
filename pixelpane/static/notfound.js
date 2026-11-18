// The not-found page: just the header's status pill and the footer's version.
api('/api/health').then(showStatus).catch(() => {})
  .finally(() => { document.body.getBoundingClientRect(); document.documentElement.classList.remove('preload'); });   // transitions only after the first render
