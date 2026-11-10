import pygame
import random
import math

pygame.init()
WIDTH, HEIGHT = 1100, 720
WORLD_H = 640
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption('EvoLife - Yapay Yasam Laboratuvari')
clock = pygame.time.Clock()
font = pygame.font.SysFont('consolas', 19)
small = pygame.font.SysFont('consolas', 15)

FOOD_TARGET = 440
MAX_POP = 650
START_POP = 75
FOOD_ENERGY = 24

foods = []
cells = []
next_id = 0
births = 0
deaths = 0
ticks = 0
paused = False
speed_multiplier = 1


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class Cell:
    def __init__(self, x, y, speed=None, sense=None, efficiency=None, generation=0, energy=65):
        global next_id
        self.id = next_id
        next_id += 1
        self.x, self.y = x, y
        self.speed = speed if speed is not None else random.uniform(0.8, 2.1)
        self.sense = sense if sense is not None else random.uniform(25, 85)
        self.efficiency = efficiency if efficiency is not None else random.uniform(0.75, 1.3)
        self.generation = generation
        self.energy = energy
        self.age = 0
        self.angle = random.uniform(0, 2 * math.pi)
        self.wander_timer = 0

    def update(self):
        global births, deaths
        self.age += 1
        nearest = None
        best_d2 = self.sense ** 2
        for food in foods:
            dx = food[0] - self.x
            dy = food[1] - self.y
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                nearest = food

        if nearest is not None:
            dx = nearest[0] - self.x
            dy = nearest[1] - self.y
            self.angle = math.atan2(dy, dx)
        else:
            self.wander_timer -= 1
            if self.wander_timer <= 0:
                self.angle += random.uniform(-1.1, 1.1)
                self.wander_timer = random.randint(12, 35)

        self.x = clamp(self.x + math.cos(self.angle) * self.speed, 5, WIDTH - 5)
        self.y = clamp(self.y + math.sin(self.angle) * self.speed, 5, WORLD_H - 5)
        # Tradeoffs: faster motion and longer sensing consume more energy.
        self.energy -= (0.035 + 0.018 * self.speed ** 2 + 0.00035 * self.sense) / self.efficiency

        if nearest is not None and best_d2 < 45:
            try:
                foods.remove(nearest)
                self.energy += FOOD_ENERGY
            except ValueError:
                pass

        if self.energy > 115 and len(cells) < MAX_POP:
            self.energy *= 0.5
            child = Cell(
                clamp(self.x + random.uniform(-8, 8), 5, WIDTH - 5),
                clamp(self.y + random.uniform(-8, 8), 5, WORLD_H - 5),
                speed=clamp(self.speed + random.gauss(0, 0.12), 0.4, 3.5),
                sense=clamp(self.sense + random.gauss(0, 5), 12, 150),
                efficiency=clamp(self.efficiency + random.gauss(0, 0.045), 0.45, 1.8),
                generation=self.generation + 1,
                energy=self.energy,
            )
            cells.append(child)
            births += 1

        if self.energy <= 0 or self.age > 5500:
            deaths += 1
            return False
        return True

    def draw(self):
        t = (self.speed - 0.4) / 3.1
        color = (int(65 + 185 * t), int(215 - 115 * t), int(235 - 150 * t))
        r = 4 + min(3, int(self.energy / 48))
        pygame.draw.circle(screen, color, (int(self.x), int(self.y)), r)
        pygame.draw.circle(screen, (225, 240, 250), (int(self.x - 1), int(self.y - 1)), 1)


def seed_food(n):
    for _ in range(n):
        foods.append((random.randint(6, WIDTH - 6), random.randint(6, WORLD_H - 6)))


def reset():
    global cells, foods, next_id, births, deaths, ticks
    cells, foods = [], []
    next_id = births = deaths = ticks = 0
    seed_food(FOOD_TARGET)
    for _ in range(START_POP):
        cells.append(Cell(random.randint(10, WIDTH - 10), random.randint(10, WORLD_H - 10)))


def step():
    global ticks, deaths
    ticks += 1
    # Steady environmental replenishment; no user intervention required.
    if len(foods) < FOOD_TARGET:
        seed_food(min(5, FOOD_TARGET - len(foods)))
    for cell in cells[:]:
        if cell not in cells:
            continue
        if not cell.update():
            cells.remove(cell)
    # A population can genuinely go extinct. R resets the experiment.


def draw():
    screen.fill((11, 19, 29))
    pygame.draw.rect(screen, (16, 31, 42), (0, 0, WIDTH, WORLD_H))
    for x, y in foods:
        pygame.draw.circle(screen, (83, 171, 95), (int(x), int(y)), 2)
    for cell in cells:
        cell.draw()
    pygame.draw.line(screen, (54, 73, 87), (0, WORLD_H), (WIDTH, WORLD_H), 2)
    pop = len(cells)
    mean_speed = sum(c.speed for c in cells) / pop if pop else 0
    mean_sense = sum(c.sense for c in cells) / pop if pop else 0
    max_gen = max((c.generation for c in cells), default=0)
    text1 = f'CANLI: {pop}   BESIN: {len(foods)}   EN YUKSEK NESIL: {max_gen}   DOGUM: {births}   OLUM: {deaths}'
    text2 = f'ORT. HIZ: {mean_speed:.2f}   ORT. ALGI: {mean_sense:.1f}   ZAMAN: {ticks}   HIZLANDIRMA: {speed_multiplier}x'
    screen.blit(font.render(text1, True, (230, 237, 245)), (18, 651))
    screen.blit(small.render(text2, True, (169, 204, 215)), (18, 679))
    status = 'DURAKLATILDI' if paused else 'CALISIYOR'
    pygame.display.set_caption(f'EvoLife | {status} | Bosluk: Duraklat | 1/2/3: Hiz | R: Sifirla | ESC: Cik')
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
                speed_multiplier = 1
            elif event.key == pygame.K_2:
                speed_multiplier = 4
            elif event.key == pygame.K_3:
                speed_multiplier = 12
            elif event.key == pygame.K_r:
                reset()
    if not paused:
        for _ in range(speed_multiplier):
            step()
    draw()
    clock.tick(60)
pygame.quit()
