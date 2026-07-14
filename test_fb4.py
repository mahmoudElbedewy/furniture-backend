import requests
url = 'https://www.facebook.com/profile.php?id=61591261844925'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
r = requests.get(url, headers=headers)
with open('fb_out.html', 'w', encoding='utf-8') as f:
    f.write(r.text)
