'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { PublicFrame } from '@/components/PublicFrame';
import { Banner, Button, Field, Wordmark } from '@/components/ui';
import { useAction } from '@/lib/hooks';
import { useSession } from '@/lib/session';

export default function SignIn() {
  const router = useRouter();
  const { signIn } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const submit = useAction(async () => {
    await signIn(email, password);
    router.replace('/app/home');
  });

  return (
    <PublicFrame>
      <form className="auth" onSubmit={(e) => { e.preventDefault(); void submit.run(); }} noValidate>
        <Wordmark large />
        <div>
          <h1>Welcome back</h1>
          <p className="muted">Sign in to your circles.</p>
        </div>
        <Field label="Email">
          {(id) => <input id={id} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />}
        </Field>
        <Field label="Password">
          {(id) => <input id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />}
        </Field>
        {submit.error && <Banner tone="danger">{submit.error}</Banner>}
        <Button block type="submit" disabled={submit.pending || !email || !password}>{submit.pending ? 'Signing in…' : 'Sign in'}</Button>
        <p className="auth__alt">New here? <Link className="link" href="/register">Create an account</Link></p>
      </form>
    </PublicFrame>
  );
}
