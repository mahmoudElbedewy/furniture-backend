import requests, re
url = 'https://www.facebook.com/profile.php?id=61591261844925'
headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
r = requests.get(url, headers=headers)
# Find the exact text blocks
import json
matches = re.findall(r'"text":"(.*?)"', r.text)
for m in matches:
    try:
        decoded = m.encode('latin1').decode('unicode_escape')
        if 'المتابع' in decoded or 'followers' in decoded.lower():
            print("MATCH:", decoded)
    except Exception as e:
        pass
