import math
import random
from collections import deque
import pygame

pygame.init()
W, H, WORLD_H = 1120, 780, 650
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
font = pygame.font.SysFont('consolas', 17)
small = pygame.font.SysFont('consolas', 14)
BG = (13, 28, 38)
MAX_POP = 900
START_POP = 90
FOOD_MAX = 380
FOOD_ENERGY = 28
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
    # Resource supply is finite; population is not forced to remain at a fixed number.
    if len(foods) < FOOD_MAX:
        seed_food(min(4, FOOD_MAX - len(foods)))

    # Spatial buckets reduce food-search cost.
    bucket_size = 42
    buckets = {}
    for food in foods:
        key = (int(food[0] // bucket_size), int(food[1] // bucket_size))
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
                for f in buckets.get((ix, iy), ()):
                    if f in eaten:
                        continue
                    d2 = (f[0]-c.x)**2 + (f[1]-c.y)**2
                    if d2 < best_d2:
                        best, best_d2 = f, d2
        if best is not None:
            c.angle = math.atan2(best[1]-c.y, best[0]-c.x)
        else:
            c.turn_timer -= 1
            if c.turn_timer <= 0:
                c.angle += random.uniform(-1.1, 1.1)
                c.turn_timer = random.randint(10, 35)
        # Connected cells still act locally, with elastic links below.
        c.x = clamp(c.x + math.cos(c.angle)*g['speed'], 7, W-7)
        c.y = clamp(c.y + math.sin(c.angle)*g['speed'], 7, WORLD_H-7)
        c.energy -= (.050 + .018*g['speed']**2 + .0004*g['sense'] + .014*g['adhesion']) / g['eff']
        if best is not None and best_d2 < 85 and best not in eaten:
            eaten.add(best)
            c.energy += FOOD_ENERGY
        # Adhesion is inherited; linking is possible but never guaranteed.
        if c.energy > 128 and len(cells)+len(newcomers) < MAX_POP:
            c.energy *= .50
            child = Cell(clamp(c.x+random.uniform(-12,12), 8, W-8),
                         clamp(c.y+random.uniform(-12,12), 8, WORLD_H-8),
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
        if c.energy <= 0 or c.age > 6500:
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
            dx, dy = other.x-c.x, other.y-c.y
            d = max(0.01, math.hypot(dx,dy))
            if d > 13:
                pull = min(2.5, (d-13)*.17)
                ux, uy = dx/d, dy/d
                c.x = clamp(c.x+ux*pull*.5, 7, W-7)
                c.y = clamp(c.y+uy*pull*.5, 7, WORLD_H-7)
                other.x = clamp(other.x-ux*pull*.5, 7, W-7)
                other.y = clamp(other.y-uy*pull*.5, 7, WORLD_H-7)
            transfer = (c.energy-other.energy)*.012*min(c.genes['share'],other.genes['share'])
            c.energy -= transfer
            other.energy += transfer
    if ticks % 100 == 0:
        groups = components()
        history.append((len(cells), sum(len(g) for g in groups if len(g)>1)))


def draw_graph(rect, values, color, upper):
    x, y, w, h = rect
    pygame.draw.rect(screen, (20, 39, 49), rect, border_radius=4)
    if len(values) < 2:
        return
    pts = [(x+i*(w-1)/(len(values)-1), y+h-4-(min(v,upper)/upper)*(h-8))
           for i,v in enumerate(values)]
    pygame.draw.lines(screen, color, False, pts, 2)


def draw():
    screen.fill((11, 20, 30))
    pygame.draw.rect(screen, BG, (0, 0, W, WORLD_H))
    for x,y in foods:
        pygame.draw.circle(screen, (75, 162, 91), (int(x),int(y)), 2)
    by_id = {c.id:c for c in cells}
    for c in cells:
        for cid in c.children_links:
            if cid in by_id:
                o = by_id[cid]
                pygame.draw.line(screen, (133, 110, 207), (int(c.x),int(c.y)), (int(o.x),int(o.y)), 2)
    for c in cells:
        g = c.genes
        t = (g['speed']-.35)/2.65
        color = (int(62+170*t), int(204-80*t), int(230-125*t))
        r = CELL_RADIUS + (1 if c.energy>90 else 0)
        pygame.draw.circle(screen, color, (int(c.x),int(c.y)), r)
        if c.parent_link is not None or c.children_links:
            pygame.draw.circle(screen, (207, 168, 249), (int(c.x),int(c.y)), r+2, 1)
    pygame.draw.line(screen, (65, 85, 98), (0,WORLD_H), (W,WORLD_H), 2)
    groups = components()
    colonies = [g for g in groups if len(g)>1]
    in_colonies = sum(map(len, colonies))
    biggest = max(map(len,groups), default=0)
    n = len(cells)
    gen = max((c.generation for c in cells), default=0)
    adhesion = sum(c.genes['adhesion'] for c in cells)/n if n else 0
    line1 = f'CANLI: {n}   KOLONI: {len(colonies)}   BAGLI HUCRE: {in_colonies}   EN BUYUK: {biggest}   NESIL: {gen}'
    line2 = f'DOGUM: {births}   OLUM: {deaths}   BESIN: {len(foods)}   ORT. YAPISKANLIK: {adhesion:.2f}   ZAMAN: {ticks}   HIZ: {speed_factor}x'
    screen.blit(font.render(line1, True, (235,241,245)), (14, WORLD_H+8))
    screen.blit(small.render(line2, True, (166,207,216)), (14, WORLD_H+36))
    draw_graph((14,WORLD_H+63, 525, 58), [p[0] for p in history], (70,207,225), MAX_POP)
    draw_graph((555,WORLD_H+63, 550, 58), [p[1] for p in history], (190,139,245), MAX_POP)
    screen.blit(small.render('Nufus (mavi)', True, (175,220,230)), (22,WORLD_H+66))
    screen.blit(small.render('Kolonilerdeki hucreler (mor)', True, (210,182,244)), (565,WORLD_H+66))
    status = 'DURAKLATILDI' if paused else 'CALISIYOR'
    pygame.display.set_caption(f'EvoLife 2.0 | {status} | BOSLUK: Duraklat | 1/2/3: Hiz | R: Yeniden | ESC: Cik')
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
    if not paused:
        for _ in range(speed_factor):
            step()
    draw()
    clock.tick(60)
pygame.quit()
