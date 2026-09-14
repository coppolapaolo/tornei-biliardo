# Authentication & Security

This document details the authentication system, including new features for email verification and password reset implemented in January 2026.

## Overview

The application uses standard session-based authentication via `Flask-Login`. Passwords are hashed using `scrypt` (via `werkzeug.security`).

## Session Lifetime

- **Credential-bound sessions** (ADR-055): the session id carries a
  fingerprint of the password hash, so changing the password invalidates every
  open session.
- **No "remember me"** and no server-side lifetime for directors and players:
  a session lasts as long as the browser keeps its cookie.
- **Admin idle timeout** (ADR-063): the admin is logged out after
  `ADMIN_IDLE_TIMEOUT` (30 minutes, `config.py`) without opening a page. The
  last activity lives in the signed session cookie (`_admin_ultima_attivita`),
  not in `user_session`, which is analytics only. Live-update polls
  (`/sse/poll/*`) do **not** count as activity: an expired poll gets 401 and
  the page shows the "session expired" notice. Pages redirect to the login
  with a flash message and, for GET requests, a `next` back to where the admin
  was.

## Email Verification

New users must verify their email address before their account is fully activated (though currently they can still login, but with a warning).

- **Flow**:
    1. User registers.
    2. A random secure token is generated (32 bytes, URL-safe).
    3. Token is stored in `user_token` table with type `verification`.
    4. Email is sent via SMTP containing a link: `/auth/verify-email/<token>`.
    5. User clicks link -> `is_verified` flag on `user` table is set to `TRUE`.

- **Manual Request**: Users can request a new verification email from their profile page if they haven't verified yet.

## Password Reset

Allows users to recover access if they forget their password.

- **Flow**:
    1. User requests reset at `/auth/forgot-password`.
    2. Token is generated with type `password_reset`.
    3. Email is sent with link: `/auth/reset-password/<token>`.
    4. User sets new password -> Token is consumed and invalidated.

## Configuration

The system uses **Flask-Mail** to send emails via SMTP.

| Variable | Description | Example (Gmail) |
|----------|-------------|-----------------|
| `MAIL_SERVER` | SMTP Server Host | `smtp.gmail.com` |
| `MAIL_PORT` | SMTP Port | `587` |
| `MAIL_USE_TLS` | Use TLS | `true` |
| `MAIL_USERNAME` | SMTP Username | `user@gmail.com` |
| `MAIL_PASSWORD` | SMTP Password | `app-password` |
| `MAIL_DEFAULT_SENDER` | "From" Address | `Name <email>` |

## Database Schema Changes

### User Table (`user`)
- Added `is_verified` (BOOLEAN, default: False) - Tracks verification status.

### User Token Table (`user_token`)
New table for managing secure tokens.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer | PK |
| `user_id` | Integer | FK to User |
| `token` | String(100) | Unique secure token |
| `token_type` | String(20) | `verification` or `password_reset` |
| `created_at` | DateTime | Timestamp |
| `expires_at` | DateTime | Expiration timestamp |
| `is_used` | Boolean | If token has been consumed |
