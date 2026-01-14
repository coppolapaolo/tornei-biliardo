# Mobile-First Gara View Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace table-based match display with card-based layout on mobile devices (< 768px).

**Architecture:** Two separate templates switched via Bootstrap CSS classes (`d-md-none` / `d-none d-md-block`). Desktop remains unchanged. Mobile uses card stack with touch-friendly actions.

**Tech Stack:** Jinja2 templates, Bootstrap 5.3, existing JavaScript functions (no new JS needed).

---

## Task 1: Create Single Match Card Component

**Files:**
- Create: `templates/components/_match_card.html`

**Step 1: Create the base card structure**

Create `templates/components/_match_card.html`:

```html
{# templates/components/_match_card.html #}
{# Expects: match, user_can_manage, available_tables, match_can_modify, forfeit_user_ids, user_inscription #}

{% set p1_wins = match.status == 'completed' and match.winner_id == match.player1_id %}
{% set p2_wins = match.status == 'completed' and match.winner_id == match.player2_id %}
{% set p1_forfeit = forfeit_user_ids is defined and match.player1_id in forfeit_user_ids %}
{% set p2_forfeit = forfeit_user_ids is defined and match.player2_id in forfeit_user_ids %}
{% set is_my_match = user_inscription and current_user.is_authenticated and (match.player1_id == current_user.id or match.player2_id == current_user.id) %}

{# Determine card border color based on status #}
{% set status_class = 'border-warning' if match.status == 'pending' else ('border-primary' if match.status == 'playing' else 'border-success') %}
{% if match.is_bye %}{% set status_class = 'border-info' %}{% endif %}

<div class="card mb-3 {{ status_class }}" style="border-width: 2px;">
  {# === HEADER === #}
  <div class="card-header py-2 d-flex justify-content-between align-items-center">
    <div>
      {% if match.is_bye %}
      <span class="badge bg-info">{{ _('Bye') }}</span>
      {% elif match.status == 'pending' %}
      <span class="badge bg-warning text-dark">{{ _('In Attesa') }}</span>
      {% elif match.status == 'playing' %}
      <span class="badge bg-primary">{{ _('In Corso') }}</span>
      {% elif match.status == 'completed' %}
      <span class="badge bg-success">{{ _('Completata') }}</span>
      {% endif %}

      {% if match.is_trio and match.trio_match %}
      <span class="badge bg-secondary ms-1"><i class="fas fa-users"></i> {{ _('Trio') }}</span>
      {% endif %}
    </div>

    {# Table badge #}
    <div>
      {% if match.is_bye or match.status == 'completed' %}
        {# No table shown #}
      {% elif user_can_manage and available_tables %}
        {% if match.is_trio and match.trio_match %}
          {% set player_display = match.trio_match.player1.username ~ ' · ' ~ match.trio_match.player2.username ~ ' · ' ~ match.trio_match.player3.username %}
        {% else %}
          {% set player_display = match.player1.username ~ ' vs ' ~ (match.player2.username if not match.is_bye else _('Bye')) %}
        {% endif %}
        {% if match.table_assignment %}
        <span class="badge bg-primary" style="cursor: pointer; min-height: 32px; line-height: 20px;"
              data-bs-toggle="modal" data-bs-target="#tableAssignmentModal"
              onclick='openTableAssignment({{ match.id }}, "{{ match.table_assignment }}", {{ player_display|tojson }}, "")'>
          <i class="fas fa-table"></i> {{ match.table_assignment }}
        </span>
        {% else %}
        <span class="badge bg-warning text-dark" style="cursor: pointer; min-height: 32px; line-height: 20px;"
              data-bs-toggle="modal" data-bs-target="#tableAssignmentModal"
              onclick='openTableAssignment({{ match.id }}, null, {{ player_display|tojson }}, "")'>
          <i class="fas fa-plus-circle"></i> {{ _('Assegna') }}
        </span>
        {% endif %}
      {% elif match.table_assignment %}
        <span class="badge bg-secondary">
          <i class="fas fa-table"></i> {{ match.table_assignment }}
        </span>
      {% endif %}
    </div>
  </div>

  {# === BODY: Players and Score === #}
  <div class="card-body py-3 text-center">
    {% if match.is_trio and match.trio_match %}
      {% set trio = match.trio_match %}
      {% set p3_wins = match.status == 'completed' and match.winner_id == trio.player3_id %}
      {% set p3_forfeit = forfeit_user_ids is defined and trio.player3_id in forfeit_user_ids %}

      {# Trio: 3 players #}
      <div class="d-flex justify-content-center align-items-center gap-2 flex-wrap">
        <span class="{% if p1_forfeit %}text-muted text-decoration-line-through{% endif %}">
          <strong>{{ trio.player1.username }}</strong>
          {% if p1_wins %}<i class="fas fa-crown text-warning"></i>{% endif %}
          {% if p1_forfeit %}<i class="fas fa-ban text-secondary"></i>{% endif %}
        </span>
        <span class="text-muted">·</span>
        <span class="{% if p2_forfeit %}text-muted text-decoration-line-through{% endif %}">
          <strong>{{ trio.player2.username }}</strong>
          {% if p2_wins %}<i class="fas fa-crown text-warning"></i>{% endif %}
          {% if p2_forfeit %}<i class="fas fa-ban text-secondary"></i>{% endif %}
        </span>
        <span class="text-muted">·</span>
        <span class="{% if p3_forfeit %}text-muted text-decoration-line-through{% endif %}">
          <strong>{{ trio.player3.username }}</strong>
          {% if p3_wins %}<i class="fas fa-crown text-warning"></i>{% endif %}
          {% if p3_forfeit %}<i class="fas fa-ban text-secondary"></i>{% endif %}
        </span>
      </div>

      {# Trio score #}
      <div class="mt-2">
        {% if match.status == 'completed' %}
        <span class="badge bg-info fs-6">{{ trio.player1_racks }} - {{ trio.player2_racks }} - {{ trio.player3_racks }}</span>
        {% elif trio.player1_racks > 0 or trio.player2_racks > 0 or trio.player3_racks > 0 %}
        <span class="badge bg-warning fs-6">{{ trio.player1_racks }} - {{ trio.player2_racks }} - {{ trio.player3_racks }}</span>
        {% endif %}
      </div>

    {% else %}
      {# Normal match: 2 players #}
      <div class="d-flex justify-content-center align-items-center gap-3">
        <span class="{% if p1_forfeit %}text-muted text-decoration-line-through{% endif %}">
          <strong>{{ match.player1.username }}</strong>
          {% if p1_wins %}<i class="fas fa-crown text-warning ms-1"></i>{% endif %}
          {% if p1_forfeit %}<i class="fas fa-ban text-secondary ms-1"></i>{% endif %}
        </span>

        <span class="text-muted">vs</span>

        {% if match.is_bye %}
        <em class="text-muted">{{ _('Bye') }}</em>
        {% else %}
        <span class="{% if p2_forfeit %}text-muted text-decoration-line-through{% endif %}">
          <strong>{{ match.player2.username }}</strong>
          {% if p2_wins %}<i class="fas fa-crown text-warning ms-1"></i>{% endif %}
          {% if p2_forfeit %}<i class="fas fa-ban text-secondary ms-1"></i>{% endif %}
        </span>
        {% endif %}
      </div>

      {# Score #}
      {% if not match.is_bye %}
      <div class="mt-2">
        {% if match.status == 'completed' %}
        <span class="badge bg-info fs-6">{{ match.player1_score }} - {{ match.player2_score }}</span>
        {% elif match.player1_score > 0 or match.player2_score > 0 %}
        <span class="badge bg-warning fs-6">{{ match.player1_score }} - {{ match.player2_score }}</span>
        {% endif %}
      </div>
      {% endif %}
    {% endif %}
  </div>

  {# === FOOTER: Actions === #}
  {% if not match.is_bye %}
  <div class="card-footer py-2">
    {% if user_can_manage %}
      {# Director/Admin actions #}
      {% set can_modify = match_can_modify.get(match.id, True) %}
      {% set has_table = match.table_assignment %}
      {% set has_scores = (match.player1_score > 0 or match.player2_score > 0) %}
      {% if match.is_trio and match.trio_match %}
        {% set has_scores = (match.trio_match.player1_racks > 0 or match.trio_match.player2_racks > 0 or match.trio_match.player3_racks > 0) %}
      {% endif %}

      {% if not can_modify %}
        {# Locked #}
        <div class="text-center text-muted">
          <i class="fas fa-lock"></i> {{ _('Bloccato') }}
        </div>
      {% elif not has_table and match.status != 'completed' %}
        {# Need to assign table first #}
        <div class="text-center text-muted small">
          <i class="fas fa-clock"></i> {{ _('Assegna tavolo per abilitare azioni') }}
        </div>
      {% else %}
        {# Actions available #}
        <div class="d-flex flex-wrap gap-2">
          {% if match.status != 'completed' %}
            {# Quick Result button #}
            {% if match.is_trio and match.trio_match %}
              {% set trio = match.trio_match %}
              <button class="btn btn-warning flex-grow-1" style="min-height: 44px;"
                      data-bs-toggle="modal" data-bs-target="#quickResultModal"
                      onclick="openQuickResultTrio({{ match.id }}, {{ trio.id }}, '{{ trio.player1.username }}', '{{ trio.player2.username }}', '{{ trio.player3.username }}', {{ trio.player1_racks }}, {{ trio.player2_racks }}, {{ trio.player3_racks }})">
                <i class="fas fa-tachometer-alt"></i> {{ _('Risultato') }}
              </button>
            {% else %}
              <button class="btn btn-warning flex-grow-1" style="min-height: 44px;"
                      data-bs-toggle="modal" data-bs-target="#quickResultModal"
                      onclick="openQuickResult({{ match.id }}, '{{ match.player1.username }}', '{{ match.player2.username }}', {{ match.player1_score }}, {{ match.player2_score }})">
                <i class="fas fa-tachometer-alt"></i> {{ _('Risultato') }}
              </button>
            {% endif %}

            {# Validate button (if winner exists but not validated) #}
            {% if match.winner_id and not match.validated_by_admin %}
            <button class="btn btn-success" style="min-height: 44px;" onclick="validateMatchQuick({{ match.id }})">
              <i class="fas fa-check-circle"></i>
            </button>
            {% endif %}

            {# Detail link #}
            <a href="{{ url_for('admin.match.match_detail', match_id=match.id) }}" class="btn btn-outline-primary" style="min-height: 44px;">
              <i class="fas fa-edit"></i>
            </a>
          {% endif %}

          {# Reset button (if completed or has scores) #}
          {% if match.status == 'completed' or has_scores %}
            {% if match.is_trio and match.trio_match %}
            <button class="btn btn-outline-danger" style="min-height: 44px;" onclick="resetTrioQuick({{ match.trio_match.id }})">
              <i class="fas fa-undo"></i>
            </button>
            {% else %}
            <button class="btn btn-outline-danger" style="min-height: 44px;" onclick="resetMatchQuick({{ match.id }})">
              <i class="fas fa-undo"></i>
            </button>
            {% endif %}
          {% endif %}
        </div>
      {% endif %}

    {% elif is_my_match %}
      {# Player's own match - link to detail #}
      <div class="d-grid">
        <a href="{{ url_for('admin.match.match_detail', match_id=match.id) }}" class="btn btn-outline-primary" style="min-height: 44px;">
          <i class="fas fa-eye"></i> {{ _('Vai alla Partita') }}
        </a>
      </div>

    {% else %}
      {# Guest or other player's match - no actions #}
    {% endif %}
  </div>
  {% endif %}
</div>
```

