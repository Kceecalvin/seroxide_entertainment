# SeroTix marketplace release

Implemented locally; no production migration, account provisioning, payments, or real email sends performed during this change.

## Roles and ownership

- Buyer: personal order history/settings/password recovery. Guest checkout remains supported.
- Seller: retains buyer abilities; self-service onboarding, private drafts, cover preview, ticket tiers, submission, and own paid-sales reporting. No cross-seller reads or writes. Revenue excludes fees and cancelled/refunded bookings; it is not a payout balance.
- Admin: event operations and approval queue; cannot assign roles, issue refunds, read the mail-delivery log, or enter Django administration.
- Super Admin: existing Django superuser; controls team assignments, refunds, reconciliation, and delivery retries. The team screen cannot create/promote a superuser or change the owner's access.
- Gate scanner: paid tickets for explicitly assigned events only, with atomic single admission and scanner identity recorded.

User requested two admins and three scanner accounts. Names/emails and whether Super Admin is included in the two are pending. Do not invent or share credentials. Members can register individually, then the owner assigns their roles at `/manage/team/`. Existing owners remain owners. The migration preserves legacy is_staff-only scanners' access to events that already exist; new events require explicit assignment.

## Event lifecycle

`draft → pending → approved (public)` or `pending → changes → draft → pending`.
Seller-supplied publication, feature, ownership, and staff flags are ignored. Submitted/live content is locked to the seller. Withdrawing a listing removes it from sale and requires approval again; already purchased tickets remain valid. Approval needs a cover, future date, and paid active tier. Existing platform listings preserve their publication state and do not silently acquire a seller.

## Tickets and money

Order pages and payment-status polling require buyer ownership, an authorized checkout/lookup session, a signed 90-day email link, or admin access. Guest retrieval validates the full phone number with the reference; a one-digit suffix no longer grants access. Existing emailed plain links require guest lookup/sign-in. No automatic matching of guest orders by an unverified account email.

Ticket inventory is locked at reservation. Late confirmed payments must reacquire stock after expiry; insufficient stock leaves the confirmed payment in reconciliation. Replayed refunded callbacks cannot revive tickets. Card callbacks validate exact decimal amounts and KES currency. Payment-row locks serialize callback updates with refunds. Card checkout requires a real receipt email. Payment-provider authentication and bank OTP remain provider-controlled.

## Email

Branded HTML and text alternatives: tickets (inline QR attachments), waitlist, account welcome, seller onboarding/submission/decision, password reset, contact notifications, and refund/cancellation updates. Transactional outbox persists pending/failed/sent state, attempt count and a sanitized error class. Enqueue ticket/waitlist messages in the transaction; send only after commit. Failures do not undo purchases. SMTP acceptance is not proof of inbox delivery. SMTP cannot guarantee exactly-once delivery after ambiguous timeouts; ticket confirmations and generic messages have stable Message-IDs.

`python manage.py retry_emails` retries at most 100 messages and five attempts. `deploy/serotix-retry-emails.{service,timer}` supplies a five-minute production schedule. Owner retries are available at `/manage/emails/`. Password-reset links are single-use and expire in one hour. No real messages were sent during verification.

## Release procedure

1. Back up PostgreSQL and media; preserve `.env` and database credentials.
2. Copy the reviewed app/templates/static/migrations and install the pinned dependencies.
3. Run production Django checks and `migrate --noinput`, then `collectstatic --noinput`.
4. Install the email retry service/timer, reload systemd, enable/start the timer, and restart the app.
5. Verify public listings/checkout, all role landings, and existing gate accounts. Assign the requested named staff accounts and their events.
6. Verify SMTP configuration and the sender-domain SPF/DKIM/DMARC through the actual email provider before relying on delivery. No provider configuration has been changed here.

## Verification and remaining limits

Automated tests cover role isolation, seller ownership, moderation, duplicate scanning, guest/owner ticket access, email retries, reset email, stock reservation and late payment, exact card amount/currency, and refunded callback replay. Browser checks cover the new screens at phone and desktop widths. All payment calls are simulated/mocked and emails use Django's memory backend during tests. SQLite tests do not prove PostgreSQL concurrent-lock behavior; perform a staging concurrency check before a busy live event.

Django was upgraded and pinned to 5.2.17. The local PyPI wheel requests failed through the network proxy; installation succeeded from the official Django GitHub `5.2.17` tag. Validate the pinned dependency installation on the release host. Seller payout routing/settlement is not automated in this release and needs a separate commercial/provider setup.

Verified results: 114 tests passed on Django 5.2.17, followed by a passing account-suite rerun after reset-token replay and email/username uniqueness changes. Browser: 44 role/route/viewport combinations (320, 390, 768, 1440 px), zero overflow or page errors. TypeScript checking and frontend build passed. Local preview: http://127.0.0.1:3050/account/signup/ . No live release was performed.
