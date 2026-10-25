'use client';

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="frame"><div className="app"><main className="screen screen--plain" role="alert">
      <div className="state">
        <h1>Something went wrong</h1>
        <p>The screen failed to load. Your data is unchanged.</p>
        <button type="button" className="btn btn--primary" onClick={reset}>Try again</button>
      </div>
    </main></div></div>
  );
}
