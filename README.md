# Reddit Ban Checker

A small Windows app that checks whether Reddit accounts are active, suspended, or missing, without opening a browser.

> **Known limitation:** this app uses Reddit's public, logged-out profile data. Reddit can block these requests depending on your network, and every row then shows `Error` with a 403 message. Trying a different connection or turning off a VPN may help.

## Install

1. Open [Releases](../../releases/latest) and download `RedditBanChecker.exe`.
2. Double-click it. There is nothing to install and no Python needed.

The exe isn't code-signed, so Windows may show "Windows protected your PC". Click **More info**, then **Run anyway**.

## Use

Paste usernames (one per line) or click **Load file…**, then click **Check**. `u/name` and profile links work too. Use **Export CSV…** to save the results.

| Status | Meaning |
| --- | --- |
| Active | The profile is public. Shows karma and creation date. |
| Suspended (banned) | Reddit reports the account as suspended. |
| Not found / shadowbanned / deleted | The profile returns a 404. These three cases look identical from outside. |
| Invalid username | Not a valid Reddit username format. |
| Error | Network problem, or Reddit blocked or rate-limited the request. Try a longer delay. |

## Build from source

```
pip install pyinstaller
pyinstaller --onefile --windowed --name RedditBanChecker reddit_ban_checker.py
```

The exe is written to `dist/`.
