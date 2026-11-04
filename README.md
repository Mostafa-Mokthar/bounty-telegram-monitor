# Free bug bounty alerts for Telegram

Runs on GitHub's computers every hour, even when your computer is off. Watches public HackerOne and Bugcrowd data for newly observed programs and in-scope assets, including paid programs and VDPs. Also detects HackerOne assets becoming bounty eligible. No HackerOne/Bugcrowd login or paid services are required.

## Setup

1. Create a **public** GitHub repository named `bounty-telegram-monitor`. Standard GitHub-hosted runners in public repositories are free. Use only public data in this project.
2. Upload the project contents, preserving `.github/workflows/monitor.yml` and `tests/test_monitor.py`. Upload the extracted files, not the ZIP itself. Files must be at the repository root, not inside an extra enclosing folder. The Actions tab should show **Bug bounty Telegram alerts**.
3. In Telegram, open the official [@BotFather](https://t.me/BotFather), send `/newbot`, and follow its instructions. Keep the returned token private. Open your new bot and press **Start**.
4. Get your numeric Telegram chat ID: run the included `python get_chat_id.py` once. It asks for the bot token without displaying it, then reads the `/start` message you sent to your bot. Your computer is needed only for this optional setup helper, not for monitoring. Alternatively, you can obtain your numeric Telegram user ID through a Telegram ID bot, which is a separate third party.
5. In your GitHub repository, open **Settings > Secrets and variables > Actions > New repository secret**. Add:

   | Secret | Value |
   | --- | --- |
   | `TELEGRAM_BOT_TOKEN` | The token from BotFather |
   | `TELEGRAM_CHAT_ID` | Your numeric chat ID |

   Never add these values to a code file, a repository variable, an issue, or a screenshot.

6. Open **Actions > Bug bounty Telegram alerts > Run workflow**. Leave the test checkbox off for the first full run. You should receive two baseline confirmations, one per platform. Existing programs are saved silently; they do not generate individual alerts.
7. Later checks run at minute 17 of every hour (GitHub schedules may be delayed). To test only delivery, manually run the workflow with **Send a Telegram test message** checked.

The workflow has a repository-scoped `contents: write` permission to save `state.json`. If a repository or organization rule blocks this, the save step will fail visibly; do not ignore that failure, because delivery history would not persist. The workflow does not run on pull requests or execute external program content.

## What you receive

```text
SCOPE UPDATE | Hackerone
Example
https://hackerone.com/example
New in-scope assets: 1
+ [wildcard] *.new.example.com
```

Only baseline confirmations and detected changes generate Telegram messages. Run failures appear in GitHub Actions; enable GitHub's Actions failure notifications in your account if you want email alerts about failures.

## How it remembers changes

`state.json` stores previously observed programs, assets, and pending messages. State is saved before delivery and after each successful message. A failed delivery is retried on a later run. Messages are paced and limited to 80 per run; excess messages remain queued.

Delivery is **at least once**: an uncertain Telegram timeout, abrupt runner termination, or failed GitHub state push can occasionally cause a duplicate. Normal successful runs do not repeat the same additions.

Previously observed programs and assets are retained when absent from the feed, so temporary omissions do not create false relaunches. Consequently, removal followed by re-addition of the same asset is not alerted. Scope removals, arbitrary policy edits, reward amount changes, and private programs are not covered. A new-program alert means newly observed in this feed, which may include programs that were already live before feed coverage began.

A daily state timestamp produces a daily repository commit while runs succeed, keeping the public repository active. GitHub automatically disables public repository schedules after 60 days without repository activity; a persistently broken workflow still needs attention.

## Cost and timing

- Standard GitHub-hosted runners for **public** repositories are free. This project uses those runners and no paid APIs, external storage, or server.
- Private repositories use your plan's allowance and may incur charges beyond it. Keep this repository public for the intended free setup.
- The public data source currently advertises checks every 30 minutes. Our monitor checks hourly, so alerts depend on both schedules and feed availability. It is not an instant launch feed.
- Scheduled GitHub jobs can be delayed or dropped under load. Check the latest successful run occasionally.
- Feed availability is not guaranteed. Malformed or unavailable platform data does not replace that platform's baseline.
- An alert is a discovery hint. Always review the platform's live scope and policy before testing.

## Local verification (optional)

Requires Python 3.10 or later; no packages need installing.

```sh
python -m unittest discover -s tests -v
python monitor.py --dry-run
```

Dry runs read live public feeds without sending messages or saving state. GitHub Actions uses Python 3.12 and runs the tests automatically.

## Sources

- [Public scope feed and its update cadence](https://github.com/arkadiyt/bounty-targets-data)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub schedule limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
- [Telegram Bot API](https://core.telegram.org/bots/api)

The monitor code is supplied for your use and modification. Feed data remains with its respective source and owners; this repository downloads it at runtime.