**Step 2: Verify template syntax**

Run:
```bash
cd /Users/paolo/My\ Drive/Programming/Python/tornei-biliardo && python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
env.get_template('components/_match_card.html')
print('Template syntax OK')
"
```

Expected: `Template syntax OK`

**Step 3: Commit**

```bash
git add templates/components/_match_card.html
git commit -m "feat(mobile): add single match card component

Touch-friendly card with:
- Status badge + table assignment in header
- Players and score in body
- Contextual actions in footer (role-based)
"
```

---

## Task 2: Create Mobile Match Cards Container

**Files:**
- Create: `templates/components/_match_cards_mobile.html`

**Step 1: Create the container template**

Create `templates/components/_match_cards_mobile.html`:

```html
{# templates/components/_match_cards_mobile.html #}
{# Mobile card-based view for matches - replaces table on small screens #}
{# Uses same variables as _gara_matches.html #}

{% set display_matches = all_matches if all_matches else matches %}
{% if display_matches %}
<div class="card">
  <div class="card-header">
    <h5 class="mb-0"><i class="fas fa-shield-halved"></i> {{ _('Partite') }}</h5>
  </div>
  <div class="card-body">
    {# Collect rounds by status #}
    {% set active_rounds = [] %}
    {% set completed_rounds = [] %}

    {% for round_num in range(1, gara.rounds_count + 1) %}
      {% set round_matches = display_matches | selectattr("round_number", "equalto", round_num) | list %}
      {% if round_matches %}
        {% set has_playing = round_matches | selectattr("status", "equalto", "playing") | list | length > 0 %}
        {% set has_pending = round_matches | selectattr("status", "equalto", "pending") | list | length > 0 %}
        {% set all_completed = round_matches | selectattr("status", "equalto", "completed") | list | length == round_matches | length %}

        {% if has_playing or has_pending %}
          {% set _void = active_rounds.append(round_num) %}
        {% elif all_completed %}
          {% set _void = completed_rounds.append(round_num) %}
        {% endif %}
      {% endif %}
    {% endfor %}

    {# Display active rounds first #}
    {% for round_num in active_rounds %}
      {% set round_matches = display_matches | selectattr("round_number", "equalto", round_num) | list %}
      <h6 class="mt-3 mb-3 pb-2 border-bottom">
        <i class="fas fa-play-circle text-primary"></i> {{ _('Turno %(num)s', num=round_num) }}
      </h6>
      {% for match in round_matches %}
        {% include "components/_match_card.html" %}
      {% endfor %}
    {% endfor %}

    {# Then display completed rounds #}
    {% for round_num in completed_rounds %}
      {% set round_matches = display_matches | selectattr("round_number", "equalto", round_num) | list %}
      <h6 class="mt-4 mb-3 pb-2 border-bottom text-muted">
        <i class="fas fa-check-circle text-success"></i> {{ _('Turno %(num)s', num=round_num) }}
      </h6>
      {% for match in round_matches %}
        {% include "components/_match_card.html" %}
      {% endfor %}
    {% endfor %}
  </div>
</div>
{% endif %}
```

