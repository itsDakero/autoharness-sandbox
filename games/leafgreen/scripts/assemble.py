"""Build dist/index.html from src/ and data/. Run from the project root: python3 scripts/assemble.py"""
import os
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
r = lambda *p: open(os.path.join(root, *p), encoding='utf-8').read()
h = r('src', 'app.html')
h = h.replace('/*__DATA__*/', r('data', 'game.json'), 1)
h = h.replace('/*__TRAINERS__*/', r('data', 'trainers.json'), 1)
h = h.replace('/*__WALK__*/', r('src', 'walk.js'), 1)
h = h.replace('/*__ROUTE__*/', r('data', 'route.json'), 1)
os.makedirs(os.path.join(root, 'dist'), exist_ok=True)
open(os.path.join(root, 'dist', 'index.html'), 'w', encoding='utf-8').write(h)
print('dist/index.html', len(h) // 1024, 'KB')
