# Client-specific gate teams

Each event owner (or SeroTix platform administrator) manages that event's gate
team at /account/studio/<event-id>/gate-team/. Invitations bind the recipient's
email to one event, entrance, shift and optional supervisor permission. They do
not change global buyer/seller/admin roles. One person may work for several
clients without access to their financial pages. There is no three-guard limit.

The organizer enters a shift of up to 24 hours, in Nairobi time. The invitation
expires at the earlier of seven days or shift end. A new invitation revokes any
older unaccepted invitation for that event/email. An invitation link is stored
as a hash; the email outbox contains the private link needed for delivery. The
organizer also sees the new link once for private sharing. Treat it as private.
The recipient registers/logs in with the invited email and accepts once. A later
accepted invitation replaces that person's previous assignment for this event.

/tickets/scan/ is now the event selector. Selecting an active event opens its
camera page. Every camera API request includes that event ID; tickets for another
event are rejected even if the operator is assigned to both. The manual QR route
requires a selected event and uses the same admission service. Guards with future,
expired or revoked shifts cannot admit. Owner/platform operations access is an
explicit exception: event owners can operate their events and platform admins
can operate all events. Supervisors receive only event-specific gate activity.

Revocation blocks subsequent admission on already signed-in phones and cancels
pending invitations to that guard for this event. It does not revoke other
clients' assignments. Admission, invitation acceptance and event-team revocation
use event-first database locks. The assignment and order are rechecked before the
ticket-only conditional admission UPDATE. Audit rows are written in the same
transaction; duplicate check-ins cannot both succeed. Wrong-event attempts log
no foreign ticket or attendee details. Revoked/unauthorized requests return no
private event/ticket information and are not added to an event's activity feed.

Supervisor: /tickets/scan/events/<event-id>/supervisor/. Shows paid admissions,
valid tickets remaining, scan results and admissions by guard/entrance. Refresh
activity explicitly; this is not a WebSocket/live-stream dashboard. Existing
admitted tickets contribute to totals, but detailed scan logs begin at deployment.
These pages are marked no-store and must be checked online for current access.

Migrations: accounts 0003 adds invitation and bounded assignment fields; existing
assignments receive a window from two hours before the event to its end (or twelve
hours after start), capped at 24 hours. Owners must review migrated shifts. Tickets
0007 adds GateScanLog. No ticket/order/payment amounts are modified. Older open
scanner tabs must reload and select an event after deployment. No offline
admission is implemented: a connection failure must not be treated as admission.

Owner tasks: real guard names/emails, entrance labels, shift times and supervisor
choice; verify email delivery and rehearse with actual gate phones. Invite only
real people deliberately; this release does not seed production users or send
invitations itself. Keep checkout closed until merchant acceptance is complete.

Validation before activation: 148 backend tests pass on PostgreSQL / Django
5.2.18, including duplicate scanning, concurrent revocation, client isolation,
invitation replay/expiry, CSRF and supervisor boundaries. Existing 13 browser
scenarios passed. New mobile gate flow passed after fixing an invitation
Referrer-Policy/CSRF incompatibility; a later test wait was added for deferred
Alpine initialization. The final test exercises the actual scanner controller's
wrong-event response and stopping the camera after access is revoked. Real phone
camera hardware and real email delivery remain owner acceptance checks. TypeScript,
JavaScript syntax, whitespace and migration-drift checks passed.