**Step 2: Verify template syntax**

Run:
```bash
cd /Users/paolo/My\ Drive/Programming/Python/tornei-biliardo && python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
env.get_template('components/_match_cards_mobile.html')
print('Template syntax OK')
"
```

Expected: `Template syntax OK`

**Step 3: Commit**

```bash
git add templates/components/_match_cards_mobile.html
git commit -m "feat(mobile): add match cards container

Groups matches by round with active rounds first.
Same logic as _gara_matches.html but renders cards.
"
```

---

## Task 3: Create Mobile Classification Component

**Files:**
- Create: `templates/components/_classification_mobile.html`

**Step 1: Create the classification template**

Create `templates/components/_classification_mobile.html`:

```html
{# templates/components/_classification_mobile.html #}
{# Mobile-friendly classification with compact/full toggle #}
{# Expects: classification, round_number #}

{% if classification %}
<div class="card mt-3">
  <div class="card-header py-2 d-flex justify-content-between align-items-center">
    <h6 class="mb-0"><i class="fas fa-trophy"></i> {{ _('Classifica') }}</h6>
    <select class="form-select form-select-sm" style="width: auto;"
            onchange="toggleClassificationView(this.value)" id="classificationViewToggle">
      <option value="compact">{{ _('Compatta') }}</option>
      <option value="full">{{ _('Completa') }}</option>
    </select>
  </div>
  <div class="card-body py-2">
    {# Compact view (default) #}
    <div id="classificationCompact">
      <table class="table table-sm mb-0">
        <tbody>
          {% for entry in classification[:6] %}
          <tr>
            <td style="width: 40px;">
              {% if loop.index == 1 %}
              <span class="text-warning"><i class="fas fa-medal"></i></span>
              {% elif loop.index == 2 %}
              <span class="text-secondary"><i class="fas fa-medal"></i></span>
              {% elif loop.index == 3 %}
              <span class="text-danger"><i class="fas fa-medal"></i></span>
              {% else %}
              <span class="text-muted">{{ loop.index }}°</span>
              {% endif %}
            </td>
            <td><strong>{{ entry.username }}</strong></td>
            <td class="text-end">
              <span class="badge bg-secondary">{{ entry.rack_totali }}</span>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% if classification|length > 6 %}
      <div class="text-center mt-2">
        <button class="btn btn-sm btn-link" onclick="document.getElementById('classificationViewToggle').value='full'; toggleClassificationView('full');">
          {{ _('Mostra tutti (%(count)s)', count=classification|length) }}
        </button>
      </div>
      {% endif %}
    </div>

    {# Full view (hidden by default) #}
    <div id="classificationFull" style="display: none;">
      {% for entry in classification %}
      <div class="border-bottom py-2 {% if loop.index <= 3 %}bg-light{% endif %}">
        <div class="d-flex justify-content-between align-items-center">
          <div>
            {% if loop.index == 1 %}
            <span class="text-warning"><i class="fas fa-medal"></i></span>
            {% elif loop.index == 2 %}
            <span class="text-secondary"><i class="fas fa-medal"></i></span>
            {% elif loop.index == 3 %}
            <span class="text-danger"><i class="fas fa-medal"></i></span>
            {% else %}
            <span class="text-muted">{{ loop.index }}°</span>
            {% endif %}
            <strong class="ms-2">{{ entry.username }}</strong>
          </div>
          <span class="badge bg-secondary">{{ entry.rack_totali }}</span>
        </div>
        <div class="small text-muted mt-1 ms-4">
          {% if entry.posizione_precedente %}
          {{ _('Pos. Prec:') }} {{ entry.posizione_precedente }}°
          {% if entry.movimento > 0 %}
          <span class="text-success"><i class="fas fa-arrow-up"></i> {{ entry.movimento }}</span>
          {% elif entry.movimento < 0 %}
          <span class="text-danger"><i class="fas fa-arrow-down"></i> {{ entry.movimento|abs }}</span>
          {% else %}
          <span class="text-muted">=</span>
          {% endif %}
          {% else %}
          {{ _('Pos. Prec:') }} —
          {% endif %}
          {% if entry.ssr_score %}
          · SSR: {{ entry.ssr_score }}
          {% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
  </div>
</div>

<script>
function toggleClassificationView(view) {
  document.getElementById('classificationCompact').style.display = view === 'compact' ? 'block' : 'none';
  document.getElementById('classificationFull').style.display = view === 'full' ? 'block' : 'none';
}
</script>
{% endif %}
```

