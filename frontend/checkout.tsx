import { Component, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { createPortal } from 'react-dom';
import { AnimatePresence, LazyMotion, domAnimation, m, MotionConfig, useReducedMotion } from 'framer-motion';

type Tier = { id: number; name: string; description: string; price: number; remaining: number; max_per_order: number; sales_closed: boolean; waitlist_url: string };
type CheckoutData = { types: Tier[]; checkoutUrl: string; csrfToken: string; eventTitle: string; eventDate: string; eventVenue: string; mpesaEnabled: boolean; paystackEnabled: boolean; authenticated: boolean; buyerName: string; buyerEmail: string; termsUrl: string; privacyUrl: string };
type Totals = { subtotal: number; total: number; count: number };
const money = (amount: number) => `KES ${new Intl.NumberFormat('en-KE', { minimumFractionDigits: Number.isInteger(amount) ? 0 : 2, maximumFractionDigits: 2 }).format(amount)}`;
const FOCUSABLE_SELECTOR = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function Icon({ name }: { name: string }) { return <svg className="icon" aria-hidden="true"><use href={`#i-${name}`} /></svg>; }
function Summary({ totals }: { totals: Totals }) {
  return <div className="order-summary">
    <div className="summary-row"><span>{totals.count} ticket{totals.count === 1 ? '' : 's'}</span><span>{money(totals.subtotal)}</span></div>
    <div className="summary-row"><span>Payment processing</span><span>Included</span></div>
    <div className="summary-row total"><span>Total to pay</span><strong data-testid="checkout-total">{money(totals.total)}</strong></div>
  </div>;
}

function Waitlist({ tier, csrfToken }: { tier: Tier; csrfToken: string }) {
  return <details className="waitlist-form"><summary>Join the {tier.name} waitlist</summary><form method="post" action={tier.waitlist_url}>
    <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
    <label className="form-label">Full name<input name="name" autoComplete="name" required maxLength={150} /></label>
    <label className="form-label">Email<input type="email" name="email" autoComplete="email" required /></label>
    <button className="button button-outline button-small" type="submit">Notify me when tickets return <Icon name="arrow" /></button>
  </form></details>;
}

function CheckoutModal({ data, quantities, totals, onClose }: { data: CheckoutData; quantities: Record<number, number>; totals: Totals; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [method, setMethod] = useState(data.mpesaEnabled ? 'mpesa' : 'paystack');
  const [submitting, setSubmitting] = useState(false);
  const reduce = useReducedMotion();
  useLayoutEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const element = dialog.current;
    element?.showModal();
    element?.querySelector<HTMLInputElement>('#buyer-name')?.focus({ preventScroll: true });
    document.body.style.overflow = 'hidden';
    return () => {
      element?.close();
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus({ preventScroll: true });
    };
  }, []);
  useEffect(() => {
    // Browsers can restore a form page from the back/forward cache.
    const reset = () => setSubmitting(false);
    window.addEventListener('pageshow', reset);
    return () => window.removeEventListener('pageshow', reset);
  }, []);
  function trapFocus(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== 'Tab') return;
    const element = dialog.current;
    if (!element) return;
    const nodes = Array.from(element.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(node => (node.offsetWidth || node.offsetHeight || node === document.activeElement));
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    const active = document.activeElement;
    if (!element.contains(active)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }
  return createPortal(<dialog ref={dialog} className="checkout-dialog" aria-labelledby="checkout-title" aria-describedby="checkout-event-name" onKeyDown={trapFocus} onCancel={event => { event.preventDefault(); if (!submitting) onClose(); }} onClick={event => { if (event.target === event.currentTarget && !submitting) onClose(); }}>
    <m.div className="checkout-sheet" initial={{ opacity: 0, y: reduce ? 0 : 32 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduce ? 0 : 18 }} transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}>
      <p className="checkout-progress">01 Tickets selected <span aria-hidden="true">/</span> 02 Make it official</p>
      <div className="checkout-heading"><h2 id="checkout-title">You're nearly there.</h2><button type="button" className="checkout-close" onClick={onClose} aria-label="Close checkout" disabled={submitting}>×</button></div>
      <div className="checkout-event"><strong id="checkout-event-name">{data.eventTitle}</strong><p>{data.eventDate}</p><p>{data.eventVenue}</p></div>
      <form className="checkout-form" action={data.checkoutUrl} method="post" onSubmit={event => { if (submitting) { event.preventDefault(); return; } setSubmitting(true); }}>
        <input type="hidden" name="csrfmiddlewaretoken" value={data.csrfToken} />
        <input type="hidden" name="payment_method" value={method} />
        {data.types.map(tier => <input key={tier.id} type="hidden" name={`qty_${tier.id}`} value={quantities[tier.id] || 0} />)}
        {data.paystackEnabled ? <div className="payment-tabs" role="group" aria-label="Payment method">{data.mpesaEnabled ? <button type="button" aria-pressed={method === 'mpesa'} onClick={() => setMethod('mpesa')}>M-Pesa</button> : null}<button type="button" aria-pressed={method === 'paystack'} onClick={() => setMethod('paystack')}>Debit / credit card</button></div> : null}
        <label className="form-label" htmlFor="buyer-name">Full name<input id="buyer-name" name="buyer_name" autoComplete="name" required maxLength={150} defaultValue={data.buyerName} autoFocus placeholder="Your name" /></label>
        <label className="form-label" htmlFor="buyer-email">Email <small>{method === 'paystack' ? '(for your receipt)' : '(optional — get a copy of your tickets)'}</small><input id="buyer-email" type="email" name="buyer_email" autoComplete="email" required={method === 'paystack'} defaultValue={data.buyerEmail} placeholder="you@example.com" /></label>
        <label className="form-label" htmlFor="buyer-phone">{method === 'mpesa' ? 'M-Pesa phone number' : 'Phone number'}<input id="buyer-phone" type="tel" name="buyer_phone" autoComplete="tel" inputMode="tel" maxLength={20} required placeholder="07XX XXX XXX" /></label>
        <p className="payment-hint">{method === 'mpesa' ? 'Confirm the M-Pesa prompt on your phone. Never enter your PIN on this website.' : 'You’ll continue to Paystack to enter your card details securely.'}</p>
        <Summary totals={totals} />
        {!data.authenticated ? <label className="terms-label"><input type="checkbox" name="terms_accepted" required /><span>I agree to the <a href={data.termsUrl} target="_blank" rel="noopener">Terms of Service</a> and <a href={data.privacyUrl} target="_blank" rel="noopener">Privacy Policy</a>.</span></label> : null}
        <m.button whileTap={reduce ? undefined : { scale: 0.98 }} type="submit" className="button button-gold" disabled={submitting}>{submitting ? 'Starting your payment…' : method === 'mpesa' ? `Pay ${money(totals.total)} with M-Pesa` : `Continue to card payment`}<Icon name={submitting ? 'phone' : 'arrow'} /></m.button>
        <p className="payment-hint" role="status">{submitting ? 'Please wait for the next page. Your tickets are issued after payment is confirmed.' : 'Your order total is shown above. No account needed to check out.'}</p>
      </form>
    </m.div>
  </dialog>, document.body);
}

