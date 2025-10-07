# Template Migration Guide - Distance/Score Filters

**Purpose**: Guide for migrating templates to use the new Distance/Score Jinja filters.

**Status**: Optional incremental migration - templates work as-is, migration improves UX.

---

## Quick Reference

### Available Filters

```jinja
{# Full distance display #}
{{ gara|format_distance }}
→ "Best of 7 racks"
→ "Best of 3 sets, each set best of 5 racks"

{# Score display #}
{{ match|format_score }}
→ "4-2"
→ "2-1" (sets in multi-set)

{# Short distance format #}
{{ gara|format_distance_short }}
→ "BO7"
→ "X4"
```

---

## Migration Patterns

### Pattern 1: Simple Distance Display

**Before**:
```jinja
{% if gara.best_of %}
    Al meglio di {{ gara.distance }} rack
{% else %}
    Esattamente {{ gara.distance }} rack
{% endif %}
```

**After**:
```jinja
{{ gara|format_distance }}
```

**Benefits**:
- 3 lines → 1 line
- No logic in template
- Consistent formatting
- Supports multi-set automatically

---

### Pattern 2: Match Score Display

**Before**:
```jinja
{{ match.player1_score }} - {{ match.player2_score }}
```

**After**:
```jinja
{{ match|format_score }}
```

**Benefits**:
- Cleaner syntax
- Works with both single-set and multi-set
- Handles trio matches automatically (3 players)

---

### Pattern 3: Compact Distance Badge

**Before**:
```jinja
<span class="badge">
    {% if gara.best_of %}BO{% else %}X{% endif %}{{ gara.distance }}
</span>
```

**After**:
```jinja
<span class="badge">{{ gara|format_distance_short }}</span>
```

**Benefits**:
- Simpler syntax
- Type-safe

---

### Pattern 4: Match Details Card

**Before**:
```jinja
<div class="match-info">
    <p>Distanza:
        {% if gara.best_of %}
            Al meglio di {{ gara.distance }}
        {% else %}
            {{ gara.distance }} rack esatti
        {% endif %}
    </p>
    <p>Score: {{ match.player1_score }}-{{ match.player2_score }}</p>
</div>
```

**After**:
```jinja
<div class="match-info">
    <p>Distanza: {{ gara|format_distance }}</p>
    <p>Score: {{ match|format_score }}</p>
</div>
```

**Benefits**:
- Much cleaner
- Easier to maintain
- Consistent formatting

---

## Real-World Examples

### Example 1: Gara Detail Page

**File**: `templates/garas/detail.html`

**Before**:
```jinja
<div class="gara-header">
    <h2>{{ gara.name }}</h2>
    <p class="discipline">{{ gara.discipline }}</p>
    <p class="distance">
        {% if gara.best_of %}
            Al meglio di {{ gara.distance }} rack
        {% else %}
            Esattamente {{ gara.distance }} rack
        {% endif %}
    </p>
</div>
```

**After**:
```jinja
<div class="gara-header">
    <h2>{{ gara.name }}</h2>
    <p class="discipline">{{ gara.discipline }}</p>
    <p class="distance">{{ gara|format_distance }}</p>
</div>
```

---

### Example 2: Match List

**File**: `templates/matches/list.html`

**Before**:
```jinja
{% for match in matches %}
<tr>
    <td>{{ match.player1.username }}</td>
    <td>{{ match.player2.username }}</td>
    <td>{{ match.player1_score }}-{{ match.player2_score }}</td>
    <td>
        {% if match.gara.best_of %}BO{% else %}X{% endif %}{{ match.gara.distance }}
    </td>
</tr>
{% endfor %}
```

**After**:
```jinja
{% for match in matches %}
<tr>
    <td>{{ match.player1.username }}</td>
    <td>{{ match.player2.username }}</td>
    <td>{{ match|format_score }}</td>
    <td>{{ match.gara|format_distance_short }}</td>
</tr>
{% endfor %}
```

---

### Example 3: Multi-Set Match Display

**Before**: Would need complex logic to handle multi-set
```jinja
{% if match.is_multi_set %}
    Set vinti: {{ match.player1_score }}-{{ match.player2_score }}
    <br>
    Formato: {{ match.match_distance }} set, {{ match.gara.distance }} rack per set
{% else %}
    Rack vinti: {{ match.player1_score }}-{{ match.player2_score }}
    <br>
    {% if match.gara.best_of %}Al meglio di{% else %}Esattamente{% endif %}
    {{ match.gara.distance }} rack
{% endif %}
```

**After**: Filters handle complexity automatically
```jinja
Score: {{ match|format_score }}
<br>
Formato: {{ match|format_distance }}
```

---

## Migration Priority

### High Priority (User-Facing)
Templates that display match/gara info to users:
- `templates/garas/detail.html`
- `templates/garas/list.html`
- `templates/matches/detail.html`
- `templates/matches/list.html`
- `templates/public/gara_detail.html`

### Medium Priority (Forms/Admin)
Templates with distance configuration:
- `templates/garas/create.html`
- `templates/garas/edit.html`
- `templates/admin/gara_management.html`

### Low Priority (Internal)
Templates with complex logic that already works:
- Internal admin tools
- Debug views

---

## Testing After Migration

### Manual Testing Checklist

For each migrated template:
- [ ] View renders without errors
- [ ] Distance displays correctly
- [ ] Score displays correctly
- [ ] Multi-set matches display properly (if applicable)
- [ ] Trio matches show 3 scores (if applicable)
- [ ] UI looks good on mobile

### Visual Regression
Before/after screenshots recommended for:
- Gara list pages
- Match detail pages
- Tournament brackets

---

## Common Issues & Solutions

### Issue 1: Filter Not Found

**Error**: `jinja2.exceptions.UndefinedError: 'format_distance' is undefined`

**Solution**: Ensure filters are registered in `app.py`:
```python
from utils.jinja import format_distance, format_score, format_distance_short
app.jinja_env.filters["format_distance"] = format_distance
```

### Issue 2: None Values

**Error**: Filter receives None

**Solution**: Filters handle None gracefully:
- `format_distance(None)` → "N/A"
- `format_score(None)` → "0-0"

No template changes needed.

### Issue 3: Multi-Set Match Display

**Before**: Unsure which filter to use

**Solution**:
- Use `format_distance` on match or gara (shows full format)
- Use `format_score` on match (automatically detects single vs multi-set)

---

## Migration Strategy

### Recommended Approach: Incremental

1. **Week 1**: Migrate high-priority user-facing pages
2. **Week 2**: Migrate medium-priority admin pages
3. **Week 3+**: Migrate remaining templates as needed

### Alternative: All at Once

If preferred, can migrate all templates in one PR:
- Search for: `gara.best_of`, `gara.distance`, `player.*_score`
- Replace with appropriate filters
- Test thoroughly
- Deploy

---

## Statistics

**Total Templates with Distance/Score**: ~42
**Estimated Time per Template**: 5-15 minutes
**Total Estimated Time**: 3-10 hours (depending on complexity)

**Expected Improvements**:
- ~30% reduction in template code
- Better maintainability
- Consistent formatting
- Automatic multi-set support

---

## Support

**Questions?**
- Check `tests/new/unit/test_jinja_filters.py` for usage examples
- See `utils/jinja.py` for filter implementation
- Refer to `docs/refactoring/DISTANCE_SCORE_REFACTOR.md` for context

**Issues?**
- Verify filters are registered in `app.py`
- Check that value objects are imported correctly
- Run `pytest tests/new/unit/test_jinja_filters.py` to verify filters work
