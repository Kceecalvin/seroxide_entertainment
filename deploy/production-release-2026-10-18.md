# Production marketplace release — 18 October 2026

This release includes the buyer/seller marketplace, two operational admin roles
and assigned scanner roles (accounts must be individually provisioned by owner),
protected order retrieval, event moderation, transactional email outbox/retries,
and the responsive experience frontend. Historical order/payment data is retained.

## Safety changes

- Django 5.2.18, with server-tested dependency versions in requirements.lock.
- Direct-card/Flutterwave charge and webhook routes removed. Historical fields
  remain for data/migration compatibility. Hosted Paystack and M-Pesa are the
  available new-purchase integrations; Stripe is legacy callback/refund support.
- PAYMENTS_LIVE defaults off. Production checks and checkout fail closed on
  missing providers/test credentials before reserving stock. The public event
  page shows booking unavailable when no production provider is ready.
- Gate admission locks the order and uses a ticket-only conditional UPDATE.
  A new PostgreSQL test exposed a joined-update double-admission race; this
  release fixes it and tests two simultaneous scanners plus last-ticket stock.
- Every simulation is prohibited by production settings. Demo tools remain local.
- Gunicorn access logs omit request URLs so callback and signed-link tokens do
  not leak into those new access entries. Existing logs remain restricted.
- Terms/privacy use a fixed revision date. Environment examples use .co.ke.

## Operations

Install retry-emails (five minutes), monitor (five minutes) and backup-full
(03:15 UTC daily) services/timers. Retain existing expiry and SQL backup timers.
The full backup contains SQL and media, checks integrity and uses restrictive
permissions. An owner-controlled recurring offsite destination is still needed.
`production_status --check` checks DB/cache and completed-payment reconciliation;
it never prints credentials, recipients or raw payment data. Monitoring currently
records systemd status/journal; owner should select an external alert recipient.

## Verified before activation

- Restored a fresh production SQL dump into a separate PostgreSQL database;
  preserved 1 event, 18 orders and 7 tickets, then applied all migrations.
- 124 tests passed on PostgreSQL / Django 5.2.18, including real concurrency.
  Test settings used in-memory email, simulated providers and a fast test-only
  password hasher. No live charges, refunds or emails were sent.
- Browser checks: 12 passed; one browser-process interruption; that test passed
  on an isolated rerun. TypeScript and frontend build passed.
- Existing SMTP authentication passed without sending a message.

## Activation and rollback record

Server: `/srv/serotix/app`; stage: `/srv/serotix/releases/20261018-marketplace`.
Prepared venv: `/srv/serotix/venv-20261018`.
Private rollback code/config: `/srv/serotix/backups/pre-marketplace-code-20261018.tar.gz`.
Old venv is preserved when the live `venv` path switches to the prepared one.
Preserve media and .env; append PAYMENTS_LIVE=0 until owner activation.
Stop app/expiry briefly during code replacement and migrations; collect assets,
restart, poll HTTPS-aware socket readiness, and verify public HTTPS.

All migrations in this release are additive. If activation fails, restore the
old code and previous venv; do not restore the database over any new provider
transactions. Confirm health and reconcile before enabling sales. A deployment
result and current revision are recorded separately in the handover addendum.

## Owner acceptance still required

Live merchant credentials/settlement account, approved upcoming event, named
owner + two admins + three scanners, domain/provider ownership transfer, support
inbox and authorized receipt/refund test, real-device gate rehearsal, seller
settlement agreement, and recurring offsite storage/alert destination.
