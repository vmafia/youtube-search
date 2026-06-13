import requests
url = 'https://glasp.co/reader?url=https://www.youtube.com/watch?v=-0YQxmVNZk0'
res = requests.get(url)
print('transcripts\":[]' in res.text or 'transcripts\\\\":[]' in res.text)
