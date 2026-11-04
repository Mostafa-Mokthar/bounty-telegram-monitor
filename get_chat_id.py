"""Optional one-time helper. Token stays off command lines, URLs and logs."""
import getpass
import json
import urllib.request


def main():
    print('Open your new Telegram bot and send /start before continuing.')
    token = getpass.getpass('BotFather token (hidden): ').strip()
    if not token:
        print('No token entered.')
        return
    try:
        request = urllib.request.Request(f'https://api.telegram.org/bot{token}/getUpdates',
                                         data=b'limit=100&timeout=0',
                                         headers={'Content-Type': 'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        chats = {}
        for update in data.get('result', []):
            message = update.get('message', {})
            chat = message.get('chat', {})
            if chat.get('type') == 'private' and str(message.get('text', '')).startswith('/start'):
                chats[chat['id']] = chat.get('first_name', '')
        if not chats:
            print('No /start message found. Send /start to your new bot now, then run this helper again.')
        else:
            for chat_id, name in chats.items():
                print(f'TELEGRAM_CHAT_ID = {chat_id} ({name})')
            print('Choose your own chat if multiple IDs are listed. Save it and the token in GitHub Secrets.')
    except (OSError, ValueError):
        print('Could not read Telegram updates. Check the token and connection. The token has not been printed.')


if __name__ == '__main__':
    main()
