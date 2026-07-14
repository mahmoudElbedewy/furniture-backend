import requests, re
url = 'https://www.facebook.com/profile.php?id=61591261844925'
headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
r = requests.get(url, headers=headers)
meta_desc = re.search(r'<meta name="description" content="(.*?)"', r.text)
if meta_desc:
    desc = meta_desc.group(1)
    print("META:", desc)
