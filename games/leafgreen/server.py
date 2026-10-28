"""LeafGreen Field Notes server: serves dist/index.html and stores the save as one JSON file.

GET  /            the app
GET  /api/state   the save ({} if none yet)
PUT  /api/state   replace the save; refused (409 + current save) if it is older than the stored one
GET  /api/cards?dex=<n>&name=<Species>  printings of a species from TCGdex (cached 7 days, stale cache if TCGdex is down)
GET  /api/cards/prices  the price history the host cron (scripts/card-prices.py) writes; {} if none yet
GET  /healthz     ok
Every response carries X-App-Version (hash of the page) so open pages can reload after a deploy.
Before an accepted PUT, the previous save is copied to backups/ if the newest copy is over an hour old
(newest KEEP kept, so about KEEP hours of play to roll back to).
"""
import hashlib, json, os, re, shutil, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('DATA_DIR', '/data')
STATE = os.path.join(DATA, 'state.json')
BACKUPS = os.path.join(DATA, 'backups')
KEEP = 100
EVERY = 3600
MAX_BODY = 1 << 20
PAGE = open(os.path.join(ROOT, 'dist', 'index.html'), 'rb').read()
VERSION = hashlib.sha256(PAGE).hexdigest()[:12]   # open pages reload when this changes
lock = threading.Lock()

# ----- Cards (TCGdex, free, no key; Cardmarket EUR prices updated daily) -----
TCGDEX = 'https://api.tcgdex.net/v2/en'
CARDS = os.path.join(DATA, 'cards')
CACHE = os.path.join(CARDS, 'cache')
PRICES = os.path.join(CARDS, 'prices.json')   # written only by scripts/card-prices.py
CACHE_DAYS = 7
MAX_CARDS = 300
# Rarity strings, compared lowercase. Cards with any other rarity are dropped.
MODERN = {'illustration rare', 'special illustration rare', 'ultra rare', 'rare ultra', 'hyper rare',
          'mega hyper rare', 'secret rare', 'rare secret'}
RETRO = {'rare holo', 'holo rare', 'rare holo lv.x', 'rare holo star', 'rare shining', 'rare prime'}
species_locks = {}
species_locks_guard = threading.Lock()


def tcgdex(path, tries=3):
    """GET a TCGdex path as JSON; 2 retries with backoff. Raises on failure."""
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(TCGDEX + path, headers={'User-Agent': 'homelab-leafgreen'})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as e:
            err = e
            if i < tries - 1:
                time.sleep(1 + i * 2)
    raise err


def cache_read(name, stale_ok=False):
    path = os.path.join(CACHE, name)
    try:
        if not stale_ok and time.time() - os.path.getmtime(path) > CACHE_DAYS * 86400:
            return None
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def cache_write(name, data):
    try:
        os.makedirs(CACHE, exist_ok=True)
        path = os.path.join(CACHE, name)
        tmp = path + '.tmp%d' % threading.get_ident()
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass   # a read-only or full disk must not break the page


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def card_detail(cid):
    """Raw card JSON: fresh cache, else TCGdex, else stale cache, else None."""
    safe = re.sub(r'[^A-Za-z0-9._-]', '_', cid)
    got = cache_read('card-%s.json' % safe)
    if got is not None:
        return got
    try:
        d = tcgdex('/cards/' + urllib.parse.quote(cid, safe=''))
        if isinstance(d, dict) and d.get('id'):
            cache_write('card-%s.json' % safe, d)
            return d
    except Exception:
        pass
    return cache_read('card-%s.json' % safe, stale_ok=True)


def shape(d, dex):
    """One card for the page, or None (wrong species, other rarity)."""
    ids = d.get('dexId') or []
    if dex not in ids:
        return None
    rar = (d.get('rarity') or '').strip().lower()
    kind = 'modern' if rar in MODERN else 'retro' if rar in RETRO else None
    if not kind or not d.get('image'):
        return None
    cm = ((d.get('pricing') or {}).get('cardmarket')) or {}
    def pick(k):
        return num(cm.get(k)) or num(cm.get(k + '-holo'))
    eur = {k: pick(k) for k in ('low', 'trend', 'avg', 'avg7', 'avg30')}
    eur['updated'] = cm.get('updated')
    s = d.get('set') or {}
    return {'id': d['id'], 'name': d.get('name'), 'localId': d.get('localId'),
            'set': {'id': s.get('id'), 'name': s.get('name')}, 'rarity': d.get('rarity'),
            'image': d['image'], 'kind': kind, 'eur': eur}