**Step 2: Verify template syntax**

Run:
```bash
cd /Users/paolo/My\ Drive/Programming/Python/tornei-biliardo && python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
env.get_template('components/_classification_mobile.html')
print('Template syntax OK')
"
```

Expected: `Template syntax OK`

**Step 3: Commit**

```bash
git add templates/components/_classification_mobile.html
git commit -m "feat(mobile): add classification with compact/full toggle

Shows top 6 in compact view, expandable to full view
with previous position and SSR score details.
"
```

---

## Task 4: Integrate Mobile Views in gara_detail.html

**Files:**
- Modify: `templates/gara_detail.html`

**Step 1: Add mobile switch for matches section**

In `templates/gara_detail.html`, find the matches section (around line 57-69) and wrap with responsive classes:

```html
{# Sezione Partite - adattiva #}
<div class="row">
  <div class="col-md-8">
    {# === MOBILE VIEW (< 768px) === #}
    <div class="d-md-none">
      {% include "components/_match_cards_mobile.html" %}
    </div>

    {# === DESKTOP VIEW (>= 768px) === #}
    <div class="d-none d-md-block">
      {% if user_can_manage %}
      {% include "components/_gara_matches.html" %}
      {% elif user_inscription %}
      {% include "components/_gara_matches.html" %}
      {% else %}
      {% include "components/_gara_matches.html" %}
      {% endif %}
    </div>

    {# SSR Section remains unchanged... #}
```

