import requests
from bs4 import BeautifulSoup

r = requests.get(
    'https://www.boatrace.jp/owpc/pc/race/pay',
    params={'jcd':'21','hd':'20260507','rno':'1'},
    headers={'User-Agent':'Mozilla/5.0'}
)
soup = BeautifulSoup(r.text, 'html.parser')

for a in soup.find_all('a', href=True):
    if any(k in a['href'] for k in ['pay', 'haraimodoshi', 'odds', 'race']):
        print(a['href'])