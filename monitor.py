"""Public bug bounty changes -> Telegram. Python standard library only."""
import argparse
import copy
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SOURCE = 'https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/'
PLATFORMS = ('hackerone', 'bugcrowd')


class MonitorError(Exception):
    pass


def download(platform):
    for attempt in range(3):
        try:
            request = urllib.request.Request(SOURCE + platform + '_data.json',
                                             headers={'User-Agent': 'bounty-telegram-monitor/1.0'})
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except (OSError, ValueError):
            if attempt == 2:
                raise MonitorError(f'{platform}: feed unavailable or invalid; baseline kept.') from None
            time.sleep(2 ** attempt)


def normalize(platform, rows):
    if not isinstance(rows, list) or not rows:
        raise MonitorError(f'{platform}: empty or malformed feed; baseline kept.')
    programs = {}
    host = 'hackerone.com' if platform == 'hackerone' else 'bugcrowd.com'
    for row in rows:
        if not isinstance(row, dict):
            raise MonitorError(f'{platform}: invalid program record.')
        url = row.get('url', '')
        if not isinstance(url, str) or urllib.parse.urlsplit(url).hostname != host:
            raise MonitorError(f'{platform}: invalid program URL.')
        if not isinstance(row.get('name'), str) or not row['name'].strip():
            raise MonitorError(f'{platform}: missing program name.')
        scopes = row.get('targets', {}).get('in_scope')
        if not isinstance(scopes, list):
            raise MonitorError(f'{platform}: missing scope list.')
        assets = {}
        for target in scopes:
            if not isinstance(target, dict):
                raise MonitorError(f'{platform}: invalid asset.')
            identifier = target.get('asset_identifier') if platform == 'hackerone' else target.get('target')
            kind = target.get('asset_type') if platform == 'hackerone' else target.get('type')
            if not isinstance(identifier, str) or not identifier.strip():
                raise MonitorError(f'{platform}: missing asset identifier.')
            if platform == 'hackerone' and target.get('eligible_for_submission') is False:
                continue
            if '\u2588' in identifier:  # Do not alert about redacted target placeholders.
                continue
            kind = str(kind or 'other').strip().lower()
            identifier = identifier.strip()  # Preserve case, URL paths and wildcard semantics.
            key = json.dumps([kind, identifier], ensure_ascii=False)
            assets[key] = {'type': kind, 'identifier': identifier,
                           'bounty': target.get('eligible_for_bounty') if platform == 'hackerone' else None}
        key = url.rstrip('/')
        if key in programs:
            raise MonitorError(f'{platform}: duplicate program URL.')
        programs[key] = {'name': row['name'].strip(), 'url': url, 'assets': assets}
    return programs


def chunks(text, size=1800):
    # Telegram counts UTF-16 code units; the smaller character limit leaves room.
    lines, current = text.splitlines(), ''
    for line in lines:
        while len(line) > size:
            if current:
                yield current
                current = ''
            yield line[:size]
            line = line[size:]
        if len(current) + len(line) + 1 > size:
            yield current
            current = ''
        current += ('\n' if current else '') + line
    if current:
        yield current


