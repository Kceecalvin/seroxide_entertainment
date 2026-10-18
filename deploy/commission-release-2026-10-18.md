# Organizer commission and official support number

New orders charge the listed ticket subtotal, without the former buyer surcharge.
SeroTix retains 5% gross commission and covers processing costs from that amount;
the organizer receives the remaining 95%, rounded to cents per order.
The commission rate and amount are saved with each new order. Payment attempts
and historical/paid orders cannot be repriced. Existing orders keep their original
amounts and fees; migration 0006 only adds nullable rate and zero-default amount.

Example: KES 1,000 sale -> KES 950 organizer allocation, KES 50 gross commission.
Actual processing costs must be reconciled against provider statements; dashboard
commission is not net profit. Fees are never deducted from the organizer share.
Paid reports exclude pending/cancelled/refunded orders. Allocations are not payout
confirmations. Organizer transfers remain manual until merchant/subaccount setup,
verified organizer settlement details, refund recovery terms and payout timing are
agreed. This release does not initiate transfers or activate checkout.

Official support phone: 0119300000, click-to-call +254119300000. Set the production
SITE_SUPPORT_PHONE accordingly. A phone number alone does not establish WhatsApp
availability; existing optional social links are retained. The sender inbox is
unchanged and still requires owner-controlled delivery/reply acceptance.

Before activation: back up source/config and database; run migration checks,
backend tests and browser checkout/mobile checks. During deployment stop the
application and expiry/email/monitor jobs, apply migration, collect static files,
restart jobs and application, and confirm /healthz/, /contact/, /terms/, and phone
links. Compare historical financial fields before and after migration. Keep
PAYMENTS_LIVE disabled. The additive migration is compatible with the previous
source for rollback; do not overwrite the production DB to undo a code release.

Validation: 129 backend tests passed on PostgreSQL / Django 5.2.18, including
concurrent scanners/last-ticket reservations, rounding, legacy-order preservation,
provider charge amounts and seller reports. Browser run: 11 passed initially;
two assertions still expected old fee-inclusive prices/formatting. Corrected
those expectations and both targeted reruns passed (all 13 scenarios verified).
TypeScript, frontend build, migration drift and whitespace checks passed.
The first server test used the old phone environment; the final run used the
new explicit deployment value and passed. No live payments or customer mail sent.
