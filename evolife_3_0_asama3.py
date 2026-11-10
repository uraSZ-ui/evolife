import math
import random
from collections import deque
import json
from pathlib import Path
import pygame

pygame.init()
W, H, WORLD_H = 1120, 780, 650
screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
clock = pygame.time.Clock()
font = pygame.font.SysFont('consolas', 17)
small = pygame.font.SysFont('consolas', 14)
BG = (13, 28, 38)
MAX_POP = 1500
START_POP = 90
FOOD_MAX = 500
FOOD_ENERGY = 25
CELL_RADIUS = 5
cells = []
foods = []
next_id = 0
births = deaths = ticks = 0
paused = False
speed_factor = 1
history = deque(maxlen=210)
predations = 0
SAVE_FILE = Path(__file__).with_name("evolife_3_save.json")
selected_id = None
inspector_open = True
PANEL_W = 315
ANCESTOR_LIMIT = 32  # Per-cell ancestry is bounded to keep saves manageable.
family_open = False
family_scroll = 0
lineage_stats = {}  # Root -> total births and sampled trait history.



def clamp(v, a, b):
    return max(a, min(b, v))


def delta(a, b, size):
    """Shortest signed displacement from a to b on a wrapping axis."""
    return (b - a + size / 2) % size - size / 2


class Cell:
    def __init__(self, x, y, generation=0, genes=None, energy=70):
        global next_id
        self.id = next_id
        next_id += 1
        self.x, self.y = x, y
        self.generation = generation
        self.energy = energy
        self.age = 0
        self.angle = random.random() * math.tau
        self.turn_timer = 0
        self.parent_link = None
        self.children_links = set()
        self.parent_id = None
        self.lineage = self.id
        self.ancestors = []  # Nearest parent first; immutable snapshots at birth.
        self.birth_tick = ticks
        if genes is None:
            self.genes = {
                'speed': random.uniform(.7, 2.0),
                'sense': random.uniform(24, 72),
                'eff': random.uniform(.85, 1.28),
                'adhesion': random.uniform(.12, .50),
                'share': random.uniform(.15, .65),
                'predation': random.uniform(0, .42),
                'armor': random.uniform(.05, .5),
                'size': random.uniform(.8, 1.2),
            }
        else:
            self.genes = genes

    def links(self):
        return ([self.parent_link] if self.parent_link is not None else []) + list(self.children_links)

    def mutate(self):
        g = self.genes
        return {
            'speed': clamp(g['speed'] + random.gauss(0, .10), .35, 3.0),
            'sense': clamp(g['sense'] + random.gauss(0, 4.0), 12, 130),
            'eff': clamp(g['eff'] + random.gauss(0, .035), .55, 1.65),
            'adhesion': clamp(g['adhesion'] + random.gauss(0, .045), 0, 1),
            'share': clamp(g['share'] + random.gauss(0, .045), 0, 1),
            'predation': clamp(g['predation'] + random.gauss(0, .055), 0, 1),
            'armor': clamp(g['armor'] + random.gauss(0, .035), 0, 1),
            'size': clamp(g['size'] + random.gauss(0, .035), .65, 1.55),
        }


def components():
    by_id = {c.id: c for c in cells}
    seen = set()
    groups = []
    for c in cells:
        if c.id in seen:
            continue
        stack = [c.id]
        group = []
        seen.add(c.id)
        while stack:
            cid = stack.pop()
            item = by_id.get(cid)
            if item is None:
                continue
            group.append(item)
            for other in item.links():
                if other in by_id and other not in seen:
                    seen.add(other)
                    stack.append(other)
        groups.append(group)
    return groups


def unlink(c, by_id):
    if c.parent_link is not None and c.parent_link in by_id:
        by_id[c.parent_link].children_links.discard(c.id)
    for child_id in c.children_links:
        if child_id in by_id:
            by_id[child_id].parent_link = None
    c.children_links.clear()
    c.parent_link = None


