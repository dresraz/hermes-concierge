# Demo shotlist: 88 seconds

Record the terminal only, 1080p, font at 16 or larger. No music, no captions needed if the audio is
clean. Rehearse once before recording, then undo whatever the rehearsal installed.

Start Hermes in the repo you actually use:

```
hermes
```

| # | Time | On screen | Say (short) |
|---|---|---|---|
| 1 | 0-5 | terminal, prompt | "Adding something to an agent is usually a research project." |
| 2 | 5-18 | type `/concierge read my rss feeds` | "So I ask for it in one sentence." |
| 3 | 18-26 | the card | "One card: what it is, what it adds, what it costs on every request, and the exact commit." |
| 4 | 26-32 | type `/concierge yes`, receipt appears | "One yes, and it installs through Hermes's own installer and scan gate." |
| 5 | 32-40 | the receipt | "The receipt is read back off the disk, not remembered." |
| 6 | 40-48 | type `/concierge undo`, receipt | "And undo removes exactly what it added." |
| 7 | 48-64 | type `/concierge hire a researcher for papers`, receipt | "Same sentence works for a whole bot: a role, its catalog skills, and a soul you can train later." |
| 8 | 64-72 | type `/concierge a bot that writes my taxes` | "And when nothing fits, it installs nothing and says so." |
| 9 | 72-82 | type `/concierge bots` | "It also keeps track of the bots it made." |
| 10 | 82-88 | back to prompt | "One sentence, one card, one receipt, one undo. Concierge is in the catalog." |

## What you should see on screen

Card for beat 2 and 3:

```
Concierge

  you said    read my rss feeds
  best match  rss-reader  (community, desktop)
  why         rss, feeds
  what        Desktop RSS reader with reader-mode capture, drag-reorder subscriptions, mute
              rules, saved searches, AI summaries, keyboard shortcuts, and an optional ...
  adds        1 tool
  cost        1 tool, sent on every request like every other tool
  install     https://github.com/apoapostolov/hermes-agent-awesome-plugins v1.1.0 @ 30d6dc6311bf

Install it?  /concierge yes   or   /concierge no
```

Hire beat (verified on 2026-11-06, real session):

```
Hired inbox-bot

    home     /home/andres/.hermes/profiles/inbox-bot
    soul     SOUL.md, 985 chars
    skills   8 installed
    profile  listed by hermes profile list
  skills   assistant 7/7 installed: email-inbox-triage, google-workspace, microsoft-office,
           pdf, document-to-action-items, weekly-review-planning +1 more

  next     /concierge train inbox-bot: <habit>
  undo     /concierge undo
```

Bots beat:

```
  BOTS  1

   1  inbox-bot  Keeps my inbox at zero

  fire <n>    delete that bot
  reset <n>   take back what Concierge changed in it
```

Nothing-fits beat:

```
Concierge

  you said    a bot that writes my taxes
  best match  none

Nothing in the catalog does that yet. Nothing was installed.
```

## Rules for a clean recording

- A card and its `/concierge yes` must happen in the same session. That is normal in one chat, but
  it will not work if you show the card in one session and answer in another.


- Rehearse once, then run `/concierge undo` and `hermes profile delete researcher-bot --yes` so the
  recorded run starts clean.
- Do not edit or speed up the video. Cut nothing between beats, or the cut is the story.
- If an install takes longer than ten seconds on camera, cut away and come back, then say how long
  it took.
- Do not show the file system, keys, or any other profile.
- Under 90 seconds or it does not count.

## Post text

```
Adding stuff to @NousResearch Hermes Agent is a research project. I made it one sentence:
say what you want, get one card, say yes, get a receipt you can check, and /concierge undo
removes exactly what it added. It also hires whole bots from a sentence. #HermesAgent
```
