# Organizer workspace and event themes

The organizer's account still uses the existing seller role and routes. Navigation
now calls it Organizer studio. No additional permissions are granted.

## Organizer workflow

1. Open /account/studio/. The dashboard shows lifetime paid sales and organizer
   allocation, with the existing 5% commission policy and settlement disclosure.
   Search event name, venue or city; filter by attention needed, in review, live
   and upcoming, or started/past. Results are scoped to the signed-in organizer,
   paginated at 12 events. Financial totals always cover all their events.
2. Create an event. Fill in the essentials, choose a cover and visual theme, then
   Save & continue to tickets. A private draft is created. Optional fields are
   marked. Dates use Nairobi time.
3. Add ticket tiers: name, price and quantity first; description, per-order limit,
   sale closing time and active status are under More ticket options. Quick name
   buttons fill Regular, Early Bird or VIP without setting a price. On server
   validation errors, submitted ticket values and field errors remain visible.
4. The checklist reflects the SAVED draft: future date, cover and active paid tier
   with capacity. Save changes before submitting. Existing backend review and
   ownership enforcement remain authoritative. Live/in-review listings remain
   locked until withdrawn; withdrawing stops sales but preserves existing tickets.
5. Preview the listing, submit for approval, and manage event-specific gate staff
   from the workspace. Gate invitations and supervisor permissions are unchanged.

The editor warns about unsaved form edits when leaving in browsers supporting
beforeunload. This is not autosave or a guarantee of recovery after a browser/app
crash. Essential forms, filtering and theme selection work without JavaScript;
poster updates, quick names and unsaved warnings are enhancements.

## Theme scope

Event.theme has five fixed presets: classic (SeroTix signature), after-dark,
coastal, gold-night and electric. Existing events receive classic. The palette
covers the event hero overlay/date badge, public booking panel/buttons and private
poster/listing preview. It does not recolor global organizer controls, platform
navigation, other recommended events, payment-provider screens or email templates.
Organizers cannot inject arbitrary CSS. Choosing a theme is saved with event
content and follows the same review/withdrawal rules as other listing edits.

Migration: events/0004_event_theme.py, one additive field with a safe default.
No changes to payments, orders, tickets, gate permissions or settlement rules.
Checkout must remain closed pending the owner's merchant acceptance.

## Validation / release

See organizer-studio-release-evidence for actual backend, browser and activation
results. Browser fixtures and all created drafts/tickets are isolated local data;
PostgreSQL tests use a separate disposable database. No production organizers,
events or invitation emails are created as part of this release.

Take a full backup and snapshot existing business record fingerprints before
activation. Add the migration, collect static assets, restart the app and check
health, private organizer routes, existing record fingerprints and checkout state.
For code rollback, restore the prior source archive and collectstatic, leaving the
additive theme column in place. Do not restore an older database over live orders.

Validation completed: 155 tests passed on PostgreSQL / Django 5.2.18. Eighteen
browser scenarios were verified: the full run passed 17; one existing vibe-quiz
scenario lost its browser context and passed in an isolated rerun. All four new
studio scenarios passed, covering mobile draft/theme/ticket/error/submission,
desktop search and unsaved-change protection, no-JavaScript forms, and public
theme/booking controls. Desktop and mobile screenshots were visually reviewed.
Migration drift, JavaScript syntax and whitespace checks passed.
