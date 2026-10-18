# Poster import, event colours and promotion studio

## Organizer workflow

1. Open Organizer studio, create/edit a private event, and upload its poster under
   **Start with your poster**. JPG, PNG and WebP up to 5 MB / 20 megapixels are read.
2. Choose **Read poster & import colours**. The app extracts a palette and uses
   local Tesseract OCR to suggest readable event details. Review the extracted
   text, name, venue, city, organizer and date/time. Full explicit dates with a
   year and a time may be suggested; ambiguous dates stay in the detected text.
   Suggested times are interpreted as Nairobi time. Stylized or small lettering
   can be missed or misread. Prices are reference only, never automatic tiers.
3. Select the suggestions to apply. Existing nonempty details are unchecked by
   default. Applying fills the form; it does not save or publish anything.
   Save the draft after reviewing it. A failed draft save requires reselecting a
   newly uploaded image, as in the existing upload workflow.
4. **From your poster** stores two extracted colours with the event. You can
   adjust both colour controls. Background/foreground shades are derived from
   that palette so buttons and text remain readable. Preset themes still work.
   A **View the full event poster** disclosure on the listing/preview preserves
   the original artwork uncropped.
5. **Promote** opens /account/studio/<event-id>/promote/. It shows the saved poster
   and event details, a sharing caption, and square (1080×1080) / story
   (1080×1920) PNG downloads. The whole poster fits inside each creative.
   Published events get a QR link to their public listing. Private drafts do not
   expose a public URL or QR. Past events are described as recaps; closed
   checkout and sold-out events do not receive a misleading buy-now caption.
6. Choose Instagram, Facebook, TikTok and/or SeroTix placement, enter an audience,
   optional budget, contact email and notes, and request a tailored offer.
   The enquiry is stored, and an existing durable branded email notification is
   queued to support. Requests are idempotent for repeated submissions of the
   same signed form. The form expires after two hours; reload to request again.
7. Platform admins see **Promotion enquiries** in Operations. They can mark a
   request followed-up or closed; each status change is audited. The organizer
   sees their own request status in their event's promotion workspace.

## Commercial scope

This provides a promotion sales channel and creative exports. It does not create
campaigns in social-platform accounts, buy ads, promise reach, or charge anyone.
The SeroTix team agrees placement, timing, creative, ad spend, service fee and
payment with the organizer before execution. Campaign pricing and settlement
must be defined by the owner. Ticket commission remains 5%, with processing fees
covered by SeroTix; promotion requests do not affect ticket/order accounting.

## Privacy, access and runtime

Poster analysis is authenticated seller-only, CSRF-protected, POST-only and
no-store. The endpoint accepts uploaded image bytes, not a URL to fetch. Uploads
are decoded with Pillow, bounded, normalized and processed in temporary files
that are removed after OCR. Extracted text is not stored by the analysis endpoint.
Only explicitly saved event fields/colours persist. No external AI API is used.

At most one OCR operation runs through the shared cache lock, with a 15-second
Tesseract timeout and eight requests per IP per ten minutes. Production uses
Valkey for the shared lock/rate limit. Without OCR, palette import still works and
the UI explicitly reports that text reading is unavailable. English OCR data is
used; this is not a multilingual document-understanding service. Imported hex
colours are validated; templates never accept arbitrary customer CSS.

Install Tesseract and English data. On the current Arch VPS:
`pacman -S --needed tesseract tesseract-data-eng`.
On Debian/Ubuntu: `apt-get install tesseract-ocr tesseract-ocr-eng`.
The Ubuntu provisioning script includes these packages. Pillow and qrcode are
already in the Python lockfile. New browser scripts are plain JavaScript and
ship through Django collectstatic; no frontend bundle rebuild is required.

Migrations: events 0005 adds poster colours and the poster theme choice; events
0006 creates PromotionRequest. Both are additive. Existing event themes, content,
orders, tickets, financial amounts, users and gate assignments are preserved.
No promotion enquiry/email is submitted against production during deployment.

## Release checks

Backend coverage includes real OCR, invalid images, missing/timed-out OCR,
CSRF/authentication, no automatic event creation, colour sanitization/readability,
owner isolation, duplicate enquiry submissions, admin permissions/audit and
private/public advert-link handling. Browser coverage includes actual mobile
poster reading and review, saved colours, complete-poster viewing, PNG dimensions,
QR decoding from an exported advert, and organizer/admin promotion follow-up.
See poster-promotion-release-evidence for final test and activation logs.

Before activation: full backup; snapshot business records; ensure OCR works as
serotix; apply migrations and collectstatic; restart and check readiness and
private routes. Code rollback may leave additive columns/table in place. Do not
restore an older database over real customer transactions.

Implementation references: [Tesseract command-line / TSV output](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html)
and [Pillow image operations](https://pillow.readthedocs.io/en/stable/reference/Image.html).

Verified before activation: 169 tests passed on PostgreSQL / Django 5.2.18 with
native Tesseract, including actual OCR of a clear sample poster. Twenty browser
scenarios were verified: 19 passed in the full run; an existing discovery test
failed during fixture setup because the preceding no-JavaScript test closed its
context without awaiting teardown. That teardown is now awaited, and the two
adjacent scenarios passed together. The new poster/promotion scenarios passed,
including QR decoding from the exported PNG. JavaScript syntax, migration drift,
whitespace and mobile overflow checks passed. Screenshots and exports use isolated
fixtures. Local and VPS OCR packages are installed; no external AI key is needed.
