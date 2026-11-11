'use client';
import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';
import { Icon } from '@/components/Icon';
import { MoneyInput } from '@/components/domain';
import { Screen } from '@/components/shell';
import { Banner, Button, Card, Field } from '@/components/ui';
import { api } from '@/lib/api/endpoints';
import { useAction } from '@/lib/hooks';
import { CURRENCY_EXPONENTS, parseMajorToMinor } from '@/lib/money';
import { PAYOUT_MODES, buildRuleset, describeRules, isAuction, percentToRate, type RulesForm } from '@/lib/ruleset';
import { useSession } from '@/lib/session';
import { useToast } from '@/lib/toast';
import type { PayoutMode, RulesetData } from '@/lib/types';

interface Seat { name: string; email: string }
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const CURRENCIES = Object.keys(CURRENCY_EXPONENTS);

export default function NewCirclePage() {
  const router = useRouter();
  const session = useSession();
  const toast = useToast();
  const me = session.user!;

  const [name, setName] = useState('');
  const [mode, setMode] = useState<PayoutMode>('SEALED_BID_AUCTION');
  const [currency, setCurrency] = useState('INR');
  const [potRaw, setPotRaw] = useState('1,00,000');
  const [includeMe, setIncludeMe] = useState(true);
  const [mySeat, setMySeat] = useState<'first' | 'last'>('last');
  const [seats, setSeats] = useState<Seat[]>([{ name: '', email: '' }, { name: '', email: '' }, { name: '', email: '' }]);
  const [commission, setCommission] = useState('5');
  const [maxDiscount, setMaxDiscount] = useState('30');
  const [stepRaw, setStepRaw] = useState('');
  const [tieBreak, setTieBreak] = useState<RulesForm['tieBreak']>('EARLIEST_BID');
  const [fallback, setFallback] = useState<RulesForm['noBidFallback']>('FIXED_ROTATION');
  const [dividend, setDividend] = useState<RulesForm['dividendAllocation']>('ALL_MEMBERS');
  const [grace, setGrace] = useState('3');
  const [approvals, setApprovals] = useState(1);
  const [requireSecurity, setRequireSecurity] = useState(false);
  const [fullCollection, setFullCollection] = useState(true);

  const potMinor = parseMajorToMinor(potRaw, currency);
  const stepMinor = stepRaw.trim() ? parseMajorToMinor(stepRaw, currency) : 0;
  const memberCount = seats.length + (includeMe ? 1 : 0);
  const auction = isAuction(mode);

  const errors = useMemo(() => {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = 'Give the circle a name.';
    if (!potMinor) e.pot = 'Enter the pot size, e.g. 1,00,000.';
    if (memberCount < 2) e.members = 'A circle needs at least two members.';
    seats.forEach((s, i) => {
      if (!s.name.trim() && !s.email.trim()) e[`seat${i}`] = 'Add a name or an email.';
      else if (s.email.trim() && !EMAIL.test(s.email.trim())) e[`seat${i}`] = 'That email doesn’t look right.';
    });
    const emails = seats.map((s) => s.email.trim().toLowerCase()).filter(Boolean);
    if (new Set(emails).size !== emails.length) e.members = 'Each email can hold only one seat.';
    if (includeMe && me.email && emails.includes(me.email.toLowerCase())) e.members = 'You are already included; remove your own email from the list.';
    if (percentToRate(commission) === null) e.commission = 'Enter a percentage between 0 and 100.';
    const md = percentToRate(maxDiscount);
    if (auction && (md === null || md === '0' || md === '1')) e.maxDiscount = 'Enter a cap between 0 and 100 (exclusive).';
    if (auction && stepMinor === null) e.step = 'Enter a valid amount or leave blank.';
    if (!/^\d{1,2}$/.test(grace)) e.grace = 'Whole days, 0–99.';
    return e;
  }, [name, potMinor, memberCount, seats, includeMe, me.email, commission, maxDiscount, auction, stepMinor, grace]);

  const form: RulesForm = {
    currency, payoutMode: mode, chitValueMinor: potMinor ?? 0, memberCount, commissionPercent: commission,
    maxDiscountPercent: maxDiscount, minIncrementMinor: stepMinor ?? 0, tieBreak, noBidFallback: fallback,
    dividendAllocation: dividend, gracePeriodDays: Number(grace) || 0, requiredApprovals: approvals,
    requireSecurity, requireFullCollection: fullCollection,
  };
  const summary = potMinor ? describeRules(buildRuleset(form) as unknown as RulesetData) : [];

  const create = useAction(async () => {
    const others = seats.map((s) => ({ name: s.name.trim() || undefined, email: s.email.trim() || undefined }));
    const meSeat = { name: me.name, user_id: me.id };
    const members = includeMe ? (mySeat === 'first' ? [meSeat, ...others] : [...others, meSeat]) : others;
    const res = await api.createCircle(session, { name: name.trim(), ruleset: buildRuleset(form), members });
    toast(`“${name.trim()}” created`);
    router.push(`/app/circles/${encodeURIComponent(res.id)}`);
  });

  const setSeat = (i: number, patch: Partial<Seat>) => setSeats((s) => s.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const valid = Object.keys(errors).length === 0;

  return (
    <Screen title="New circle" subtitle="Set the rules once. The engine applies them the same way every round."
            back={{ href: '/app/circles', label: 'Circles' }}>
      <form className="grid grid--main" onSubmit={(e) => { e.preventDefault(); if (valid) void create.run(); }} noValidate>
        <div className="stack stack--lg">
          <Card title="Basics">
            <div className="form-grid form-grid--2">
              <Field label="Circle name" error={name ? errors.name : null}>
                {(id) => <input id={id} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Family chit 2026" />}
              </Field>
              <div className="form-grid form-grid--2">
                <Field label="Currency">
                  {(id) => (
                    <select id={id} value={currency} onChange={(e) => { setCurrency(e.target.value); }}>
                      {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
                    </select>
                  )}
                </Field>
                <Field label="Pot each round" error={potRaw ? errors.pot : null}>
                  {(id) => <MoneyInput id={id} currency={currency} value={potRaw} onChange={(raw) => setPotRaw(raw)} invalid={!!(potRaw && errors.pot)} />}
                </Field>
              </div>
            </div>
          </Card>

          <Card title="How the pot is given out" subtitle="Pick the tradition your group follows.">
            <div className="choices">
              {PAYOUT_MODES.map((m) => (
                <button key={m.id} type="button" className="choice" aria-pressed={mode === m.id} onClick={() => setMode(m.id)}>
                  <span className="choice__tag">{m.tradition}</span>
                  <b>{m.title}</b>
                  <small>{m.body}</small>
                </button>
              ))}
            </div>
          </Card>

          <Card title={`Members (${memberCount})`} subtitle="Invite by email to link their account; a name alone reserves a seat you manage.">
            <label className="check">
              <input type="checkbox" checked={includeMe} onChange={(e) => setIncludeMe(e.target.checked)} />
              <span>I also contribute and receive the pot (I hold a seat)</span>
            </label>
            {includeMe && (
              <div className="row row--wrap">
                <span className="muted small">My seat</span>
                <div className="segmented" role="group" aria-label="My seat">
                  <button type="button" aria-pressed={mySeat === 'first'} onClick={() => setMySeat('first')}>First</button>
                  <button type="button" aria-pressed={mySeat === 'last'} onClick={() => setMySeat('last')}>Last</button>
                </div>
              </div>
            )}
            <div className="members-editor">
              {seats.map((s, i) => (
                <div key={i} className="stack stack--sm">
                  <div className="members-editor__row">
                    <span className="seat">{i + 1 + (includeMe && mySeat === 'first' ? 1 : 0)}</span>
                    <input aria-label={`Member ${i + 1} name`} placeholder="Name" value={s.name} onChange={(e) => setSeat(i, { name: e.target.value })} />
                    <input className="email" aria-label={`Member ${i + 1} email`} placeholder="Email (to invite)" type="email" value={s.email}
                           onChange={(e) => setSeat(i, { email: e.target.value })} />
                    <button type="button" className="icon-btn" aria-label={`Remove member ${i + 1}`} disabled={seats.length <= 1}
                            onClick={() => setSeats((x) => x.filter((_, j) => j !== i))}><Icon name="x" /></button>
                  </div>
                  {errors[`seat${i}`] && (s.name || s.email) && <span className="field__error">{errors[`seat${i}`]}</span>}
                </div>
              ))}
            </div>
            <div className="row row--wrap">
              <Button variant="soft" small icon="plus" onClick={() => setSeats((s) => [...s, { name: '', email: '' }])}>Add member</Button>
              {errors.members && <span className="field__error">{errors.members}</span>}
            </div>
            {includeMe && mySeat === 'first' && mode === 'FIXED_ROTATION' && (
              <Banner tone="warning">In rotation, seat 1 receives the first pot. You can’t approve your own payout, so a designated approver will be needed that round.</Banner>
            )}
          </Card>

          <Card title="Rules">
            <div className="form-grid form-grid--3">
              <Field label="Organizer commission (% of pot)" error={errors.commission}>
                {(id) => <input id={id} inputMode="decimal" value={commission} onChange={(e) => setCommission(e.target.value)} />}
              </Field>
              <Field label="Grace period (days)" error={errors.grace}>
                {(id) => <input id={id} inputMode="numeric" value={grace} onChange={(e) => setGrace(e.target.value)} />}
              </Field>
              <Field label="Approvals before payout">
                {(id) => (
                  <select id={id} value={approvals} onChange={(e) => setApprovals(Number(e.target.value))}>
                    <option value={1}>1 (organizer)</option>
                    <option value={2}>2 (organizer + approver)</option>
                  </select>
                )}
              </Field>
            </div>
            {auction && (
              <div className="form-grid form-grid--2">
                <Field label="Maximum discount (% of pot)" error={errors.maxDiscount}>
                  {(id) => <input id={id} inputMode="decimal" value={maxDiscount} onChange={(e) => setMaxDiscount(e.target.value)} />}
                </Field>
                <Field label="Bid step (optional)" error={errors.step} help="Bids must be multiples of this amount.">
                  {(id) => <MoneyInput id={id} currency={currency} value={stepRaw} onChange={(raw) => setStepRaw(raw)} placeholder="No step" />}
                </Field>
                <Field label="If bids tie">
                  {(id) => (
                    <select id={id} value={tieBreak} onChange={(e) => setTieBreak(e.target.value as RulesForm['tieBreak'])}>
                      <option value="EARLIEST_BID">Earliest bid wins</option>
                      <option value="LOWEST_POSITION">Lower seat number wins</option>
                      <option value="SEEDED_RANDOM">Committed random draw</option>
                    </select>
                  )}
                </Field>
                <Field label="If nobody bids">
                  {(id) => (
                    <select id={id} value={fallback} onChange={(e) => setFallback(e.target.value as RulesForm['noBidFallback'])}>
                      <option value="FIXED_ROTATION">Next in seat order receives</option>
                      <option value="LOTTERY">Lottery draw</option>
                      <option value="HOLD">Hold for the organizer</option>
                    </select>
                  )}
                </Field>
                <Field label="Dividends go to">
                  {(id) => (
                    <select id={id} value={dividend} onChange={(e) => setDividend(e.target.value as RulesForm['dividendAllocation'])}>
                      <option value="ALL_MEMBERS">Every member</option>
                      <option value="ELIGIBLE_MEMBERS">Members not in arrears</option>
                    </select>
                  )}
                </Field>
              </div>
            )}
            <label className="check">
              <input type="checkbox" checked={requireSecurity} onChange={(e) => setRequireSecurity(e.target.checked)} />
              <span>Require verified security (guarantor or collateral) before a winner is paid</span>
            </label>
            <label className="check">
              <input type="checkbox" checked={fullCollection} onChange={(e) => setFullCollection(e.target.checked)} />
              <span>Only pay out once every contribution is confirmed</span>
            </label>
          </Card>
        </div>

        <div className="stack stack--lg sticky-col">
          <Card title="Rules summary" subtitle="This is what members will see.">
            {summary.length ? <ul className="rules-list">{summary.map((s) => <li key={s}>{s}</li>)}</ul>
              : <p className="muted">Enter the pot size to see the summary.</p>}
            <p className="muted small">Exact installments are computed by the settlement engine. A pot that can’t be split evenly across {memberCount} members is rejected rather than rounded silently.</p>
          </Card>
          {create.error && <Banner tone="danger" title="Couldn’t create the circle">{create.error}</Banner>}
          <Button block type="submit" icon="check" disabled={!valid || create.pending}>{create.pending ? 'Creating…' : 'Create circle'}</Button>
        </div>
      </form>
    </Screen>
  );
}
