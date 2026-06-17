"""
╔══════════════════════════════════════════════════════════════╗
║          DEAD ZONE — 2D Zombie Survival                      ║
║  pip install pygame  →  python zombie_survival.py            ║
║  WASD/Arrows = Move | Mouse = Aim | LClick = Shoot           ║
║  R = Reload  |  ESC = Pause/Quit                             ║
╚══════════════════════════════════════════════════════════════╝
"""
 
import pygame
import math
import random
import sys
import time
from collections import deque
 
pygame.init()
try:
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    AUDIO = True
except:
    AUDIO = False
 
# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
W, H       = 1024, 720
FPS        = 60
TAU        = math.pi * 2
WORLD_W    = 2400
WORLD_H    = 2400
 
# Colours
C_BG       = (10, 12, 8)
C_GRID     = (18, 22, 14)
C_PLAYER   = (80, 200, 120)
C_BULLET   = (255, 220, 80)
C_BLOOD    = (120, 15, 15)
C_HUD_BG   = (0, 0, 0)
C_WHITE    = (255, 255, 255)
C_RED      = (220, 40, 40)
C_GREEN    = (60, 200, 80)
C_YELLOW   = (230, 200, 40)
C_ORANGE   = (230, 110, 20)
C_DARK     = (5, 5, 5)
 
# Zombie type configs  {type: (colour, hp, speed, size, score_val, label)}
ZOMBIE_CFG = {
    "normal": ((50, 160, 50),  60,  1.2, 16, 10, ""),
    "fast":   ((160, 60, 160), 30,  2.8, 12, 20, "F"),
    "tank":   ((180, 80, 20),  220, 0.6, 24, 40, "T"),
}
 
# ─────────────────────────────────────────────────────────────────────────────
#  AUDIO  (procedurally generated)
# ─────────────────────────────────────────────────────────────────────────────
def _gen_sound(freq, ms, shape="sine", vol=0.5):
    sr = 44100
    n  = int(sr * ms / 1000)
    buf = []
    for i in range(n):
        t   = i / sr
        env = min(1.0, min(i, n-i) / (sr * 0.008))
        if   shape == "sine":   v = math.sin(TAU * freq * t)
        elif shape == "square": v = 1.0 if math.sin(TAU * freq * t) > 0 else -1.0
        elif shape == "noise":  v = random.uniform(-1, 1)
        elif shape == "decay":  v = math.sin(TAU * freq * t) * math.exp(-t * 18)
        else: v = 0
        s = int(v * env * vol * 32767)
        buf.append(s)
    raw = bytes(b for s in buf for b in [s & 0xFF, (s >> 8) & 0xFF, s & 0xFF, (s >> 8) & 0xFF])
    return pygame.mixer.Sound(buffer=raw)
 
if AUDIO:
    try:
        SND_SHOOT  = _gen_sound(880,  60,  "square", 0.35)
        SND_HIT    = _gen_sound(220,  80,  "decay",  0.45)
        SND_DEATH  = _gen_sound(110,  180, "decay",  0.50)
        SND_RELOAD = _gen_sound(440,  120, "sine",   0.30)
        SND_EMPTY  = _gen_sound(160,  60,  "square", 0.25)
        SND_HURT   = _gen_sound(150,  200, "noise",  0.40)
    except:
        AUDIO = False
 
def play(snd):
    if AUDIO:
        try: snd.play()
        except: pass
 
# ─────────────────────────────────────────────────────────────────────────────
#  UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])
 
def norm(dx, dy):
    d = math.hypot(dx, dy)
    return (dx/d, dy/d) if d else (0, 0)
 
def clamp(v, lo, hi):
    return max(lo, min(hi, v))
 
def lerp(a, b, t):
    return a + (b-a)*t
 