def seed_food(n):
    for _ in range(n):
        foods.append((random.uniform(8, W - 8), random.uniform(8, WORLD_H - 8)))


def reset():
    global cells, foods, next_id, births, deaths, ticks, predations, selected_id, family_scroll, lineage_stats
    selected_id = None
    family_scroll = 0
    lineage_stats = {}
    cells, foods = [], []
    next_id = births = deaths = ticks = predations = 0
    history.clear()
    seed_food(FOOD_MAX)
    for _ in range(START_POP):
        c = Cell(random.uniform(20, W-20), random.uniform(20, WORLD_H-20))
        cells.append(c)
        lineage_stats[c.lineage] = {'births': 1, 'samples': []}



def save_world():
    data = {
        'version': '3.0-stage3', 'ticks': ticks, 'births': births,
        'deaths': deaths, 'predations': predations, 'next_id': next_id,
        'foods': foods, 'history': list(history), 'lineage_stats': lineage_stats,
        'cells': [dict(id=c.id,x=c.x,y=c.y,generation=c.generation,
                       energy=c.energy,age=c.age,angle=c.angle,turn_timer=c.turn_timer,
                       genes=c.genes,parent_link=c.parent_link,
                       children_links=list(c.children_links),parent_id=c.parent_id,
                       lineage=c.lineage, ancestors=c.ancestors,
                       birth_tick=c.birth_tick) for c in cells],
    }
    SAVE_FILE.write_text(json.dumps(data),encoding='utf-8')
    print('Kaydedildi:', SAVE_FILE)


def load_world():
    global cells, foods, next_id, births, deaths, ticks, predations, selected_id, lineage_stats, family_scroll
    selected_id = None
    family_scroll = 0
    data = json.loads(SAVE_FILE.read_text(encoding='utf-8'))
    if data.get('version') not in ('3.0-stage1', '3.0-stage3'):
        raise ValueError('Uyumsuz kayit surumu')
    new_cells = []
    for item in data['cells']:
        c = Cell(item['x'],item['y'],item['generation'],item['genes'],item['energy'])
        c.id=item['id']; c.age=item['age']; c.angle=item['angle']
        c.turn_timer=item['turn_timer']; c.parent_link=item['parent_link']
        c.children_links=set(item['children_links'])
        c.parent_id=item['parent_id']; c.lineage=item['lineage']
        c.ancestors = item.get('ancestors', [])[:ANCESTOR_LIMIT]
        c.birth_tick = item.get('birth_tick', 0)
        new_cells.append(c)
    cells=new_cells; foods=[tuple(f) for f in data['foods']]
    next_id=data['next_id']; births=data['births']; deaths=data['deaths']
    ticks=data['ticks']; predations=data['predations']
    history.clear(); history.extend(tuple(h) for h in data['history'])
    lineage_stats = {int(k):v for k,v in data.get('lineage_stats', {}).items()}
    if not lineage_stats:
        for c in cells:
            lineage_stats.setdefault(c.lineage, {'births': 0, 'samples': []})
        print('Eski kayit: gecmis ata DNA verileri yok; yeni dogumlar izlenecek.')
    print('Yuklendi:', SAVE_FILE)


