# Refined Gamification System (V2)

**Date**: 2026-01-24
**Status**: Implemented

This document describes the "Invisible/Signal-based" Gamification system implemented to replace the previous widget-based approach.

## Overview

The system has been redesigned to be less intrusive ("polite") and more mobile-friendly. Instead of persistent dashboard widgets taking up screen space, gamification elements are now ubiquitous but subtle.

### Core Components

1.  **Navbar Badge** (Persistent)
    *   **Location**: Top Navigation Bar (Blue header).
    *   **Visibility**: Always visible on all pages (Desktop & Mobile).
    *   **Content**: 🏆 Icon + Current Level ( + XP on Desktop).
    *   **Behavior**: Click directs to the detailed Gamification Dashboard.
    *   **Implementation**: Injected via `inject_gamification` context processor in `app.py`.

2.  **Toast Notification System** (Transient)
    *   **Location**: Top-right corner (standard toast container).
    *   **Behavior**: Events trigger animated toasts featuring the "Chalky" mascot.
    *   **Events Covered**:
        *   `WELCOME`: On login (Gender-neutral "Che piacere rivederti!").
        *   `XP`: When points are gained.
        *   `LEVEL_UP`: Celebration with confetti.
        *   `ACHIEVEMENT`: Trophy unlock (Bronze/Silver/Gold/Legendary).
        *   `STREAK`: Weekly streak updates.
        *   `QUEST`: Quest completion.

3.  **Frontend Bridge**
    *   **File**: `models/gamification/frontend_bridge.py`
    *   **Mechanism**: Listens to Domain Events -> Flashes special `gamification_event` messages to Flask session -> `base.html` captures them -> `gamification.js` renders animations.
    *   **Safety**: Messages are consumed separately from standard Bootstrap alerts to prevent raw JSON from leaking into the UI.

## Internationalization (I18N)

All visible strings are internationalized using Flask-Babel (`gettext`).
- Welcome messages use gender-neutral phrasing in Italian.
- Dynamic titles/subtitles are passed from Backend to Frontend.

## usage

### Triggering Manual Events
You can manually trigger events (like Welcome) using the helper:

```python
from models.gamification.frontend_bridge import flash_gamification_event, GamificationEventType

flash_gamification_event(GamificationEventType.WELCOME, {
    "username": current_user.username,
    "title": _("Che piacere rivederti!"),
    "subtitle": _("Tutto pronto per giocare?")
})
```

### Adding New Events
1. Add new type to `GamificationEventType` enum.
2. Update `gamification.js` switch case to handle the new type.
3. Ensure appropriate Mascot image exists in `static/img`.

## Files Reference

- `app.py`: Context Processor.
- `templates/base.html`: Navbar integration & Message consumption logic.
- `static/js/gamification.js`: Animation logic & Mascot definitions.
- `models/gamification/`: Backend logic & Bridges.
