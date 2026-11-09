'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { PublicFrame } from '@/components/PublicFrame';
import { Banner, Button, Field, Wordmark } from '@/components/ui';
import { useAction } from '@/lib/hooks';
import { useSession } from '@/lib/session';

export default function Register() {
  const router = useRouter();
  const { register } = useSession();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const tooShort = password.length > 0 && password.length < 8;
  const submit = useAction(async () => {
    await register({ name: name.trim(), email, password });
    router.replace('/app/home');
  });

  return (
    <PublicFrame>
      <form className="auth" onSubmit={(e) => { e.preventDefault(); void submit.run(); }} noValidate>
        <Wordmark large />
        <div>
          <h1>Create your account</h1>
          <p className="muted">Organize a circle, or join one you’ve been invited to.</p>
        </div>
        <Field label="Your name">
          {(id) => <input id={id} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required />}
        </Field>
        <Field label="Email" help="Use the email your organizer invited, if you have an invite.">
          {(id) => <input id={id} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />}
        </Field>
        <Field label="Password" error={tooShort ? 'Use at least 8 characters.' : null}>
          {(id) => <input id={id} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required />}
        </Field>
        {submit.error && <Banner tone="danger">{submit.error}</Banner>}
        <Button block type="submit" disabled={submit.pending || !name.trim() || !email || password.length < 8}>
          {submit.pending ? 'Creating account…' : 'Create account'}
        </Button>
        <p className="auth__alt">Already have an account? <Link className="link" href="/sign-in">Sign in</Link></p>
      </form>
    </PublicFrame>
  );
}
