# Selected-plan trials

Registration saves the public plan, billing term and quoted total on the account. The trial uses that plan's workspace permissions and limits for 14 days. Selecting 3 years saves the full 3-year total; there is no automatic charge.

The app checks for reminders hourly. It sends one email per account per date from four days before expiry through the expiry date. SMTP acceptance is recorded persistently; failed sends are retried. An in-app notice is recorded separately once per account per date. Paid accounts stop receiving reminders. The payment link remains accessible from the workspace page after expiry.

Before enabling outgoing reminders on deployment:

- Set `PUBLIC_APP_URL` to the public HTTPS address, without a trailing path (for example `https://app.example.com`). No public domain has been selected yet, so outgoing reminders are currently disabled.
- Configure the existing SMTP credentials and Razorpay credentials.
- Keep an application worker running. The reminder worker runs within the application; a sleeping hosting service cannot send scheduled emails while asleep.
- Restart the app to apply the additive reminder-date columns.

Emails link to `/subscription/trial`, where the account owner signs in and starts Razorpay checkout at the saved registration price. Payment is verified server-side before activation. Email sending and actual gateway payment were not exercised against live customers during development.