**Step 2: Add mobile classification in sidebar**

Find the classification section (around line 152-158) and add mobile version:

```html
  <div class="col-md-4">
    {# === MOBILE: Classification appears here on mobile === #}
    <div class="d-md-none">
      {% if current_round_classification %}
      {% with classification=current_round_classification, round_number=latest_round_with_classification %}
      {% include "components/_classification_mobile.html" %}
      {% endwith %}
      {% endif %}
    </div>

    {# === DESKTOP: Original classification === #}
    <div class="d-none d-md-block">
      {% if current_round_classification %}
      {% with classification=current_round_classification, round_number=latest_round_with_classification %}
      {% include "components/_detailed_classification.html" %}
      {% endwith %}
      {% endif %}
    </div>

    {# Iscrizioni... #}
```

**Step 3: Make collapsible sections for mobile**

Wrap Info Gara and Iscritti sections for mobile collapse:

The info section is in the first row. For mobile, we can use Bootstrap collapse. This is optional - can be done in a follow-up task.

**Step 4: Test in browser**

1. Start the dev server: `python app.py`
2. Open a gara detail page in browser
3. Use DevTools to toggle mobile view (< 768px)
4. Verify:
   - Cards show instead of table on mobile
   - Actions work correctly
   - Table shows on desktop

