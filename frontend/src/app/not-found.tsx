import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="frame"><div className="app"><main className="screen screen--plain">
      <div className="state">
        <h1>Page not found</h1>
        <p>That page doesn’t exist. Head back to your circles.</p>
        <Link className="btn btn--primary" href="/app/home">Go to Home</Link>
      </div>
    </main></div></div>
  );
}