def world_to_screen(wx, wy, cam_x, cam_y):
    return (int(wx - cam_x + W//2), int(wy - cam_y + H//2))
 
def screen_to_world(sx, sy, cam_x, cam_y):
    return (sx + cam_x - W//2, sy + cam_y - H//2)
 
# ─────────────────────────────────────────────────────────────────────────────
#  BLOOD PARTICLE
# ─────────────────────────────────────────────────────────────────────────────
class BloodParticle:
    def __init__(self, x, y):
        self.x, self.y = x, y
        angle = random.uniform(0, TAU)
        speed = random.uniform(1, 5)
        self.vx = math.cos(angle)*speed
        self.vy = math.sin(angle)*speed
        self.life = random.uniform(0.3, 0.7)
        self.max_life = self.life
        self.r = random.randint(2, 5)
        self.col = (random.randint(100,160), random.randint(5,25), random.randint(5,20))
 
    def update(self, dt):
        self.x  += self.vx
        self.y  += self.vy
        self.vy += 0.12
        self.vx *= 0.92
        self.life -= dt
 
    def draw(self, surf, cam_x, cam_y):
        sx, sy = world_to_screen(self.x, self.y, cam_x, cam_y)
        a = max(0, int(255 * self.life / self.max_life))
        s = pygame.Surface((self.r*2, self.r*2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.col, a), (self.r, self.r), self.r)
        surf.blit(s, (sx-self.r, sy-self.r))
 
    @property
    def alive(self): return self.life > 0
 
# ─────────────────────────────────────────────────────────────────────────────
#  BULLET
# ─────────────────────────────────────────────────────────────────────────────
class Bullet:
    SPEED = 620
    RANGE = 700
 
    def __init__(self, x, y, angle):
        self.x, self.y = x, y
        self.vx = math.cos(angle) * self.SPEED
        self.vy = math.sin(angle) * self.SPEED
        self.dist_travelled = 0
        self.alive = True
        self.r = 4
 
    def update(self, dt):
        dx = self.vx * dt
        dy = self.vy * dt
        self.x += dx
        self.y += dy
        self.dist_travelled += math.hypot(dx, dy)
        if self.dist_travelled >= self.RANGE:
            self.alive = False
        if not (0 <= self.x <= WORLD_W and 0 <= self.y <= WORLD_H):
            self.alive = False
 
    def draw(self, surf, cam_x, cam_y):
        sx, sy = world_to_screen(self.x, self.y, cam_x, cam_y)
        tail_x = sx - int(self.vx * 0.025)
        tail_y = sy - int(self.vy * 0.025)
        pygame.draw.line(surf, C_BULLET, (tail_x, tail_y), (sx, sy), 3)
        pygame.draw.circle(surf, C_WHITE, (sx, sy), 3)
 
    def rect(self):
        return pygame.Rect(self.x - self.r, self.y - self.r, self.r*2, self.r*2)
 
# ─────────────────────────────────────────────────────────────────────────────
#  ZOMBIE
# ─────────────────────────────────────────────────────────────────────────────
class Zombie:
    def __init__(self, x, y, ztype="normal"):
        self.x, self.y = float(x), float(y)
        cfg = ZOMBIE_CFG[ztype]
        self.col, self.max_hp, self.base_speed, self.r, self.score_val, self.label = cfg
        self.hp       = self.max_hp
        self.speed    = self.base_speed
        self.ztype    = ztype
        self.alive    = True
        self.hurt_t   = 0        # flash timer
        self.stagger  = 0        # brief push-back timer
        self.stagger_dx = 0
        self.stagger_dy = 0
        self.groan_t  = random.uniform(0, 4)
 
    def update(self, dt, player_x, player_y, speed_mult=1.0):
        self.hurt_t  = max(0, self.hurt_t  - dt)
        self.groan_t = max(0, self.groan_t - dt)
        if self.stagger > 0:
            self.stagger -= dt
            self.x += self.stagger_dx * dt * 80
            self.y += self.stagger_dy * dt * 80
            return
        dx, dy = player_x - self.x, player_y - self.y
        d = math.hypot(dx, dy)
        if d > 0:
            nx, ny = dx/d, dy/d
            spd = self.speed * speed_mult
            self.x += nx * spd * dt * 60
            self.y += ny * spd * dt * 60
        self.x = clamp(self.x, 0, WORLD_W)
        self.y = clamp(self.y, 0, WORLD_H)
 
    def take_damage(self, dmg, bvx=0, bvy=0):
        self.hp -= dmg
        self.hurt_t = 0.12
        if self.hp <= 0:
            self.alive = False
            return True
        # stagger
        nx, ny = norm(bvx, bvy)
        self.stagger    = 0.08
        self.stagger_dx = nx
        self.stagger_dy = ny
        return False
 
    def draw(self, surf, cam_x, cam_y, night_factor=0):
        sx, sy = world_to_screen(self.x, self.y, cam_x, cam_y)
        # Cull off-screen
        if not (-60 < sx < W+60 and -60 < sy < H+60):
            return
        col = (220, 60, 60) if self.hurt_t > 0 else self.col
        # Shadow
        shadow_s = pygame.Surface((self.r*2+4, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_s, (0,0,0,60), (0,0,self.r*2+4,8))
        surf.blit(shadow_s, (sx-self.r-2, sy+self.r-3))
        # Body
        pygame.draw.circle(surf, col, (sx, sy), self.r)
        pygame.draw.circle(surf, (0,0,0), (sx, sy), self.r, 1)
        # Eyes
        pygame.draw.circle(surf, (200,30,30), (sx-4, sy-3), 3)
        pygame.draw.circle(surf, (200,30,30), (sx+4, sy-3), 3)
        # Type label
        if self.label:
            fs = pygame.font.SysFont("consolas", 10, bold=True)
            t  = fs.render(self.label, True, C_WHITE)
            surf.blit(t, (sx - t.get_width()//2, sy - t.get_height()//2))
        # HP bar
        if self.hp < self.max_hp:
            bw = self.r*2
            pct = self.hp / self.max_hp
            pygame.draw.rect(surf, C_RED,   (sx-self.r, sy-self.r-8, bw, 4))
            pygame.draw.rect(surf, C_GREEN, (sx-self.r, sy-self.r-8, int(bw*pct), 4))
 
    def rect(self):
        return pygame.Rect(self.x-self.r, self.y-self.r, self.r*2, self.r*2)
 
# ─────────────────────────────────────────────────────────────────────────────
#  ADAPTIVE AI MANAGER
# ─────────────────────────────────────────────────────────────────────────────
class AdaptiveAI:
    """
    Tracks player behaviour and adjusts zombie spawning accordingly.
 
    Behaviours detected:
      1. CAMPING   – player hasn't moved much in last N seconds
                     → spawn zombies in a tight ring around player
      2. RUNNING   – player moves a lot continuously
                     → zombies get a speed multiplier
      3. PATH LOOP – player repeatedly passes the same waypoints
                     → spawn ambush zombies ahead of predicted path
    """
    GRID_CELL  = 160          # spatial hash cell size
    HIST_LEN   = 300          # frames of position history (~5 s at 60fps)
    CAMP_DIST  = 80           # pixels: "not moving" threshold
    CAMP_SECS  = 4.0          # seconds before camping triggers
 
    def __init__(self):
        self.pos_history   = deque(maxlen=self.HIST_LEN)
        self.cell_visits   = {}    # cell → visit count
        self.camp_timer    = 0.0
        self.is_camping    = False
        self.is_running    = False
        self.run_timer     = 0.0
        self.speed_mult    = 1.0
        self.ambush_cells  = []    # predicted ambush world positions
        self.ambush_timer  = 0.0
        self.state_label   = ""    # for HUD debug
        self.frame         = 0
 
    def update(self, dt, player_x, player_y):
        self.frame += 1
        pos = (player_x, player_y)
        self.pos_history.append(pos)
 
        # ── 1. Camping detection ──────────────────────────────────────────
        if len(self.pos_history) >= 60:
            recent = list(self.pos_history)[-60:]
            spread = max(dist(recent[0], p) for p in recent)
            if spread < self.CAMP_DIST:
                self.camp_timer  += dt
                self.is_running   = False
                self.run_timer    = 0
            else:
                self.camp_timer   = max(0, self.camp_timer - dt * 0.5)
 
        self.is_camping = self.camp_timer >= self.CAMP_SECS
 
        # ── 2. Running detection ──────────────────────────────────────────
        if len(self.pos_history) >= 10:
            recent10 = list(self.pos_history)[-10:]
            moved = sum(dist(recent10[i], recent10[i+1]) for i in range(len(recent10)-1))
            if moved > 200:
                self.run_timer += dt
            else:
                self.run_timer = max(0, self.run_timer - dt)
 
        self.is_running = (self.run_timer > 3.0) and not self.is_camping
        if self.is_running:
            self.speed_mult = clamp(1.0 + (self.run_timer - 3.0) * 0.08, 1.0, 2.0)
        elif self.is_camping:
            self.speed_mult = 1.0
        else:
            self.speed_mult = max(1.0, self.speed_mult - dt * 0.05)
 
        # ── 3. Path loop / ambush detection ──────────────────────────────
        cell = (int(player_x // self.GRID_CELL), int(player_y // self.GRID_CELL))
        self.cell_visits[cell] = self.cell_visits.get(cell, 0) + 1
 
        self.ambush_timer -= dt
        if self.ambush_timer <= 0 and len(self.pos_history) >= 120:
            self.ambush_timer = 6.0
            self.ambush_cells = self._predict_ambush(player_x, player_y)
 
        # State label for HUD
        if self.is_camping:
            self.state_label = "AI: SURROUNDING"
        elif self.is_running:
            self.state_label = f"AI: SPEED ×{self.speed_mult:.1f}"
        elif self.ambush_cells:
            self.state_label = "AI: AMBUSH SET"
        else:
            self.state_label = ""
 
    def _predict_ambush(self, px, py):
        """Find frequently visited cells ahead of player's movement vector."""
        hist = list(self.pos_history)
        if len(hist) < 30:
            return []
        # Recent movement direction
        dx = hist[-1][0] - hist[-30][0]
        dy = hist[-1][1] - hist[-30][1]
        d  = math.hypot(dx, dy)
        if d < 10:
            return []
        nx, ny = dx/d, dy/d
        # Top visited cells
        top_cells = sorted(self.cell_visits, key=lambda c: self.cell_visits[c], reverse=True)[:8]
        # Filter cells roughly ahead of player
        ahead = []
        for (cx, cy) in top_cells:
            wcx = cx * self.GRID_CELL + self.GRID_CELL//2
            wcy = cy * self.GRID_CELL + self.GRID_CELL//2
            dot = (wcx-px)*nx + (wcy-py)*ny
            if dot > 200:
                ahead.append((wcx, wcy))
        return ahead[:3]
 
    def get_spawn_position(self, player_x, player_y):
        """Return a world (x,y) spawn position based on current AI state."""
        margin = 80
        if self.is_camping:
            # Tight ring close to player
            angle = random.uniform(0, TAU)
            radius = random.uniform(200, 340)
            return (player_x + math.cos(angle)*radius,
                    player_y + math.sin(angle)*radius)
        if self.ambush_cells and random.random() < 0.4:
            # Spawn near a predicted ambush cell
            cell = random.choice(self.ambush_cells)
            ox = random.uniform(-80, 80)
            oy = random.uniform(-80, 80)
            x  = clamp(cell[0]+ox, margin, WORLD_W-margin)
            y  = clamp(cell[1]+oy, margin, WORLD_H-margin)
            return (x, y)
        # Default: random edge of visible screen + some distance
        angle  = random.uniform(0, TAU)
        radius = random.uniform(420, 620)
        x = clamp(player_x + math.cos(angle)*radius, margin, WORLD_W-margin)
        y = clamp(player_y + math.sin(angle)*radius, margin, WORLD_H-margin)
        return (x, y)
 
# ─────────────────────────────────────────────────────────────────────────────
#  PLAYER
# ─────────────────────────────────────────────────────────────────────────────
class Player:
    SPEED        = 3.2
    MAX_HP       = 100
    MAX_AMMO     = 12
    RELOAD_TIME  = 1.8
    SHOOT_DELAY  = 0.18
    DAMAGE       = 35
    HURT_IFRAMES = 0.6    # invincibility seconds after being hit
 
    def __init__(self):
        self.x, self.y  = WORLD_W//2, WORLD_H//2
        self.hp          = self.MAX_HP
        self.ammo        = self.MAX_AMMO
        self.reloading   = False
        self.reload_t    = 0.0
        self.shoot_t     = 0.0
        self.hurt_t      = 0.0   # iframe timer
        self.angle       = 0.0
        self.alive       = True
        self.r           = 14
        self.flash       = 0.0   # hurt flash
        self.kills       = 0
        self.move_dist   = 0.0
 
    def update(self, dt, keys, mouse_world):
        if not self.alive:
            return
        # Movement
        dx, dy = 0, 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:    dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  dy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dx += 1
        if dx or dy:
            nx, ny = norm(dx, dy)
            spd = self.SPEED * 60 * dt
            self.x = clamp(self.x + nx*spd, 0, WORLD_W)
            self.y = clamp(self.y + ny*spd, 0, WORLD_H)
            self.move_dist += math.hypot(nx*spd, ny*spd)
        # Aim
        mx, my = mouse_world
        self.angle = math.atan2(my - self.y, mx - self.x)
        # Timers
        self.shoot_t  = max(0, self.shoot_t  - dt)
        self.hurt_t   = max(0, self.hurt_t   - dt)
        self.flash     = max(0, self.flash    - dt * 3)
        if self.reloading:
            self.reload_t -= dt
            if self.reload_t <= 0:
                self.ammo      = self.MAX_AMMO
                self.reloading = False
 
    def try_shoot(self):
        if self.reloading or self.shoot_t > 0:
            return None
        if self.ammo <= 0:
            play(SND_EMPTY) if AUDIO else None
            self.start_reload()
            return None
        self.ammo    -= 1
        self.shoot_t  = self.SHOOT_DELAY
        play(SND_SHOOT)
        if self.ammo == 0:
            self.start_reload()
        return Bullet(self.x, self.y, self.angle)
 
    def start_reload(self):
        if not self.reloading and self.ammo < self.MAX_AMMO:
            self.reloading = True
            self.reload_t  = self.RELOAD_TIME
            play(SND_RELOAD)
 
    def take_damage(self, dmg):
        if self.hurt_t > 0:
            return
        self.hp     -= dmg
        self.flash   = 1.0
        self.hurt_t  = self.HURT_IFRAMES
        play(SND_HURT)
        if self.hp <= 0:
            self.hp    = 0
            self.alive = False
 
    def draw(self, surf, cam_x, cam_y):
        sx, sy = world_to_screen(self.x, self.y, cam_x, cam_y)
        # Body glow if hurt
        if self.flash > 0:
            gs = pygame.Surface((self.r*4, self.r*4), pygame.SRCALPHA)
            pygame.draw.circle(gs, (255,60,60, int(self.flash*120)),
                               (self.r*2, self.r*2), self.r*2)
            surf.blit(gs, (sx-self.r*2, sy-self.r*2))
        # Shadow
        shad = pygame.Surface((self.r*2+6, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(shad, (0,0,0,70), (0,0,self.r*2+6,10))
        surf.blit(shad, (sx-self.r-3, sy+self.r-4))
        # Body
        col = (255,100,100) if self.flash > 0.5 else C_PLAYER
        pygame.draw.circle(surf, col, (sx, sy), self.r)
        pygame.draw.circle(surf, (200,255,200), (sx,sy), self.r, 2)
        # Torch direction line
        tx = sx + int(math.cos(self.angle) * (self.r+8))
        ty = sy + int(math.sin(self.angle) * (self.r+8))
        pygame.draw.line(surf, C_YELLOW, (sx,sy), (tx,ty), 3)
        # Eye dot
        ex = sx + int(math.cos(self.angle) * (self.r-4))
        ey = sy + int(math.sin(self.angle) * (self.r-4))
        pygame.draw.circle(surf, C_WHITE, (ex,ey), 3)
 
# ─────────────────────────────────────────────────────────────────────────────
#  FLASHLIGHT  (radial dark overlay with cone)
# ─────────────────────────────────────────────────────────────────────────────
def draw_flashlight(surf, px, py, angle, night_factor, chain_flicker=0):
    if night_factor <= 0:
        return
    darkness = int(220 * night_factor)
    # Full dark overlay
    dark = pygame.Surface((W, H), pygame.SRCALPHA)
    dark.fill((0, 0, 0, darkness))
    # Cut out a radial glow around player
    radius   = int(lerp(400, 180, night_factor))
    cone_len = int(lerp(500, 260, night_factor))
    cone_ang = math.radians(lerp(60, 38, night_factor))
    # Soft radial falloff
    for r in range(radius, 0, -20):
        a = int(darkness * (1 - r/radius) * 0.7)
        pygame.draw.circle(dark, (0,0,0,a), (px,py), r)
    # Cone of light
    steps = 30
    cone_pts = [(px, py)]
    for i in range(steps+1):
        a = angle - cone_ang + (2*cone_ang * i/steps)
        cx = px + int(math.cos(a) * cone_len)
        cy = py + int(math.sin(a) * cone_len)
        cone_pts.append((cx, cy))
    flicker = random.randint(-3,3) if chain_flicker > 0 else 0
    if len(cone_pts) > 2:
        pygame.draw.polygon(dark, (0,0,0,0), cone_pts)
    surf.blit(dark, (0, 0))
 
# ─────────────────────────────────────────────────────────────────────────────
#  HUD
# ─────────────────────────────────────────────────────────────────────────────
def draw_hud(surf, player, score, elapsed, ai_label, night_factor, wave):
    fnt_big = pygame.font.SysFont("consolas", 22, bold=True)
    fnt_sm  = pygame.font.SysFont("consolas", 14)
    fnt_med = pygame.font.SysFont("consolas", 17, bold=True)
 
    # ── Health bar ──
    hx, hy, hw, hh = 20, H-50, 180, 20
    pygame.draw.rect(surf, (40,10,10),   (hx, hy, hw, hh), border_radius=4)
    pct = player.hp / player.MAX_HP
    hcol = C_GREEN if pct > 0.5 else (C_YELLOW if pct > 0.25 else C_RED)
    pygame.draw.rect(surf, hcol, (hx, hy, int(hw*pct), hh), border_radius=4)
    pygame.draw.rect(surf, (80,80,80), (hx, hy, hw, hh), 1, border_radius=4)
    ht = fnt_sm.render(f"HP  {player.hp}/{player.MAX_HP}", True, C_WHITE)
    surf.blit(ht, (hx+4, hy+3))
 
    # ── Ammo ──
    ax, ay = 20, H-80
    ammo_col = C_YELLOW if not player.reloading else C_RED
    if player.reloading:
        pct_r = 1 - player.reload_t / player.RELOAD_TIME
        at = fnt_med.render(f"RELOADING {int(pct_r*100)}%", True, C_RED)
    else:
        at = fnt_med.render(f"AMMO  {player.ammo}/{player.MAX_AMMO}", True, ammo_col)
    surf.blit(at, (ax, ay))
 
    # ── Score & kills ──
    sc = fnt_big.render(f"SCORE  {score}", True, C_WHITE)
    surf.blit(sc, (W//2 - sc.get_width()//2, 14))
    kt = fnt_sm.render(f"Kills: {player.kills}   Wave: {wave}", True, (160,160,160))
    surf.blit(kt, (W//2 - kt.get_width()//2, 40))
 
    # ── Time & night ──
    mins = int(elapsed)//60
    secs = int(elapsed)%60
    tt = fnt_sm.render(f"{mins:02d}:{secs:02d}", True, (140,140,200))
    surf.blit(tt, (W-90, 14))
    night_lbl = "NIGHT" if night_factor > 0.5 else ("DUSK" if night_factor > 0.1 else "DAY")
    nl = fnt_sm.render(night_lbl, True, (180,160,100))
    surf.blit(nl, (W-80, 32))
 
    # ── AI state ──
    if ai_label:
        at2 = fnt_sm.render(ai_label, True, (255,100,60))
        surf.blit(at2, (W - at2.get_width() - 14, H-40))
 
    # ── Crosshair dot ──
    mx, my = pygame.mouse.get_pos()
    pygame.draw.circle(surf, (255,255,255,180), (mx,my), 5, 1)
    pygame.draw.line(surf, (255,255,255,180), (mx-8,my), (mx+8,my), 1)
    pygame.draw.line(surf, (255,255,255,180), (mx,my-8), (mx,my+8), 1)
 
# ─────────────────────────────────────────────────────────────────────────────
#  WORLD GRID (background)
# ─────────────────────────────────────────────────────────────────────────────
def draw_world(surf, cam_x, cam_y, night_factor):
    surf.fill(C_BG)
    cell = 80
    start_x = int(cam_x - W//2) // cell * cell
    start_y = int(cam_y - H//2) // cell * cell
    gc = (int(lerp(18,8,night_factor)), int(lerp(22,10,night_factor)), int(lerp(14,6,night_factor)))
    for gx in range(start_x, start_x + W + cell, cell):
        sx, _ = world_to_screen(gx, 0, cam_x, cam_y)
        pygame.draw.line(surf, gc, (sx, 0), (sx, H), 1)
    for gy in range(start_y, start_y + H + cell, cell):
        _, sy = world_to_screen(0, gy, cam_x, cam_y)
        pygame.draw.line(surf, gc, (0, sy), (W, sy), 1)
    # World border
    bx1, by1 = world_to_screen(0, 0, cam_x, cam_y)
    bx2, by2 = world_to_screen(WORLD_W, WORLD_H, cam_x, cam_y)
    pygame.draw.rect(surf, (60,30,30), (bx1, by1, bx2-bx1, by2-by1), 3)
 
# ─────────────────────────────────────────────────────────────────────────────
#  GAME MANAGER
# ─────────────────────────────────────────────────────────────────────────────
class GameManager:
    DAY_CYCLE = 90.0   # seconds per full day
 
    def __init__(self):
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("DEAD ZONE")
        self.clock   = pygame.time.Clock()
        self.fonts   = {
            "big":  pygame.font.SysFont("consolas", 48, bold=True),
            "med":  pygame.font.SysFont("consolas", 28, bold=True),
            "sm":   pygame.font.SysFont("consolas", 18),
            "tiny": pygame.font.SysFont("consolas", 13),
        }
        pygame.mouse.set_visible(False)
        self.state = "start"
        self._init_game()
 
    def _init_game(self):
        self.player      = Player()
        self.zombies     = []
        self.bullets     = []
        self.particles   = []
        self.ai          = AdaptiveAI()
        self.score       = 0
        self.elapsed     = 0.0
        self.spawn_timer = 0.0
        self.shake_t     = 0.0
        self.shake_mag   = 0.0
        self.wave        = 1
        self.wave_timer  = 30.0
        self.day_time    = 0.0   # 0..1 (0=noon, 0.5=midnight)
 
    @property
    def night_factor(self):
        # 0 = full day, 1 = full night
        # Sinusoidal cycle: peaks at 0.5 of day_time
        return clamp(math.sin(self.day_time * math.pi) ** 0.6, 0, 1)
 
    def _spawn_rate(self):
        base = 2.5 - min(2.0, self.elapsed / 60)
        wave_bonus = max(0.4, base - (self.wave-1)*0.15)
        night_bonus = lerp(wave_bonus, wave_bonus*0.6, self.night_factor)
        return night_bonus
 
    def _spawn_zombie(self):
        sx, sy = self.ai.get_spawn_position(self.player.x, self.player.y)
        sx = clamp(sx, 30, WORLD_W-30)
        sy = clamp(sy, 30, WORLD_H-30)
        # Type distribution shifts with wave
        r = random.random()
        if self.wave >= 3 and r < 0.18:
            ztype = "tank"
        elif self.wave >= 2 and r < 0.35:
            ztype = "fast"
        else:
            ztype = "normal"
        self.zombies.append(Zombie(sx, sy, ztype))
 
    def trigger_shake(self, mag=6, duration=0.25):
        self.shake_t   = duration
        self.shake_mag = mag
 
    def run(self):
        running = True
        while running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
 
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.state == "playing":
                            self.state = "paused"
                        elif self.state == "paused":
                            self.state = "playing"
                        else:
                            running = False
                    if event.key == pygame.K_r and self.state == "playing":
                        self.player.start_reload()
                    if event.key == pygame.K_RETURN and self.state in ("gameover","start"):
                        self._init_game()
                        self.state = "playing"
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if self.state == "playing":
                            b = self.player.try_shoot()
                            if b: self.bullets.append(b)
                        elif self.state in ("gameover","start"):
                            self._init_game()
                            self.state = "playing"
 
            if self.state == "playing":
                self._update(dt)
                self._draw()
            elif self.state == "paused":
                self._draw()
                self._draw_pause()
            elif self.state == "gameover":
                self._draw_gameover()
            elif self.state == "start":
                self._draw_start()
 
            pygame.display.flip()
 
        pygame.quit()
        sys.exit()
 
    # ── UPDATE ────────────────────────────────────────────────────────────────
    def _update(self, dt):
        keys = pygame.key.get_pressed()
        mx_s, my_s = pygame.mouse.get_pos()
        cam_x = self.player.x
        cam_y = self.player.y
        mx_w, my_w = screen_to_world(mx_s, my_s, cam_x, cam_y)
 
        self.elapsed   += dt
        self.day_time   = (self.elapsed % self.DAY_CYCLE) / self.DAY_CYCLE
 
        # Wave scaling
        self.wave_timer -= dt
        if self.wave_timer <= 0:
            self.wave       += 1
            self.wave_timer  = 30.0
 
        # Player update
        self.player.update(dt, keys, (mx_w, my_w))
        if not self.player.alive:
            self.state = "gameover"
            return
 
        # Adaptive AI update
        self.ai.update(dt, self.player.x, self.player.y)
 
        # Spawn zombies
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn_timer = self._spawn_rate()
            self._spawn_zombie()
            # Bonus spawns at high waves / night
            if self.wave >= 3 and random.random() < 0.4:
                self._spawn_zombie()
            if self.night_factor > 0.7 and random.random() < 0.3:
                self._spawn_zombie()
 
        # Bullets
        for b in self.bullets:
            b.update(dt)
        self.bullets = [b for b in self.bullets if b.alive]
 
        # Zombies
        for z in self.zombies:
            z.update(dt, self.player.x, self.player.y, self.ai.speed_mult)
 
        # Bullet–zombie collisions
        for b in self.bullets[:]:
            for z in self.zombies[:]:
                if z.alive and b.alive and b.rect().colliderect(z.rect()):
                    killed = z.take_damage(self.player.DAMAGE, b.vx, b.vy)
                    b.alive = False
                    if killed:
                        self.score += z.score_val
                        self.player.kills += 1
                        for _ in range(random.randint(8,18)):
                            self.particles.append(BloodParticle(z.x, z.y))
                        play(SND_DEATH)
                    else:
                        play(SND_HIT)
                        for _ in range(4):
                            self.particles.append(BloodParticle(z.x, z.y))
                    break
 
        # Zombie–player collision
        for z in self.zombies:
            if z.alive and dist((z.x,z.y),(self.player.x,self.player.y)) < z.r + self.player.r:
                dmg = {"normal":12,"fast":8,"tank":18}[z.ztype]
                prev_hp = self.player.hp
                self.player.take_damage(dmg)
                if self.player.hp < prev_hp:
                    self.trigger_shake(8, 0.3)
 
        # Particles
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive]
 
        # Cleanup dead zombies
        self.zombies = [z for z in self.zombies if z.alive]
 
        # Score: survival time bonus
        self.score += dt * 2
 
        # Shake
        self.shake_t = max(0, self.shake_t - dt)
 
    # ── DRAW ──────────────────────────────────────────────────────────────────
    def _draw(self):
        # Camera with shake
        cam_x = self.player.x
        cam_y = self.player.y
        if self.shake_t > 0:
            intensity = self.shake_t / 0.3
            cam_x += random.uniform(-self.shake_mag, self.shake_mag) * intensity
            cam_y += random.uniform(-self.shake_mag, self.shake_mag) * intensity
 
        nf = self.night_factor
 
        # World & grid
        draw_world(self.screen, cam_x, cam_y, nf)
 
        # Particles (behind player)
        for p in self.particles:
            p.draw(self.screen, cam_x, cam_y)
 
        # Zombies
        for z in self.zombies:
            z.draw(self.screen, cam_x, cam_y, nf)
 
        # Bullets
        for b in self.bullets:
            b.draw(self.screen, cam_x, cam_y)
 
        # Player
        self.player.draw(self.screen, cam_x, cam_y)
 
        # Flashlight overlay
        px_s, py_s = world_to_screen(self.player.x, self.player.y, cam_x, cam_y)
        draw_flashlight(self.screen, px_s, py_s, self.player.angle, nf,
                        chain_flicker=self.ai.is_camping)
 
        # HUD
        draw_hud(self.screen, self.player, int(self.score),
                 self.elapsed, self.ai.state_label, nf, self.wave)
 
    def _draw_overlay(self, title, lines, footer):
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 180))
        self.screen.blit(ov, (0,0))
        t = self.fonts["big"].render(title, True, C_RED)
        self.screen.blit(t, (W//2 - t.get_width()//2, H//2 - 140))
        for i, (txt, col) in enumerate(lines):
            s = self.fonts["med"].render(txt, True, col)
            self.screen.blit(s, (W//2 - s.get_width()//2, H//2 - 50 + i*44))
        fs = self.fonts["sm"].render(footer, True, (140,140,140))
        self.screen.blit(fs, (W//2 - fs.get_width()//2, H//2 + 170))
 
    def _draw_gameover(self):
        # Render one last frame of the world if possible
        draw_world(self.screen, self.player.x, self.player.y, 0.9)
        self._draw_overlay(
            "YOU DIED",
            [
                (f"Score:    {int(self.score)}", C_WHITE),
                (f"Kills:    {self.player.kills}", C_YELLOW),
                (f"Survived: {int(self.elapsed)}s   Wave {self.wave}", C_ORANGE),
            ],
            "ENTER or CLICK to restart  |  ESC to quit"
        )
 
    def _draw_start(self):
        draw_world(self.screen, WORLD_W//2, WORLD_H//2, 0.5)
        self._draw_overlay(
            "DEAD ZONE",
            [
                ("WASD / Arrows = Move",       C_WHITE),
                ("Mouse = Aim  |  Click = Shoot", C_WHITE),
                ("R = Reload   |  ESC = Pause", (160,160,160)),
            ],
            "ENTER or CLICK to begin"
        )
 
    def _draw_pause(self):
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 140))
        self.screen.blit(ov, (0,0))
        t = self.fonts["big"].render("PAUSED", True, C_WHITE)
        self.screen.blit(t, (W//2-t.get_width()//2, H//2-50))
        s = self.fonts["sm"].render("ESC to resume", True, (140,140,140))
        self.screen.blit(s, (W//2-s.get_width()//2, H//2+30))
 
# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    GameManager().run()