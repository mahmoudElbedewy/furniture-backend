import requests, re, json
url = 'https://www.facebook.com/profile.php?id=61591261844925'
headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
r = requests.get(url, headers=headers)
match = re.search(r'"profile_social_context":\s*({.*?})', r.text)
if match:
    context = json.loads(match.group(1))
    for item in context.get('content', []):
        uri = item.get('uri', '')
        if 'sk=followers' in uri:
            f_text = item.get('text', {}).get('text', '')
            arabic_to_english = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
            decoded = f_text.translate(arabic_to_english)
            digits = re.findall(r'(\d+[\d,.]*[KkMm]?)', decoded)
            print('Found digits:', digits)
            
            if digits:
                val = digits[0].replace(',', '')
                if 'k' in val.lower():
                    print('Count:', int(float(val.lower().replace('k', '')) * 1000))
                elif 'm' in val.lower():
                    print('Count:', int(float(val.lower().replace('m', '')) * 1000000))
                else:
                    print('Count:', int(val))
else:
    print('No match found')
