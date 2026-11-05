# Concierge demo script (90 seconds)

One sentence in, one card out, one decision. This shot list is the recording script. Total run time is 70 seconds, under the 90 second cap.

## Shot list

| Beat | Time | On screen | Typed | Narration |
|------|------|-----------|-------|-----------|
| 1 | 0:00-0:10 | Hermes prompt, blank line | `/concierge remember my notes across sessions` | One sentence goes in. |
| 2 | 0:10-0:20 | The Concierge card: best match, why, adds, cost, install line | <enter> | The card names the match, the words that earned it, and what it adds. |
| 3 | 0:20-0:25 | Card asks Install it? | `yes` | One answer: yes. |
| 4 | 0:25-0:40 | Hermes's own scan report prints, then the caution prompt again | `yes` | Core's report lands before the final yes; a caution needs a second yes. |
| 5 | 0:40-0:55 | Receipt: on disk path with file count, enabled, scan verdict | none | The receipt reports what is actually on disk, counted file by file. |
| 6 | 0:55-1:10 | Second card: best match none, nothing installed | `/concierge pilot my spaceship` | When nothing fits, Concierge says so and installs nothing. |

Total: 70 seconds.

If the first plugin rates safe instead of caution, beat 4 does not appear and the receipt follows the first yes; the rest of the script is unchanged.

## Prep checklist (before recording)

- Fresh plugin dir: install Concierge into a clean plugin directory with no leftover state from earlier runs.
- No leftover install: run `/concierge undo` first, or record on a profile with no concierge install record, so the install starts clean.
- Key requirement: if the card's `adds` line names a requirement label (the `needs ...` words), name that label aloud but never show its value and never type a key on camera.
- Type the sentences exactly as written; do not improvise.

## Fallback: network or catalog unavailable

`match.py` ranks without a model and `card.py` renders without core, so the card still works when the catalog cannot load. Skip `seams.catalog()` and render the card from a one-entry fixture:

```
cd /home/andres/concierge
python - <<'EOF'
import importlib, pathlib, sys, types
root = pathlib.Path('/home/andres/concierge')
pkg = types.ModuleType('concierge_under_test')
pkg.__path__ = [str(root)]
sys.modules['concierge_under_test'] = pkg
match = importlib.import_module('concierge_under_test.match')
card = importlib.import_module('concierge_under_test.card')

class E:
    def __init__(self, **kw):
        self.__dict__.update(kw)

caps = {'provides_tools': ['recall', 'forget'], 'provides_hooks': [], 'requires_env': ['API_KEY']}
entry = E(name='cognee', title='Cognee Memory', description='Knowledge-graph memory for Hermes: recall, notes, code search', tier='community', category='memory', capabilities=caps, sha='b13274096018abcdef0123456789', repo='https://github.com/topoteretes/cognee-integrations', version='1.4.1')
cands = match.rank('remember my notes across sessions', [entry], limit=2)
print(card.render('remember my notes across sessions', cands))
print('======')
print(card.nothing('pilot my spaceship'))
EOF
```

That command prints the full card and the honest nothing-fits card, with no network call at all. Its `adds` line names the requirement label `needs API_KEY`: name the label, never the value.