import json
import logging
import os
import os.path

from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent, \
        PreferencesEvent, PreferencesUpdateEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction

logging.basicConfig()
logger = logging.getLogger(__name__)

fuzz = None

def is_module_installed(module):
    import imp
    try:
        imp.find_module(module)
    except ImportError:
        return False
    return True

class PreferencesEventListener(EventListener):
    def on_event(self, event, extension):
        extension.set_preferences(event.preferences)


class PreferencesUpdateEventListener(EventListener):
    def on_event(self, event, extension):
        p = extension.preferences.copy()
        p[event.id] = event.new_value
        extension.set_preferences(p)


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        return extension.get_results(event.get_argument())


class Bookmarks(Extension):

    bookmarks_files = {
        'chromium': '~/.config/chromium/Default/Bookmarks',
        'google': '~/.config/google-chrome/Default/Bookmarks',
        'yandex': '~/.config/yandex-browser-beta/Default/Bookmarks',
    }

    def __init__(self):
        super(Bookmarks, self).__init__()
        self.bookmarks_file = None
        self.results = []
        self.last_error = None

        self.set_preferences({
            'keyword': 'b',
            'browser': 'chromium',
            'bookmarks_file': '',
        })

        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(PreferencesEvent, PreferencesEventListener())
        self.subscribe(PreferencesUpdateEvent, PreferencesUpdateEventListener())

    def set_preferences(self, p):
        self.preferences = p
        prev_file = self.bookmarks_file
        if p['browser'] == 'custom':
            self.bookmarks_file = p['bookmarks_file']
        else:
            self.bookmarks_file = self.bookmarks_files[p['browser']]
        if prev_file != self.bookmarks_file:
            self.update_cache()

    def notify(self, msg, desc):
        return RenderResultListAction([ExtensionResultItem(
            icon='images/error.svg',
            name=msg.encode('utf8'),
            description=desc.encode('utf8')
        )])

    def get_results(self, query):
        if self.last_error is not None:
            return self.notify(**self.last_error)

        items = []
        for i, item in enumerate(self.match(query)):
            if i > 10:
                break
            bookmark = item['bookmark']
            items.append(ExtensionResultItem(icon='images/bookmark.svg',
                name=bookmark['name'].encode('utf8'),
                description=bookmark['url'].encode('utf8'),
                on_enter=OpenUrlAction(bookmark['url'].encode('utf8'))))
        return RenderResultListAction(items)

    def update_cache(self):
        self.last_error = None

        if fuzz is None:
            if not is_module_installed('fuzzywuzzy'):
                self.last_error = {
                    'msg': "Python module 'fuzzywuzzy' was not found",
                    'desc': u"Please install this module by pip and restart ULauncher",
                }
                return
            else:
                global fuzz
                from fuzzywuzzy import fuzz as f
                fuzz = f

        if self.bookmarks_file == '':
            self.last_error = {
                'msg': "Bookmarks file is not specified",
                'desc': u"Please specify either browser or bookmarks file in Preferences",
            }
            return

        try:
            with open(os.path.expanduser(self.bookmarks_file)) as f:
                content = json.load(f)
        except:
            self.last_error = {
                'msg': "Failed to open file '{}'".format(self.bookmarks_file),
                'desc': u"Check that file exists and is readable",
            }
            return

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