**Step 5: Commit**

```bash
git add templates/gara_detail.html
git commit -m "feat(mobile): integrate card view in gara detail

Switch between card (mobile) and table (desktop) at 768px.
Uses Bootstrap d-md-none / d-none d-md-block classes.
"
```

---

## Task 5: Visual Testing and Refinements

**Step 1: Test all match states on mobile**

Create test scenarios:
1. Match PENDING without table
2. Match PENDING with table
3. Match PLAYING with partial score
4. Match PLAYING with final score (validate button)
5. Match COMPLETED
6. TRIO match
7. BYE match
8. Locked match

**Step 2: Test all user roles**

1. As Director - all actions visible
2. As Player (own match) - "Vai alla Partita" link
3. As Player (other's match) - no actions
4. As Guest - no actions

**Step 3: Verify touch targets**

Use browser DevTools to check:
- Buttons are at least 44px height
- Adequate spacing between buttons
- Badges are tappable

**Step 4: Fix any issues found**

Document and fix issues in separate commits.

**Step 5: Final commit**

```bash
git add -A
git commit -m "fix(mobile): refinements from visual testing"
```

---

## Task 6: Add Collapsible Sections (Optional Enhancement)

**Files:**
- Modify: `templates/gara_detail.html`
- Modify: `templates/components/_gara_info.html`
- Modify: `templates/components/_gara_inscriptions.html`

This task makes Info Gara and Iscritti collapsible on mobile. Can be implemented in a follow-up PR if needed.

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Single match card component | `_match_card.html` |
| 2 | Cards container | `_match_cards_mobile.html` |
| 3 | Mobile classification | `_classification_mobile.html` |
| 4 | Integration in gara_detail | `gara_detail.html` |
| 5 | Visual testing | - |
| 6 | Collapsible sections (optional) | Multiple |

**Estimated commits:** 5-6

**Testing approach:** Manual visual testing in browser with DevTools mobile view.