def species_lock(dex):
    with species_locks_guard:
        return species_locks.setdefault(dex, threading.Lock())


def cards_for(dex, name):
    """({'cards': [...], 'stale'?: true, 'error'?: str}). Never raises."""
    key = 'species-%d.json' % dex
    with species_lock(dex):
        got = cache_read(key)
        if got is not None:
            return {'cards': got}
        try:
            brief = tcgdex('/cards?name=' + urllib.parse.quote(name))
            if not isinstance(brief, list):
                raise ValueError('bad list')
            ids = [b['id'] for b in brief if isinstance(b, dict) and b.get('id')][:MAX_CARDS]
            with ThreadPoolExecutor(4) as ex:
                details = list(ex.map(card_detail, ids))
            cards = [c for c in (shape(d, dex) for d in details if d) if c]
            if ids and not any(details):
                raise ValueError('no card details')
            if sum(1 for d in details if d) < len(ids):
                return {'cards': cards, 'partial': True}   # not cached: retry on the next request
            cache_write(key, cards)
            return {'cards': cards}
        except Exception:
            old = cache_read(key, stale_ok=True)
            if old is not None:
                return {'cards': old, 'stale': True}
            return {'cards': [], 'error': "Card prices can't load now."}


def load_prices():
    try:
        with open(PRICES, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def load():
    try:
        with open(STATE, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def store(new):
    os.makedirs(BACKUPS, exist_ok=True)
    copies = sorted(os.listdir(BACKUPS))
    last = os.path.getmtime(os.path.join(BACKUPS, copies[-1])) if copies else 0
    if os.path.exists(STATE) and time.time() - last >= EVERY:
        shutil.copy(STATE, os.path.join(BACKUPS, time.strftime('state-%Y%m%d-%H%M%S.json')))
        for old in sorted(os.listdir(BACKUPS))[:-KEEP]:
            os.remove(os.path.join(BACKUPS, old))
    tmp = STATE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(new, f, ensure_ascii=False)
    os.replace(tmp, STATE)


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype='application/json'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-App-Version', VERSION)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/api/cards':
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                dex = int(q.get('dex', [''])[0])
                name = q.get('name', [''])[0].strip()[:40]
                if not 1 <= dex <= 1025 or not name:
                    raise ValueError
            except ValueError:
                return self.send(400, {'error': 'need dex and name'})
            return self.send(200, cards_for(dex, name))
        if path == '/api/cards/prices':
            return self.send(200, load_prices())
        if path in ('/', '/index.html'):
            self.send(200, PAGE, 'text/html; charset=utf-8')
        elif path == '/api/state':
            with lock:
                self.send(200, load())
        elif path == '/healthz':
            self.send(200, b'ok', 'text/plain')
        else:
            self.send(404, {'error': 'not found'})

    def do_PUT(self):
        if self.path.split('?')[0] != '/api/state':
            return self.send(404, {'error': 'not found'})
        n = int(self.headers.get('Content-Length') or 0)
        if not 0 < n <= MAX_BODY:
            return self.send(413, {'error': 'empty or too large'})
        try:
            new = json.loads(self.rfile.read(n))
        except ValueError:
            return self.send(400, {'error': 'not JSON'})
        if not isinstance(new, dict) or not isinstance(new.get('savedAt'), (int, float)):
            return self.send(400, {'error': 'need an object with savedAt'})
        with lock:
            cur = load()
            if (cur.get('savedAt') or 0) > new['savedAt']:
                return self.send(409, cur)
            store(new)
        self.send(200, {'savedAt': new['savedAt']})

    def log_message(self, fmt, *args):
        if not self.path.startswith('/healthz'):
            super().log_message(fmt, *args)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT') or 8080)), Handler).serve_forever()
