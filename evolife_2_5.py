import math
import random
from collections import deque
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
        if genes is None:
            self.genes = {
                'speed': random.uniform(.7, 2.0),
                'sense': random.uniform(24, 72),
                'eff': random.uniform(.85, 1.28),
                'adhesion': random.uniform(.12, .50),
                'share': random.uniform(.15, .65),
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
    global cells, foods, next_id, births, deaths, ticks
    cells, foods = [], []
    next_id = births = deaths = ticks = 0
    history.clear()
    seed_food(FOOD_MAX)
    for _ in range(START_POP):
        cells.append(Cell(random.uniform(20, W-20), random.uniform(20, WORLD_H-20)))


def step():
    global ticks, births, deaths
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

    eaten = set()
    newcomers = []
    expired = []
    by_id = {c.id: c for c in cells}
    for c in cells:
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
        if best is not None:
            c.angle = math.atan2(delta(c.y, best[1], WORLD_H), delta(c.x, best[0], W))
        else:
            c.turn_timer -= 1
            if c.turn_timer <= 0:
                c.angle += random.uniform(-1.1, 1.1)
                c.turn_timer = random.randint(10, 35)
        # Connected cells still act locally, with elastic links below.
        c.x = (c.x + math.cos(c.angle)*g['speed']) % W
        c.y = (c.y + math.sin(c.angle)*g['speed']) % WORLD_H
        c.energy -= (.34 + .060*g['speed']**2 + .0010*g['sense'] + .045*g['adhesion']) / g['eff']
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
            newcomers.append(child)
            births += 1
        if c.energy <= 0 or c.age > 2400:
            expired.append(c)

    if eaten:
        foods[:] = [f for f in foods if f not in eaten]
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
        color = (int(62+170*t), int(204-80*t), int(230-125*t))
        r = max(2,round((CELL_RADIUS + (1 if c.energy>90 else 0))*zoom))
        for ox, oy in offsets:
            px, py = project(c.x, c.y, ox, oy)
            if -r-3 <= px <= sw+r+3 and -r-3 <= py <= vh+r+3:
                pygame.draw.circle(screen, color, (round(px),round(py)), r)
                if c.parent_link is not None or c.children_links:
                    pygame.draw.circle(screen, (207, 168, 249), (round(px),round(py)), r+max(1,round(2*zoom)), max(1,round(zoom)))
    screen.set_clip(None)
    pygame.draw.line(screen, (65, 85, 98), (0, vh), (sw, vh), 2)
    groups = components()
    colonies = [g for g in groups if len(g)>1]
    in_colonies = sum(len(g) for g in colonies)
    biggest = max((len(g) for g in groups), default=0)
    n = len(cells)
    gen = max((c.generation for c in cells), default=0)
    adhesion = sum(c.genes['adhesion'] for c in cells)/n if n else 0
    line1 = f'CANLI: {n}/{MAX_POP}   KOLONI: {len(colonies)}   BAGLI: {in_colonies}   EN BUYUK: {biggest}   NESIL: {gen}'
    line2 = f'DOGUM: {births}  OLUM: {deaths}  BESIN: {len(foods)}  YAPISKANLIK: {adhesion:.2f}  ZAMAN: {ticks}  HIZ: {speed_factor}x  ZOOM: {zoom:.1f}x'
    screen.blit(font.render(line1, True, (235,241,245)), (14, vh+8))
    screen.blit(small.render(line2, True, (166,207,216)), (14, vh+33))
    graph_y = vh+57
    graph_h = max(45, sh-graph_y-7)
    gap = 12
    graph_w = (sw-42-gap)//2
    pop = [p[0] for p in history] + [n]
    linked = [p[1] for p in history] + [in_colonies]
    draw_graph((14,graph_y,graph_w,graph_h),pop,(70,207,225),'Nufus',MAX_POP)
    draw_graph((26+graph_w,graph_y,graph_w,graph_h),linked,(190,139,245),'Kolonilerdeki hucreler')
    status = 'DURAKLATILDI' if paused else 'CALISIYOR'
    pygame.display.set_caption(f'EvoLife 2.5 | {status} | F11: Tam ekran | WASD: Kamera | Tekerlek: Zoom | SPACE: Duraklat')
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
            elif event.key == pygame.K_HOME:
                camera_x, camera_y, zoom = W/2, WORLD_H/2, 1.0
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (2, 3):
            dragging = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button in (2, 3):
            dragging = False
        elif event.type == pygame.MOUSEMOTION and dragging:
            dx, dy = event.rel
            camera_x = (camera_x - dx/zoom) % W
            camera_y = (camera_y - dy/zoom) % WORLD_H
        elif event.type == pygame.MOUSEWHEEL:
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