function Checkout({ data }: { data: CheckoutData }) {
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [open, setOpen] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const continueRef = useRef<HTMLButtonElement>(null);
  const reduced = useReducedMotion();
  const subtotalCents = data.types.reduce((sum, tier) => sum + Math.round(tier.price * 100) * (quantities[tier.id] || 0), 0);
  const count = Object.values(quantities).reduce((sum, qty) => sum + qty, 0);
  const totals: Totals = { subtotal: subtotalCents / 100, total: subtotalCents / 100, count };
  const available = data.types.filter(tier => !tier.sales_closed && tier.remaining > 0 && tier.max_per_order > 0);
  const lowest = available.length ? Math.min(...available.map(tier => tier.price)) : null;
  const selectedTier = count === 1 ? data.types.find(tier => quantities[tier.id] === 1) : undefined;
  const upgradeTier = selectedTier ? available.find(tier => /\bvip\b|premium/i.test(tier.name) && tier.price > selectedTier.price) : undefined;
  const upgradeCents = upgradeTier ? Math.round(upgradeTier.price * 100) : 0;
  const upgradeExtra = (upgradeCents - subtotalCents) / 100;
  function change(tier: Tier, delta: number) {
    if (tier.sales_closed) return;
    const next = Math.max(0, Math.min(tier.remaining, tier.max_per_order, (quantities[tier.id] || 0) + delta));
    setQuantities(previous => ({ ...previous, [tier.id]: next }));
    setAnnouncement(`${next} ${tier.name} ticket${next === 1 ? '' : 's'} selected.`);
  }
  function mobileAction() {
    if (count) setOpen(true);
    else {
      document.getElementById('booking')?.scrollIntoView({ behavior: reduced ? 'instant' : 'smooth', block: 'start' });
      document.querySelector<HTMLButtonElement>('[data-add-ticket]:not(:disabled)')?.focus({ preventScroll: true });
    }
  }
  function focusCheckoutTrigger() {
    const trigger = continueRef.current || document.querySelector<HTMLButtonElement>('[data-checkout-return-focus]');
    trigger?.focus({ preventScroll: true });
  }
  function closeCheckout() {
    setOpen(false);
    [0, 300, 600].forEach(delay => window.setTimeout(focusCheckoutTrigger, delay));
  }
  return <>
    <div className="booking-panel" data-testid="ticket-selector">
      <p className="eyebrow gold">YOUR WAY IN</p><h2>Make it a plan.</h2><p className="booking-intro">Pick your tickets. We'll take care of the rest.</p>
      <div className="ticket-tiers">{data.types.map(tier => {
        const qty = quantities[tier.id] || 0;
        const soldOut = tier.remaining <= 0;
        return <div key={tier.id}><div className={`ticket-tier ${qty ? 'selected' : ''} ${tier.sales_closed ? 'closed' : ''}`}>
          <div><strong>{tier.name}</strong>{tier.description ? <p>{tier.description}</p> : null}<b>{money(tier.price)} <small>processing included</small></b>{tier.remaining > 0 && tier.remaining <= 10 && !tier.sales_closed ? <p className="scarcity">Only {tier.remaining} left</p> : null}</div>
          {tier.sales_closed ? <span className="tier-state">Sales ended</span> : soldOut ? <span className="tier-state">Sold out</span> : <div className="quantity-control"><m.button type="button" whileTap={reduced ? undefined : { scale: 0.88 }} onClick={() => change(tier, -1)} disabled={qty === 0} aria-label={`Remove one ${tier.name} ticket`}>−</m.button><output aria-label={`${tier.name} quantity`}>{qty}</output><m.button type="button" data-add-ticket whileTap={reduced ? undefined : { scale: 0.88 }} onClick={() => change(tier, 1)} disabled={qty >= Math.min(tier.remaining, tier.max_per_order)} aria-label={`Add one ${tier.name} ticket`}>+</m.button></div>}
        </div>{soldOut && !tier.sales_closed ? <Waitlist tier={tier} csrfToken={data.csrfToken} /> : null}</div>;
      })}</div>
      <div className="sr-only" aria-live="polite" aria-atomic="true">{announcement} Total {money(totals.total)} with processing included.</div>
      {count ? <m.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}><Summary totals={totals} /></m.div> : <p className="fee-note"><Icon name="shield" />The ticket price is the price you pay. Payment processing included.</p>}
      {upgradeTier ? <div className="ticket-upgrade"><span className="eyebrow">A LITTLE EXTRA, IF YOU WANT IT</span><p>{upgradeTier.description || `Explore the ${upgradeTier.name} experience.`}</p><button type="button" onClick={() => { setQuantities({ [upgradeTier.id]: 1 }); setAnnouncement(`Switched to one ${upgradeTier.name} ticket.`); }}>Switch to {upgradeTier.name} <span>+{money(upgradeExtra)} ↗</span></button></div> : null}
      <m.button ref={continueRef} data-checkout-return-focus type="button" className="button button-gold checkout-continue" whileTap={reduced ? undefined : { scale: 0.98 }} disabled={!count} onClick={() => setOpen(true)}>{count ? `Continue with ${count} ticket${count === 1 ? '' : 's'}` : available.length ? 'Select your tickets' : 'No tickets available'}<Icon name="arrow" /></m.button>
      <div className="booking-methods">{data.mpesaEnabled ? <span className="payment-wordmark">M-PESA</span> : null}{data.paystackEnabled ? <><span>VISA</span><span>Mastercard</span></> : null}<span>SECURE CHECKOUT</span></div>
    </div>
    {available.length ? <div className="mobile-booking-bar"><div><small>{count ? `${count} ticket${count === 1 ? '' : 's'} · processing included` : 'Tickets from'}</small><strong>{money(count ? totals.total : lowest || 0)}</strong></div><button type="button" className="button button-gold" onClick={mobileAction}>{count ? 'Continue to checkout' : 'Get tickets'} <Icon name="arrow" /></button></div> : null}
    <AnimatePresence onExitComplete={focusCheckoutTrigger}>{open ? <CheckoutModal data={data} quantities={quantities} totals={totals} onClose={closeCheckout} /> : null}</AnimatePresence>
  </>;
}

class CheckoutBoundary extends Component<{ children: ReactNode; fallback: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <div dangerouslySetInnerHTML={{ __html: this.props.fallback }} /> : this.props.children; }
}

export function mountCheckout(element: HTMLElement, data: CheckoutData) {
  const fallback = element.innerHTML;
  createRoot(element).render(<CheckoutBoundary fallback={fallback}><LazyMotion features={domAnimation} strict><MotionConfig reducedMotion="user"><Checkout data={data} /></MotionConfig></LazyMotion></CheckoutBoundary>);
}
