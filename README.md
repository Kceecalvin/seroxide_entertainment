# SeroTix

Django ticketing marketplace at https://serotix.co.ke with buyer accounts, seller
drafts/moderation, event administrators, assigned gate scanners, protected QR
tickets, hosted payments and a transactional email outbox.

## Development and verification

Install `requirements.txt` into `venv`, and run `npm ci`. Copy `.env.example` to
`.env` for your environment; never commit the real file. `config.settings.dev`
is development only. Use explicit simulated settings for tests:

```sh
venv/bin/python manage.py test apps --settings=config.settings.browser_test
npm run typecheck
npm run build
npm run test:browser
```

Browser tests reset ONLY `/tmp/serotix-browser-tests.sqlite3` and write generated
media under `/tmp/serotix-browser-test-media`. Email is memory-only and payment
providers simulated. Do not run while another demo uses that database.

## Production

Use `config.settings.prod`, PostgreSQL, shared Valkey/Redis, a production WSGI
server and HTTPS. Review `deploy/production-release-2026-10-18.md` and the service
units in `deploy/`. Preserve production `.env` and media during every release.
Back up before migrations; test a restore into a separate database.

`PAYMENTS_LIVE=0` closes checkout while merchant activation is pending. After
owner acceptance, configure live M-Pesa (`MPESA_ENV=production`) or hosted
Paystack live keys and set `PAYMENTS_LIVE=1`. Sandbox/test credentials never
enable production checkout. All simulations are prohibited in production.
Direct-card/Flutterwave routes are retired. Card details and bank authentication
belong on the payment provider's hosted checkout.

## Roles and daily operations

- Owner/superuser: `/manage/team/`, `/manage/payments/reconciliation/`,
  `/manage/emails/`, refunds and `/secure-admin-panel/`.
- Admin: event management and `/manage/reviews/`; cannot grant roles or refund.
- Seller: `/account/sell/`, `/account/studio/`; own drafts and sales only.
- Gate scanner: `/tickets/scan/`; explicitly assigned events only.
- Buyer: `/account/my-account/`; guest retrieval `/tickets/my-tickets/`.

Owner assigns two named admins and three named scanners after each registers.
Do not use fictional demo accounts in production. New orders use a 5% commission: organizers receive 95%, and SeroTix covers
processing from its commission. There is no buyer surcharge. Historical orders
retain their original pricing. No seller payouts are automatically transferred;
agree settlement and reconcile provider receipts. See
`deploy/commission-release-2026-10-18.md`. Official support: **0119 300000**.

Email: SMTP acceptance is not proof of inbox delivery. Review failed messages
and provider bounces. `serotix-retry-emails.timer` retries pending/failed outbox
messages every five minutes. `serotix-backup-full.timer` backs up SQL plus media
daily at 03:15 UTC. Add an owner-controlled encrypted offsite destination.

Keep credentials, raw logs, backups and personal information out of public docs.
The owner handover package is stored separately in the workstation Downloads
directory, not in Git.
