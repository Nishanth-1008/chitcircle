'use client';

export default function RootError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <main className="public__panel" style={{ minHeight: '100dvh' }}>
      <div className="state" role="alert">
        <div className="state__icon state__icon--danger" aria-hidden="true">!</div>
        <h3>Something went wrong</h3>
        <p>{error.message || 'An unexpected error occurred while showing this screen.'}</p>
        <button type="button" className="btn btn--primary" onClick={reset}>Try again</button>
      </div>
    </main>
  );
}
