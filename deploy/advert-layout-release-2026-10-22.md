# Advert export layout follow-up — 22 October 2026

Long event details could be silently cut off in promotional PNGs, and multiple
lines could crowd the QR or call to action. Square and story exports now use
separate text regions, fit font sizes to the available space and wrap names
without spaces. Text that still exceeds its region ends with an ellipsis, and
the download status identifies the shortened fields for organizer review.

The complete original poster remains visible. The QR, event link and call to
action have reserved space. No event fields or captions are changed by export.
The Arch provisioning package list now includes Tesseract and English language
data, matching the packages already installed on production.

Validation: all four poster/promotion browser scenarios passed. These cover
mobile OCR/import, saved colours, square/story PNG dimensions, decoded public
QR, promotion enquiry/admin follow-up, and long/unbroken names. The added
regressions measure the actual canvas text bounds and check that text neither
overlaps other text nor the QR and stays inside each export. The long-name
square export was visually reviewed. JavaScript/shell syntax, TypeScript and
Git whitespace checks passed. Browser data and generated sample adverts are
fictional isolated fixtures. The prior release's 169 PostgreSQL tests remain
historical evidence; this change adds no backend or schema logic.

Deployment: take a full backup; preserve the current changed files and RELEASE;
install the committed files, run collectstatic, restart and check readiness.
No database migration, dependency upgrade or production form submission is
needed. Do not rerun the full Arch provisioning script on the live server.

Owner activation remains pending: approved live merchant/payment acceptance,
real upcoming event, named staff, customer email receipt/reply acceptance,
service ownership, promotion pricing/payout rules, and offsite backup/alert
destination. Checkout remains closed until merchant acceptance is complete.
