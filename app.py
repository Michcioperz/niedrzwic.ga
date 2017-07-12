import datetime
import os
import pytz
import requests
from urllib.parse import urljoin
from html import escape
from flask import Flask, request
from werkzeug.contrib.atom import AtomFeed
import bs4

app = Flask(__name__)

REDIS_PAGE_SCHEMA = 'page:{page}'
REDIS_TTL = 600

TITLE = "Gmina Niedrzwica Duża – aktualności"
URL = 'http://niedrzwicaduza.pl'
TIMEZONE = pytz.timezone('Europe/Warsaw')

if 'REDIS_DB' in os.environ:
    try:
        import simplejson as json
    except ImportError:
        import json
    import redis
    cache = redis.Redis(db=int(os.environ['REDIS_DB']))
else:
    cache = None

if 'SENTRY_DSN' in os.environ:
    from raven.contrib.flask import Sentry
    sentry = Sentry(app, dsn=os.environ['SENTRY_DSN'])

def fetch_page(page):
    r = requests.get('http://niedrzwicaduza.pl', params=dict(p=str(page)))
    r.raise_for_status()
    r.encoding = 'utf-8'
    dom = bs4.BeautifulSoup(r.text, 'lxml')
    newses = dom.find('ul', class_='newses').children
    items = []
    for news in newses:
        if type(news) != bs4.element.Tag or news.name != 'li':
            continue
        item = dict()
        item['url'] = news.find('a', class_='news_lead_img').get('href')
        item['title'] = news.find('h2', class_='news_title').get_text(strip=True)
        item['updated'] = news.find('span', class_='news_date').get_text(strip=True)
        item['content'] = str(news.find('p', class_='news_lead'))
        item['img'] = urljoin(URL, news.find('img', alt='Zdjęcie Artykułu').get('src'))
        items.append(item)
    return items

def get_page(page):
    content = None
    if cache is not None:
        content_json = cache.get(REDIS_PAGE_SCHEMA.format(page=page))
        if content_json is not None:
            content = json.loads(content_json)
    if content is None:
        content = fetch_page(page)
        if cache is not None:
            cache.set(REDIS_PAGE_SCHEMA.format(page=page), json.dumps(content), ex=REDIS_TTL)
    for item in content:
        item['updated'] = TIMEZONE.localize(datetime.datetime.strptime(item['updated'], '%Y-%m-%d %H:%M:%S'))
    return content

def atom_items(items):
    feed = AtomFeed(TITLE, feed_url=request.url, url=URL)
    for item in items:
        feed.add(item['title'], '<img src="{}">'.format(escape(item['img']))+item['content'], content_type='html', url=item['url'], updated=item['updated'])
    return feed.get_response()

@app.route('/<int:page>/')
def atom_page(page):
    return atom_items(get_page(page))

@app.route('/')
def atom_home():
    return atom_items(get_page(1)+get_page(2)+get_page(3))

if __name__ == '__main__':
    app.run(port=os.environ['APP_PORT'])
