# Privacy Policy

Last updated: 2026-05-05

## Summary

social-auto-engine is self-hosted, open-source software. When you run it on your own infrastructure, all data stays on your server. The project maintainers do not collect, receive, or have access to any data from your installation.

## What we collect

Nothing. The maintainers of social-auto-engine operate no servers that receive your data, no analytics, and no telemetry. The project ships as source code and runs entirely on machines you control.

If a hosted version is offered in the future, its privacy practices will be documented separately and presented at the point of sign-up.

## What the software stores on your machine

When you install and use the software on your own server, it stores the following locally only:

- OAuth access tokens for the social platforms you choose to connect (Facebook, Instagram, WhatsApp, Threads, LinkedIn, TikTok). These are kept in a local environment file or token store on your server.
- Posts you have drafted, scheduled, or published, including text, media references, and metadata.
- Approval queue history (which user approved which post and when).
- Application logs.

By default this data sits in a local SQLite database at `~/.social-auto-engine/dashboard.db` and is never transmitted off your machine by the software itself.

## What is sent to third parties

The software communicates only with the official APIs of the platforms you have explicitly connected. For example, if you connect TikTok, the software talks to TikTok's API to upload videos and read profile information, using the OAuth token you provided. No data is routed through servers owned by the project maintainers.

## Cookies and tracking

The dashboard uses a session cookie only when you enable optional password protection. The software does not use any analytics, advertising, or tracking cookies.

## Your rights and controls

Because all data is stored on your own machine, you control it directly. You can:

- Delete the local database file at any time to remove all stored data.
- Revoke OAuth tokens through each platform's own settings.
- Inspect or export the database directly using any SQLite tool.

## Children's data

The software is not intended for use by children under 13.

## Security

OAuth tokens are stored locally on your server. You are responsible for securing access to that server and the file system on which the database resides. The project follows reasonable engineering practice to avoid leaking credentials in logs or error output, and security issues can be reported via [github.com/Freespirits/social-auto-engine/issues](https://github.com/Freespirits/social-auto-engine/issues).

## Changes to this policy

This policy may be updated as the software evolves. Material changes will be announced in the project's changelog.

## Contact

For privacy questions, open an issue at [github.com/Freespirits/social-auto-engine/issues](https://github.com/Freespirits/social-auto-engine/issues).
