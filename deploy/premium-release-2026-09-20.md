# Premium release — 20 September 2026

Live: https://serotix.co.ke/
VPS SSH alias: cockbox
Application: /srv/serotix/app
Service: serotix

Deployed the staged premium templates, static assets, and supporting event discovery, dashboard, contact, and ticket email code. No database migrations or dependency changes were required. Production settings, payment clients, credentials, and media were preserved.

Rollback archive: /srv/serotix/backups/pre-premium-20260918.tar.gz
Staged release: /srv/serotix/stage-premium-20260918
Release payload: /tmp/serotix-premium-release.tar.gz

Validation: 96 Django tests passed; 10 browser checks passed initially, with the remaining no-JavaScript checkout check passing after replacing a forced checkbox click with Playwright check(). Production check and migration check passed. After activation, public homepage, quiz, desktop assets and mobile navigation at 390px were verified, with no horizontal overflow, failed assets or browser JavaScript errors observed. Screenshots: /tmp/serotix-live-mobile.jpg and /tmp/serotix-live-desktop.jpg (quiz dialog).

The first activation automatically rolled back because the socket check preceded Gunicorn readiness. Retrying with bounded readiness retries succeeded. Production currently has no upcoming published events, so discovery and quiz results show their empty states. Live checkout transactions and outbound emails were not sent during verification.