def update(state, platform, current):
    """Keep previously seen records across feed omissions to avoid false relaunches."""
    old = state['platforms'].get(platform)
    if old is None:
        state['platforms'][platform] = current
        state['pending'].append(f'Monitor ready: {platform.title()} baseline saved '
                                f'({len(current)} programs). Future additions will appear here.')
        return
    for key, program in current.items():
        previous = old.get(key)
        added = [asset for asset_key, asset in program['assets'].items()
                 if previous is None or asset_key not in previous['assets']]
        rewarded = [] if previous is None else [asset for asset_key, asset in program['assets'].items()
                    if asset_key in previous['assets'] and asset['bounty'] is True
                    and previous['assets'][asset_key]['bounty'] is not True]
        if previous is None or added or rewarded:
            label = 'NEW PROGRAM' if previous is None else 'SCOPE UPDATE'
            lines = [f'{label} | {platform.title()}', program['name'], program['url']]
            if added:
                lines += [f'New in-scope assets: {len(added)}']
                lines += [f"+ [{a['type']}] {a['identifier']}" for a in sorted(added, key=lambda a: (a['type'], a['identifier']))]
            if rewarded:
                lines += ['Now bounty eligible:'] + [f"$ {a['identifier']}" for a in rewarded]
            lines += ['', 'First seen in the public feed. Check the current program policy before testing.']
            state['pending'].extend(chunks('\n'.join(lines)))
        merged = copy.deepcopy(previous['assets']) if previous else {}
        merged.update(program['assets'])
        old[key] = {**program, 'assets': merged}


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def send_message(token, chat_id, message):
    body = json.dumps({'chat_id': chat_id, 'text': message,
                       'link_preview_options': {'is_disabled': True}}).encode()
    request = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',
                                     data=body, headers={'Content-Type': 'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
            if not result.get('ok'):
                raise MonitorError('Telegram rejected the message. Check the bot and chat secrets.')
            return
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt < 2:
                try:
                    delay = int(json.load(error).get('parameters', {}).get('retry_after', 5))
                except (ValueError, TypeError):
                    delay = 5
                time.sleep(min(max(delay, 1), 60))
                continue
            raise MonitorError(f'Telegram HTTP {error.code}; undelivered alerts retained.') from None
        except (OSError, ValueError):
            # A timeout can occur after Telegram received the message. Retain it;
            # retry next run rather than claiming delivery or dropping an alert.
            raise MonitorError('Telegram connection failed; undelivered alerts retained.') from None


def deliver(state, path, token, chat_id, sender=send_message):
    for _ in range(min(len(state['pending']), 80)):
        sender(token, chat_id, state['pending'][0])
        state['pending'].pop(0)
        save(path, state)
        time.sleep(1.1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', default='state.json')
    parser.add_argument('--dry-run', action='store_true', help='Read live feeds without sending or saving.')
    parser.add_argument('--test-message', action='store_true')
    args = parser.parse_args()
    token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN', ''), os.getenv('TELEGRAM_CHAT_ID', '')
    if not args.dry_run and (not token or not chat_id):
        raise MonitorError('Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in repository Settings > Secrets and variables > Actions.')
    if args.test_message:
        if args.dry_run:
            raise MonitorError('Choose either --dry-run or --test-message.')
        send_message(token, chat_id, 'Telegram connection works. Your bug bounty monitor can send alerts here.')
        print('Test message sent.')
        return
    path = Path(args.state)
    state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version': 1, 'platforms': {}, 'pending': []}
    if state.get('version') != 1 or not isinstance(state.get('platforms'), dict) or not isinstance(state.get('pending'), list):
        raise MonitorError('Invalid saved state; refusing to reset the baseline.')
    failures = []
    for platform in PLATFORMS:
        try:
            current = normalize(platform, download(platform))
            update(state, platform, current)
            print(f'{platform}: {len(current)} public programs checked.')
        except MonitorError as error:
            failures.append(str(error))
    if args.dry_run:
        print(f"Dry run: {len(state['pending'])} messages would be queued; nothing saved or sent.")
    else:
        # Daily timestamp creates a real daily repository commit and keeps the
        # public repository active even during a long period without new scopes.
        state['last_checked_date'] = dt.datetime.now(dt.timezone.utc).date().isoformat()
        save(path, state)
        deliver(state, path, token, chat_id)
        print(f"Delivery complete; {len(state['pending'])} messages pending.")
    if failures:
        raise MonitorError(' '.join(failures))


if __name__ == '__main__':
    try:
        main()
    except (MonitorError, OSError, ValueError) as error:
        # Never print HTTP request URLs (Telegram tokens are embedded in them).
        print('ERROR: ' + (str(error) if isinstance(error, MonitorError) else 'Local state or configuration error.'), file=sys.stderr)
        sys.exit(1)
