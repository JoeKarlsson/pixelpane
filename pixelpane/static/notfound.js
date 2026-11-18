// The not-found page: just the header's status pill and the footer's version.
api('/api/health').then(showStatus).catch(() => {});