def step():
    global ticks, births, deaths, predations
    ticks += 1
    # Finite renewable resources: low food availability increases replenishment,
    # but food supply does not grow in proportion to population.
    food_deficit = FOOD_MAX - len(foods)
    if food_deficit > 0:
        food_spawn = min(food_deficit, 9 + food_deficit // 55, 18)
        seed_food(food_spawn)

    # Spatial buckets reduce food-search cost.
    bucket_size = 42
    nx = math.ceil(W / bucket_size)
    ny = math.ceil(WORLD_H / bucket_size)
    buckets = {}
    for food in foods:
        key = (int(food[0] // bucket_size) % nx, int(food[1] // bucket_size) % ny)
        buckets.setdefault(key, []).append(food)

    # Nearby prey candidates; each cell can be eaten at most once per tick.
    cell_buckets = {}
    for target in cells:
        key = (int(target.x // bucket_size) % nx, int(target.y // bucket_size) % ny)
        cell_buckets.setdefault(key, []).append(target)
    eaten_cells = set()
    eaten = set()
    newcomers = []
    expired = []
    by_id = {c.id: c for c in cells}
    for c in cells:
        if c.id in eaten_cells:
            continue
        c.age += 1
        g = c.genes
        reach = g['sense']
        bx, by = int(c.x // bucket_size), int(c.y // bucket_size)
        span = math.ceil(reach / bucket_size) + 1
        best = None
        best_d2 = reach * reach
        for ix in range(bx-span, bx+span+1):
            for iy in range(by-span, by+span+1):
                for f in buckets.get((ix % nx, iy % ny), ()):
                    if f in eaten:
                        continue
                    d2 = delta(c.x, f[0], W)**2 + delta(c.y, f[1], WORLD_H)**2
                    if d2 < best_d2:
                        best, best_d2 = f, d2
        prey = None
        prey_d2 = (min(reach, 65)) ** 2
        if g['predation'] > .20:
            for ix in range(bx-2, bx+3):
                for iy in range(by-2, by+3):
                    for target in cell_buckets.get((ix % nx, iy % ny), ()):
                        if target.id == c.id or target.id in eaten_cells:
                            continue
                        # Predators need enough size and attack capability.
                        if g['size'] * (1 + g['predation']) <= target.genes['size'] * (1 + .55*target.genes['armor']):
                            continue
                        d2 = delta(c.x,target.x,W)**2 + delta(c.y,target.y,WORLD_H)**2
                        if d2 < prey_d2:
                            prey, prey_d2 = target, d2
        # Dietary preference is continuous, not a fixed predator species.
        if prey is not None and (best is None or g['predation'] > .55):
            c.angle = math.atan2(delta(c.y,prey.y,WORLD_H), delta(c.x,prey.x,W))
        elif best is not None:
            c.angle = math.atan2(delta(c.y, best[1], WORLD_H), delta(c.x, best[0], W))
        else:
            c.turn_timer -= 1
            if c.turn_timer <= 0:
                c.angle += random.uniform(-1.1, 1.1)
                c.turn_timer = random.randint(10, 35)
        # Connected cells still act locally, with elastic links below.
        c.x = (c.x + math.cos(c.angle)*g['speed']) % W
        c.y = (c.y + math.sin(c.angle)*g['speed']) % WORLD_H
        c.energy -= (.34 + .060*g['speed']**2 + .0010*g['sense'] + .045*g['adhesion'] + .16*g['predation'] + .12*g['armor'] + .08*g['size']) / g['eff']
        if prey is not None and prey.id not in eaten_cells and prey_d2 < 85 and g['predation'] > .20:
            if delta(c.x,prey.x,W)**2 + delta(c.y,prey.y,WORLD_H)**2 < (5*(g['size']+prey.genes['size']))**2:
                eaten_cells.add(prey.id)
                c.energy = min(210, c.energy + 16 + min(65, max(0,prey.energy)*.45))
                predations += 1
        if best is not None and best_d2 < 85 and best not in eaten:
            eaten.add(best)
            c.energy = min(210, c.energy + FOOD_ENERGY)
        # Adhesion is inherited; linking is possible but never guaranteed.
        if c.energy > 165 and len(cells)+len(newcomers) < MAX_POP:
            c.energy *= .50
            child = Cell((c.x+random.uniform(-12,12)) % W,
                         (c.y+random.uniform(-12,12)) % WORLD_H,
                         c.generation+1, c.mutate(), c.energy)
            if random.random() < g['adhesion'] and len(c.children_links) < 3:
                # Limit each connected component to 10 cells for stability.
                linked = set()
                queue = [c.id]
                while queue and len(linked) <= 10:
                    item_id = queue.pop()
                    if item_id in linked:
                        continue
                    linked.add(item_id)
                    if item_id in by_id:
                        queue.extend(by_id[item_id].links())
                if len(linked) < 10:
                    child.parent_link = c.id
                    c.children_links.add(child.id)
            child.parent_id = c.id
            child.lineage = c.lineage
            child.birth_tick = ticks
            snapshot = {'id': c.id, 'parent_id': c.parent_id,
                        'generation': c.generation, 'birth_tick': c.birth_tick,
                        'genes': dict(c.genes)}
            child.ancestors = ([snapshot] + c.ancestors)[:ANCESTOR_LIMIT]
            stats = lineage_stats.setdefault(child.lineage, {'births': 0, 'samples': []})
            stats['births'] += 1
            newcomers.append(child)
            births += 1
        if c.energy <= 0 or c.age > 2400:
            expired.append(c)

    if eaten:
        foods[:] = [f for f in foods if f not in eaten]
    if eaten_cells:
        expired.extend(c for c in cells if c.id in eaten_cells and c not in expired)
    if expired:
        for c in expired:
            unlink(c, by_id)
        dead_ids = {c.id for c in expired}
        cells[:] = [c for c in cells if c.id not in dead_ids]
        deaths += len(expired)
    cells.extend(newcomers)

    # Elastic connections and energy sharing create possible trade-offs.
    by_id = {c.id: c for c in cells}
    for c in cells:
        for child_id in c.children_links:
            other = by_id.get(child_id)
            if other is None:
                continue
            dx, dy = delta(c.x, other.x, W), delta(c.y, other.y, WORLD_H)
            d = max(0.01, math.hypot(dx,dy))
            if d > 13:
                pull = min(2.5, (d-13)*.17)
                ux, uy = dx/d, dy/d
                c.x = (c.x+ux*pull*.5) % W
                c.y = (c.y+uy*pull*.5) % WORLD_H
                other.x = (other.x-ux*pull*.5) % W
                other.y = (other.y-uy*pull*.5) % WORLD_H
            transfer = (c.energy-other.energy)*.012*min(c.genes['share'],other.genes['share'])
            c.energy -= transfer
            other.energy += transfer
    if ticks % 500 == 0:
        # Sample living lineages rather than claiming to track every extinct cell.
        lineage_groups = {}
        for c in cells:
            lineage_groups.setdefault(c.lineage, []).append(c)
        for root, group in lineage_groups.items():
            stats = lineage_stats.setdefault(root, {'births': 0, 'samples': []})
            stats['samples'].append([ticks, len(group),
                round(sum(c.genes['predation'] for c in group)/len(group), 3),
                round(sum(c.genes['armor'] for c in group)/len(group), 3),
                round(sum(c.genes['adhesion'] for c in group)/len(group), 3)])
            stats['samples'] = stats['samples'][-120:]
    if ticks % 100 == 0:
        groups = components()
        history.append((len(cells), sum(len(g) for g in groups if len(g)>1)))


# EvoLife 2.5: camera and fullscreen controls. World physics stays unchanged.
fullscreen = False
camera_x, camera_y = W / 2, WORLD_H / 2
zoom = 1.0
dragging = False
VIEW_MARGIN = 160


def view_size():
    return screen.get_width(), max(150, screen.get_height() - VIEW_MARGIN)


def project(x, y, ox=0, oy=0):
    sw, vh = view_size()
    return (sw / 2 + (x + ox - camera_x) * zoom,
            vh / 2 + (y + oy - camera_y) * zoom)


def draw_graph(rect, values, color, label, cap=None):
    x, y, w, h = rect
    pygame.draw.rect(screen, (20, 39, 49), rect, border_radius=5)
    pygame.draw.rect(screen, (43, 66, 77), rect, 1, border_radius=5)
    if not values:
        return
    lo = max(0, int(min(values) * .92))
    hi = max(1, int(max(values) * 1.05) + 1)
    if hi - lo < 20:
        mid = (hi + lo) / 2
        lo = max(0, int(mid - 12))
        hi = int(mid + 12)
    left, top = x + 12, y + 31
    plot_w, plot_h = max(2, w - 25), max(2, h - 43)
    pygame.draw.line(screen, (49, 74, 83), (left, top + plot_h),
                     (left + plot_w, top + plot_h), 1)
    if len(values) >= 2:
        pts = [(int(left + i * plot_w / (len(values)-1)),
                int(top + plot_h - (v-lo)/(hi-lo) * plot_h))
               for i, v in enumerate(values)]
        pygame.draw.lines(screen, color, False, pts, 2)
    latest = values[-1]
    screen.blit(small.render(f'{label}  {latest}  |  aralik {lo}-{hi}', True, color), (x+10, y+7))
    if cap is not None:
        screen.blit(small.render(f'Teknik limit: {cap}', True, (155, 172, 184)),
                    (x+w-205, y+7))


def selected_cell():
    return next((c for c in cells if c.id == selected_id), None)


def pick_cell(pos):
    global selected_id
    sw, vh = view_size()
    if pos[1] >= vh or (inspector_open and pos[0] >= sw - PANEL_W):
        return
    # Shortest wrapped displacement handles all visible world copies.
    wx = camera_x + (pos[0] - sw/2)/zoom
    wy = camera_y + (pos[1] - vh/2)/zoom
    best = None
    best_d2 = (max(10, 12*zoom)/zoom)**2
    for c in cells:
        d2 = delta(wx, c.x, W)**2 + delta(wy, c.y, WORLD_H)**2
        if d2 < best_d2:
            best, best_d2 = c, d2
    selected_id = best.id if best else None
    global family_scroll
    family_scroll = 0


def draw_inspector(sw, vh):
    if not inspector_open:
        return
    x = sw - PANEL_W
    rect = pygame.Rect(x, 0, PANEL_W, vh)
    pygame.draw.rect(screen, (17, 34, 45), rect)
    pygame.draw.line(screen, (83, 111, 126), (x, 0), (x, vh), 2)
    c = selected_cell()
    rows = ['MIKROSKOP  [TAB: gizle]', '', 'Sol tik: Hucre sec', 'Sag tik surukle: Kamera', '']
    if c is None:
        rows += ['Secili hucre yok.', '', 'Bir hucreye tikla.', '', 'Avci: avlanma geni > 0.55', 'Aktif avci: gen > 0.20', '', 'Avci ve av ayrimi kesin tur', 'siniflamasi degildir.']
    else:
        connected = len(c.links())
        rows += [f'KIMLIK: {c.id}', f'SOY KOKU: {c.lineage}',
                 f'EBEVEYN: {c.parent_id if c.parent_id is not None else "-"}',
                 f'NESIL: {c.generation}', f'YAS: {c.age} / 2400',
                 f'ENERJI: {c.energy:.1f}', f'BAGLANTI: {connected}', '', '--- DNA / GENLER ---',
                 f'Hiz: {c.genes["speed"]:.3f}', f'Algi: {c.genes["sense"]:.2f}',
                 f'Verim: {c.genes["eff"]:.3f}', f'Yapiskanlik: {c.genes["adhesion"]:.3f}',
                 f'Paylasim: {c.genes["share"]:.3f}', f'Avlanma: {c.genes["predation"]:.3f}',
                 f'Zirh: {c.genes["armor"]:.3f}', f'Boyut: {c.genes["size"]:.3f}', '',
                 'F6: Soy agaci / gen gecmisi', '', 'Durum: ' + ('Guclu avci' if c.genes['predation']>.55 else 'Avlanabilir' if c.genes['predation']>.20 else 'Dusuk avcilik')]
    y = 13
    for i, row in enumerate(rows):
        color = (218, 188, 252) if i == 0 or row.startswith('---') else (208, 226, 231)
        screen.blit(small.render(row, True, color), (x+12, y))
        y += 23
        if y > vh - 22:
            break




def draw_family(sw, vh):
    """Genealogy is a real parent chain, not a fabricated species tree."""
    if not family_open:
        return
    x, y = max(12, (sw-750)//2), 22
    w, h = min(750, sw-24), max(180, vh-44)
    pygame.draw.rect(screen, (16, 34, 46), (x,y,w,h), border_radius=9)
    pygame.draw.rect(screen, (142, 112, 210), (x,y,w,h), 2, border_radius=9)
    def line(msg, yy, color=(209,224,231), xoff=16):
        if yy < y+46 or yy > y+h-23:
            return
        screen.blit(small.render(msg[:max(8,(w-xoff-12)//9)], True, color),(x+xoff,yy))
    screen.blit(font.render('SOY AGACI / DNA GECMISI    [F6: Kapat] [Yukari/Asagi: Kaydir]', True,
                            (217,181,252)),(x+16,y+13))
    c=selected_cell()
    if c is None:
        line('Once dunyadan bir hucre sec.', y+66)
        return
    live_count = sum(item.lineage == c.lineage for item in cells)
    stats = lineage_stats.get(c.lineage, {'births':0,'samples':[]})
    lines = [
        (f'SECILI #{c.id}  NESIL {c.generation}  SOY KOKU #{c.lineage}', (252,232,156)),
        (f'Bu soydan yasayan: {live_count}  |  Kayitli dogum: {stats.get("births",0)}', (193,222,230)),
        ('ATA ZINCIRI (dogum anindaki gercek DNA kayitlari)', (217,181,252)),
        ('ID       NESIL  AVCILIK   ZIRH    YAPISK.   HIZ', (152,183,194)),
    ]
    records = [{'id':c.id,'generation':c.generation,'genes':c.genes}] + c.ancestors
    for i, record in enumerate(records):
        g=record['genes']
        prefix='SEN' if i == 0 else f'-{i:02d}'
        lines.append((f'{prefix:3s} #{record["id"]:<7} {record["generation"]:<5} '
                      f'{g["predation"]:>7.3f}  {g["armor"]:>6.3f}  '
                      f'{g["adhesion"]:>7.3f}  {g["speed"]:>5.2f}',
                      (247,230,148) if i==0 else (204,221,229)))
    lines.extend([
        ('', (200,200,200)),
        ('SOYUN ZAMAN ICINDEKI ORTALAMA GENLERI (500 adimda bir)', (217,181,252)),
        ('ZAMAN    CANLI   AVCILIK   ZIRH   YAPISK.', (152,183,194)),
    ])
    for tick, n, pred, armor, adh in stats.get('samples', [])[-35:]:
        lines.append((f'{tick:<8} {n:<6}  {pred:.3f}    {armor:.3f}   {adh:.3f}', (204,221,229)))
    lines.extend([
        ('', (200,200,200)),
        (f'Gosterilen ata sayisi: {len(c.ancestors)} / en fazla {ANCESTOR_LIMIT}', (152,183,194)),
        ('Eski kayitlardan yuklenen hucrelerin onceki ata verisi olmayabilir.', (152,183,194)),
        ('Soy ici farklilasma = turlesme kaniti degildir.', (152,183,194)),
    ])
    visible=max(1,(h-76)//20)
    scroll=min(family_scroll,max(0,len(lines)-visible))
    for i, (msg, color) in enumerate(lines[scroll:scroll+visible]):
        line(msg, y+53+i*20, color)
    if len(lines)>visible:
        screen.blit(small.render(f'{scroll+1}-{min(scroll+visible,len(lines))}/{len(lines)}',True,
                                 (165,177,190)),(x+w-110,y+h-24))

def draw():
    sw, sh = screen.get_size()
    vh = view_size()[1]
    screen.fill((11, 20, 30))
    pygame.draw.rect(screen, BG, (0, 0, sw, vh))
    screen.set_clip(pygame.Rect(0, 0, sw, vh))
    # Tile only the visible copies of the wrapping world.
    half_w, half_h = sw / (2 * zoom), vh / (2 * zoom)
    x0 = math.floor((camera_x-half_w)/W) - 1
    x1 = math.ceil((camera_x+half_w)/W) + 1
    y0 = math.floor((camera_y-half_h)/WORLD_H) - 1
    y1 = math.ceil((camera_y+half_h)/WORLD_H) + 1
    offsets = [(ix*W, iy*WORLD_H) for ix in range(x0, x1+1)
               for iy in range(y0, y1+1)]
    for x, y in foods:
        for ox, oy in offsets:
            px, py = project(x, y, ox, oy)
            if -4 <= px <= sw+4 and -4 <= py <= vh+4:
                pygame.draw.circle(screen, (75, 162, 91), (round(px),round(py)), max(1,round(2*zoom)))
    by_id = {c.id:c for c in cells}
    for c in cells:
        for cid in c.children_links:
            o = by_id.get(cid)
            if o is None:
                continue
            ex = c.x + delta(c.x, o.x, W)
            ey = c.y + delta(c.y, o.y, WORLD_H)
            for ox, oy in offsets:
                p1, p2 = project(c.x, c.y, ox, oy), project(ex, ey, ox, oy)
                if (min(p1[0],p2[0]) <= sw and max(p1[0],p2[0]) >= 0 and
                        min(p1[1],p2[1]) <= vh and max(p1[1],p2[1]) >= 0):
                    pygame.draw.line(screen, (133, 110, 207), p1, p2, max(1,round(2*zoom)))
    for c in cells:
        t = (c.genes['speed']-.35)/2.65
        hunt = c.genes['predation']
        color = (int(62+170*t), int(204-80*t), int(230-125*t))
        if hunt > .55:
            color = (245, int(115+50*(1-hunt)), 85)
        r = max(2,round((CELL_RADIUS*c.genes['size'] + (1 if c.energy>90 else 0))*zoom))
        for ox, oy in offsets:
            px, py = project(c.x, c.y, ox, oy)
            if -r-3 <= px <= sw+r+3 and -r-3 <= py <= vh+r+3:
                pygame.draw.circle(screen, color, (round(px),round(py)), r)
                if c.parent_link is not None or c.children_links:
                    pygame.draw.circle(screen, (207, 168, 249), (round(px),round(py)), r+max(1,round(2*zoom)), max(1,round(zoom)))
    # Highlight selected cell in every visible wrapped copy.
    selected = selected_cell()
    if selected is not None:
        for ox, oy in offsets:
            px, py = project(selected.x, selected.y, ox, oy)
            if -20 <= px <= sw+20 and -20 <= py <= vh+20:
                pygame.draw.circle(screen, (255, 236, 98), (round(px), round(py)),
                                   max(7, round((CELL_RADIUS*selected.genes['size']+5)*zoom)), 2)
    screen.set_clip(None)
    draw_inspector(sw, vh)
    draw_family(sw, vh)
    pygame.draw.line(screen, (65, 85, 98), (0, vh), (sw, vh), 2)
    groups = components()
    colonies = [g for g in groups if len(g)>1]
    in_colonies = sum(len(g) for g in colonies)
    biggest = max((len(g) for g in groups), default=0)
    n = len(cells)
    gen = max((c.generation for c in cells), default=0)
    adhesion = sum(c.genes['adhesion'] for c in cells)/n if n else 0
    strong_hunters = sum(c.genes['predation'] > .55 for c in cells)
    potential_hunters = sum(c.genes['predation'] > .20 for c in cells)
    line1 = f'CANLI: {n}/{MAX_POP}   AVCI(>.55): {strong_hunters}   AVLANABILEN: {potential_hunters}   KOLONI: {len(colonies)}   NESIL: {gen}'
    line2 = f'DOGUM: {births}  OLUM: {deaths}  AV: {predations}  BESIN: {len(foods)}  BAGLI: {in_colonies}  EN BUYUK: {biggest}  ZAMAN: {ticks}  HIZ: {speed_factor}x  ZOOM: {zoom:.1f}x'
    screen.blit(font.render(line1, True, (235,241,245)), (14, vh+8))
    screen.blit(small.render(line2, True, (166,207,216)), (14, vh+33))
    graph_y = vh+57
    graph_h = max(45, sh-graph_y-7)
    gap = 12
    graph_w = max(120, (sw-42-gap)//2)
    pop = [p[0] for p in history] + [n]
    linked = [p[1] for p in history] + [in_colonies]
    draw_graph((14,graph_y,graph_w,graph_h),pop,(70,207,225),'Nufus',MAX_POP)
    draw_graph((26+graph_w,graph_y,graph_w,graph_h),linked,(190,139,245),'Kolonilerdeki hucreler')
    status = 'DURAKLATILDI' if paused else 'CALISIYOR'
    pygame.display.set_caption(f'EvoLife 3.0 - Asama 3 | {status} | Sol tik: Incele | F6: Soy agaci | TAB: Panel | F5: Kaydet | F9: Yukle')
    pygame.display.flip()


reset()
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_F11:
                fullscreen = not fullscreen
                if fullscreen:
                    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                else:
                    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
            elif event.key == pygame.K_SPACE:
                paused = not paused
            elif event.key == pygame.K_1:
                speed_factor = 1
            elif event.key == pygame.K_2:
                speed_factor = 4
            elif event.key == pygame.K_3:
                speed_factor = 12
            elif event.key == pygame.K_r:
                reset()
            elif event.key == pygame.K_F5:
                try: save_world()
                except Exception as exc: print('Kayit hatasi:',exc)
            elif event.key == pygame.K_F9:
                try: load_world()
                except Exception as exc: print('Yukleme hatasi:',exc)
            elif event.key == pygame.K_F6:
                family_open = not family_open
                family_scroll = 0
            elif event.key == pygame.K_UP and family_open:
                family_scroll = max(0, family_scroll-3)
            elif event.key == pygame.K_DOWN and family_open:
                family_scroll += 3
            elif event.key == pygame.K_TAB:
                inspector_open = not inspector_open
            elif event.key == pygame.K_HOME:
                camera_x, camera_y, zoom = W/2, WORLD_H/2, 1.0
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not family_open:
                pick_cell(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (2, 3):
            dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button in (2, 3):
            dragging = False
        elif event.type == pygame.MOUSEMOTION and dragging:
            dx, dy = event.rel
            camera_x = (camera_x - dx/zoom) % W
            camera_y = (camera_y - dy/zoom) % WORLD_H
        elif event.type == pygame.MOUSEWHEEL:
            if family_open:
                family_scroll = max(0, family_scroll-event.y*3)
            else:
                zoom = clamp(zoom * (1.18 ** event.y), .45, 5.0)
    keys = pygame.key.get_pressed()
    movement = 9/zoom
    camera_x = (camera_x + (keys[pygame.K_d] or keys[pygame.K_RIGHT])*movement - (keys[pygame.K_a] or keys[pygame.K_LEFT])*movement) % W
    camera_y = (camera_y + (keys[pygame.K_s] or keys[pygame.K_DOWN])*movement - (keys[pygame.K_w] or keys[pygame.K_UP])*movement) % WORLD_H
    if not paused:
        for _ in range(speed_factor):
            step()
    draw()
    clock.tick(60)
pygame.quit()
