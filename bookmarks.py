import json
import logging
import os
import os.path
from fuzzywuzzy import fuzz

from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent, PreferencesEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction

logging.basicConfig()
logger = logging.getLogger(__name__)


class PreferencesEventListener(EventListener):
    def on_event(self, event, extension):
        pass

class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        items = []
        for i, item in enumerate(extension.match(event.get_argument())):
            if i > 10:
                break
            bookmark = item['bookmark']
            items.append(ExtensionResultItem(icon='images/yandex_browser.png',
                name=bookmark['name'].encode('utf8'),
                description=bookmark['url'].encode('utf8'),
                on_enter=OpenUrlAction(bookmark['url'].encode('utf8'))))
        return RenderResultListAction(items)


class Bookmarks(Extension):

    def __init__(self):
        super(Bookmarks, self).__init__()
        self.bookmarks_file = self.search_bookmarks_file()
        # self.update_cache()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(PreferencesEvent, PreferencesEventListener())

    def update_cache(self):

        with open(self.bookmarks_file) as f:
            content = json.load(f)

        self.bookmarks = []

        items = content['roots'].values()
        while len(items) > 0:

            item = items.pop(0)
            if 'type' not in item:
                continue

            if item['type'] == 'folder':
                if 'children' in item:
                    items = items + item['children']

            elif item['type'] == 'url':
                if 'url' not in item or len(item['url']) == 0:
                    continue
                self.bookmarks.append({
                    'key': item.get('name', '').lower() + item['url'].lower(),
                    'url': item['url'],
                    'name': item.get('name', ''),
                })

        self.results = [{
            'char': None,
            'scored_items': [{'bookmark': b, 'score': 0} for b in self.bookmarks],
        }]

    @staticmethod
    def search_bookmarks_file():
        f = os.popen('locate google-chrome | grep Bookmarks')

        home_dir = os.path.expanduser('~')
        return u'Bookmarks'

        f = os.popen('locate google-chrome | grep Bookmarks')
        res = f.read()
        res = res.split('\n')
        if len(res) == 0:
            logger.exception('Path to the Chrome Bookmarks was not found')
        if len(res) > 1:
            for i in range(0, len(res)):
                if res[i][-9:] == 'Bookmarks':
                    return res[i]

        logger.exception('Path to the Chrome Bookmarks was not found')

    def match(self, query):

        if query is None:
            query = ''
        if len(query) < 1:
            return []

        prev_query = ''.join([r['char'] for r in self.results[1:]])
        common_prefix = os.path.commonprefix([prev_query, query])
        self.results = self.results[:len(common_prefix) + 1]
        query_suffix = query[len(common_prefix):]

        for c in query_suffix:
            items = []
            for item in self.results[-1]['scored_items']:
                bookmark = item['bookmark']
                score = fuzz.partial_token_sort_ratio(bookmark['key'], query)
                items.append({
                    'bookmark': bookmark,
                    'score': score,
                })
            items = sorted(items, key=lambda i: i['score'], reverse=True)
            items = items[:int(len(items))]
            self.results.append({
                'char': c,
                'scored_items': items
            })

        return self.results[-1]['scored_items']
