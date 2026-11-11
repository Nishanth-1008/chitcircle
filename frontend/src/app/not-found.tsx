import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="public__panel" style={{ minHeight: '100dvh' }}>
      <div className="state">
        <div className="state__icon" aria-hidden="true">?</div>
        <h3>Page not found</h3>
        <p>That page doesn’t exist, or the link is out of date.</p>
        <Link className="btn btn--primary" href="/app/home">Go to Home</Link>
      </div>
    </main>
  );
}
