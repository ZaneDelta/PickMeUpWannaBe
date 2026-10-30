# ======================================================================
#  MAIN — Game Loop, UI & Save Migration
#  Game: Auto-Battle Strategy RPG "Pick Me Up: Infinite Gacha" (CLI)
#  Versi game: 2.0.0 (arsitektur 3 modul + database SQLite)
# ----------------------------------------------------------------------
#  Arsitektur:
#    database_setup.py -> init & baca game_database.db (SQLite)
#    generate_hero.py  -> Hero, Equipment, HeroGenerator, GachaSystem
#    main.py (ini)     -> Party, Enemy, BattleEngine, SaveSystem, Game
#  Backward compatibility: savegame.json versi 1.0.0 dari game lama
#  dimigrasi otomatis ke 2.0.0 tanpa KeyError / crash (deep-merge default).
#  Python 3 stdlib ONLY + 2 modul project.
# ======================================================================
import json
import os
import random
import sys
import time
from datetime import datetime

import database_setup as dbs
from generate_hero import (Hero, Equipment, Perk, Trait, Skill, HeroGenerator, GachaSystem,
                           weighted_choice, _safe_int, MAX_LEVEL, MAX_STAR,
                           CLASSES, EQUIP_SLOTS, roll_random_base_stats,
                           roll_random_growth_stats, roll_random_mp_regen,
                           roll_random_skills)

VERSION = "2.3.0"
GAME_DIR = os.path.dirname(os.path.abspath(__file__))
# Override path via environment (dipakai pengujian agar TIDAK menyentuh
# data produksi); default tetap di direktori game.
SAVE_PATH = os.environ.get("PMU_SAVE_PATH") or \
    os.path.join(GAME_DIR, "savegame.json")              # save lama single-file
SAVES_DIR = os.environ.get("PMU_SAVES_DIR") or \
    os.path.join(GAME_DIR, "saves")                      # save per-akun (v2.2+)
DB_PATH = dbs.DB_PATH

# Gabungan deskripsi item untuk layar Inventory (consumable + soulstone set)
ITEM_DESCS = dict(dbs.CONSUMABLE_DESCS)
ITEM_DESCS.update({n: d for n, (_c, _i, _q, d) in dbs.SOULSTONE_ITEMS.items()})

PARTY_MAX = 5           # jumlah hero aktif maksimum (sisanya bench)
ROUND_CAP = 50          # battle > 50 ronde = draw (dihitung kalah)
ENEMY_HP_SCALE = 0.02   # HP musuh naik superlinear ringan agar battle tidak 2-turn
HIDDEN_BOSS_CHANCE = 0.15  # peluang Emergency Raid setelah battle (canon: 15%)
HIDDEN_ESCAPE_LOSS = 0.10  # kabur dari hidden boss = kehilangan 10% coins

# Delay dramatis antar aksi battle (detik). Set PMU_DELAY=0 untuk mode cepat/testing.
try:
    BATTLE_DELAY = max(0.0, float(os.environ.get("PMU_DELAY", "0.5")))
except ValueError:
    BATTLE_DELAY = 0.5
# Mode battle cepat (diatur lewat menu Pengaturan, tersimpan per-akun):
# True = TANPA jeda antar aksi unit; jeda ganti ronde tetap berjalan.
BATTLE_FAST = False


def action_delay():
    """Jeda antar aksi unit: 0 saat mode cepat, BATTLE_DELAY saat normal."""
    return 0.0 if BATTLE_FAST else BATTLE_DELAY

# Data game yang kini disimpan di database SQLite:
PROMO_TABLE = dbs.PROMO_TABLE       # biaya Star Promotion 1->7 (eksponensial)
PERKS = dbs.load_perks()            # {nama: (tier, deskripsi)} dari tabel perks
TRAITS = PERKS                      # alias resmi Traits (dahulu Perks)
SKILLS = dbs.load_skills()          # {nama: {cls, tier, mp_cost, cd, kind, mult, description}}
TIER_LABEL = dbs.TIER_LABEL
STAR_MULTS = dbs.load_star_mults()  # {star: (base_mult, growth_mult)}

# --------------------------- DATA MUSUH ---------------------------
MOB_NAMES = {
    "Grunt":    ["Goblin", "Kobold", "Slime Raksasa", "Serigala Buas", "Bandit"],
    "Brute":    ["Ogre", "Minotaur", "Golem Batu", "Troll Guano", "Banteng Neraka"],
    "Assassin": ["Ninja Bayangan", "Harpy Kelabu", "Vampir Muda", "Mimic", "Wraith"],
    "Caster":   ["Penyihir Kultus", "Shaman Tulang", "Nekromanser", "Dukun Api", "Bomoh Es"],
}
# Tipe musuh: (modifier HP, modifier ATK)
TIPE_MOD = {"Grunt": (1.0, 1.0), "Brute": (1.4, 1.15),
            "Assassin": (0.7, 1.5), "Caster": (1.0, 1.25)}
BOSS_NAMES = ["Raja Lich Morvath", "Naga Muda Vhargos", "Titan Pasir Golgorak",
              "Ratu Arachne", "Panglima Iblis Baalzerk"]
HIDDEN_BOSS_NAMES = ["Moros sang Pemungut", "Astaroth sang Tersembunyi",
                     "Herald Kehampaan", "The Observer"]


# ============================ UTILITIES ============================
def sleep(t):
    """Sleep tahan interupsi Ctrl+C (KeyboardInterrupt tetap diteruskan)."""
    try:
        time.sleep(t)
    except KeyboardInterrupt:
        raise


def bar(cur, mx, width=20):
    """HP/MP bar sederhana: [####------] 40%"""
    cur = max(0, cur)
    pct = 0 if mx <= 0 else min(1.0, cur / mx)
    fill = int(round(pct * width))
    return "[" + "#" * fill + "-" * (width - fill) + "] %d%%" % int(round(pct * 100))


def line(ch="=", n=62):
    return ch * n


def header(title):
    print()
    print(line("=", 62))
    print(("  " + title).center(62))
    print(line("=", 62))


def pause():
    try:
        input("\n  [Enter untuk lanjut]")
    except (KeyboardInterrupt, EOFError):
        print()


def ask_int(prompt, lo=None, hi=None, default=None):
    """Validator input angka: loop sampai valid; tidak pernah crash.
    EOF (stdin tertutup) -> keluar bersih, bukan infinite loop."""
    while True:
        try:
            raw = input(prompt).strip()
            if raw == "" and default is not None:
                return default
            val = int(raw)
            if lo is not None and val < lo:
                print("  ! Minimal %s." % lo); continue
            if hi is not None and val > hi:
                print("  ! Maksimal %s." % hi); continue
            return val
        except ValueError:
            print("  ! Masukkan angka yang valid.")
        except (KeyboardInterrupt, EOFError):
            print(); _eof_exit()


def ask_choice(prompt, options):
    """Validator pilihan menu: loop sampai input ada di options.
    EOF (stdin tertutup) -> keluar bersih, bukan infinite loop."""
    opts = [str(o) for o in options]
    while True:
        try:
            raw = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print(); _eof_exit()
        if raw in opts:
            return raw
        print("  ! Pilihan tidak valid (%s)." % "/".join(opts))


def _eof_exit():
    """Dipanggil saat input stream berakhir (mis. Ctrl+D): keluar bersih."""
    print("  [Input ditutup] Keluar dari game.")
    raise SystemExit(0)


# =============================== PARTY ===============================
class Party:
    """Party aktif (maks 5 hero) + bench. Menyimpan NAME, bukan object,
    supaya gampang diserialisasi dan bebas reference loop."""
    def __init__(self):
        self.members = []       # list nama hero (maks PARTY_MAX)

    def add(self, hero, roster):
        if hero.name in self.members:
            return False, "%s sudah di party." % hero.name
        if len(self.members) >= PARTY_MAX:
            return False, "Party penuh (maks %d)." % PARTY_MAX
        self.members.append(hero.name)
        return True, "%s masuk party." % hero.name

    def remove(self, name):
        if name in self.members:
            self.members.remove(name)
            return True
        return False

    def get_members(self, roster):
        """Ambil object Hero hidup sesuai urutan members."""
        out = []
        for n in self.members:
            h = roster.get(n)
            if h and h.alive:
                out.append(h)
        return out

    def is_empty(self):
        return len(self.members) == 0

    def avg_level(self, roster):
        mem = self.get_members(roster)
        if not mem:
            return 1
        return sum(h.level for h in mem) / float(len(mem))


# ============================== ENEMY ==============================
class Enemy:
    """Musuh untuk Adventure / Tower / Hidden Boss.
    Stat dasar (Adventure): HP 120+24L, ATK 10+2.8L, DEF 4+0.85L, SPD 7+0.16L
    Stat dasar (Tower):     HP 130+24L, ATK 9+2.4L,  DEF 5+0.9L,  SPD 7+0.18L
    Lalu dikali modifier tipe (Grunt/Brute/Assassin/Caster) dan HP_SCALE."""

    def __init__(self, name, etype, level, hp, atk, dfn, spd, elite=False, boss=False):
        self.name = name
        self.etype = etype
        self.level = level
        self.max_hp = int(round(hp))
        self.hp = self.max_hp
        self.atk = int(round(atk))
        self.dfn = int(round(dfn))
        self.spd = float(spd)
        self.elite = elite
        self.boss = boss
        self.alive = True
        # Battle state
        self.stun_turns = 0
        self.slow_turns = 0

    @classmethod
    def make(cls, level, mode="adventure", etype=None, elite=False, boss=False):
        """Factory musuh. mode: 'adventure' | 'tower' | 'hidden'.
        HP dikali (1+scale)^(level-1) (superlinear ringan) supaya battle
        tidak selesai dalam 2 ronde tapi tetap tidak molor."""
        level = max(1, int(level))
        if mode == "tower":
            hp, atk, dfn, spd = 130 + 24 * level, 9 + 2.4 * level, 5 + 0.9 * level, 7 + 0.18 * level
        else:  # adventure & hidden memakai kurva yang sama
            hp, atk, dfn, spd = 120 + 24 * level, 10 + 2.8 * level, 4 + 0.85 * level, 7 + 0.16 * level
        # Scaling superlinear ringan: L20 = +48%, L50 = +172% HP
        hp *= (1.0 + ENEMY_HP_SCALE) ** (level - 1)
        if etype is None:
            etype = weighted_choice([("Grunt", 5), ("Brute", 3), ("Assassin", 2), ("Caster", 2)])
        hm, am = TIPE_MOD[etype]
        hp *= hm
        atk *= am
        if elite:
            hp *= 1.8
            atk *= 1.3
        if boss:
            hp *= 2.4
            atk *= 1.35
        name = random.choice(BOSS_NAMES if boss else MOB_NAMES[etype])
        if elite and not boss:
            name = "Elite " + name
        if mode == "hidden":
            name = random.choice(HIDDEN_BOSS_NAMES)
        return cls(name, etype, level, hp, atk, dfn, spd, elite, boss)

    @property
    def eff_spd(self):
        s = self.spd
        if self.slow_turns > 0:
            s *= 0.7
        return s

    def xp_reward(self):
        return 36 * self.level


# ========================= BATTLE ENGINE =========================
class BattleEngine:
    """Auto-battle tanpa input per turn. Satu ronde = semua unit hidup
    beraksi 1x, diurutkan SPD menurun (tie: hero dulu, lalu urutan masuk).
    Kematian hero = PERMANEN (permadeath); equipment hancur.
    can_escape=False (Tower/Hidden Boss setelah Fight) -> TIDAK ADA kabur
    sama sekali: battle wajib berakhir Victory atau Total Party Permadeath."""

    def __init__(self, heroes, enemies, can_escape=True, escape_cost_pct=0.0,
                 battle_items=None):
        self.heroes = list(heroes)      # object Hero (party aktif)
        self.enemies = list(enemies)    # object Enemy
        self.can_escape = can_escape
        self.escape_cost_pct = escape_cost_pct
        # TAS BATTLE: item bawaan dipakai OTOMATIS oleh AI. Referensi
        # LANGSUNG ke list milik pemain — item terpakai hilang dari tas.
        self.items = battle_items if battle_items is not None else []
        self.round = 0
        self.log = []
        self.result = None              # 'win' | 'lose' | 'escaped'

    # ---------------------------- helpers ----------------------------
    def say(self, text):
        print(text)
        self.log.append(text)

    def living_heroes(self):
        return [h for h in self.heroes if h.alive]

    def living_enemies(self):
        return [e for e in self.enemies if e.alive]

    def show_field(self):
        print("-" * 62)
        for h in self.living_heroes():
            print("  %-22s %s HP %d/%d%s" % (
                h.name[:22], bar(h.hp, h.max_hp), h.hp, h.max_hp,
                "  [TAUNT]" if h.taunt_turns > 0 else ""))
        for e in self.living_enemies():
            tag = " [BOSS]" if e.boss else (" [ELITE]" if e.elite else "")
            print("  %-22s %s HP %d/%d%s" % (
                e.name[:22], bar(e.hp, e.max_hp), e.hp, e.max_hp, tag))
        print("-" * 62)

    def ask_escape(self):
        """Opsi kabur — TEPAT SEKALI sebelum battle dimulai (hanya mode
        yang mengizinkan, yaitu Adventure). Inilah SATU-SATUNYA kesempatan
        kabur: begitu battle berjalan, tidak bisa kabur sama sekali.
        Return True jika pemain memilih kabur (result='escaped')."""
        if not self.can_escape or self.round > 0:
            return False
        try:
            raw = input("  Kabur sebelum battle? (y/N) > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            raw = "n"
        if raw == "y":
            self.result = "escaped"
            print("  ~ Kamu memilih mundur sebelum pertempuran dimulai. ~")
            return True
        return False

    # ---------------------------- damage ----------------------------
    def calc_damage(self, atk, dfn, variance=True):
        """Damage = max(1, ATK_total - DEF_total) + variance 5-10%.
        Variance: kalikan (1 - k) dengan k ~ U(0.05, 0.10) -> serangan
        selalu sedikit lebih lemah dari nilai mentah (feel RPG klasik)."""
        d = atk - dfn
        if variance:
            k = random.uniform(0.05, 0.10)
            d = d * (1.0 - k)
        return max(1, int(round(d)))

    def apply_damage_to_hero(self, hero, raw_atk, source_name):
        """Terapkan damage ke hero + cek kematian PERMANEN.
        Targeting taunt ditangani AI musuh (enemy_act)."""
        if not hero.alive:
            return 0
        # Guardian: hero NON-taunter yang punya perk ini dapat DEF +25%
        # selama ada ally lain yang sedang menarik perhatian (taunt aktif)
        dfn_eff = hero.dfn
        taunters = [t for t in self.living_heroes() if t.taunt_turns > 0]
        if taunters and hero is not taunters[0] and hero.has("Guardian"):
            dfn_eff = int(round(dfn_eff * 1.25))
        dmg = self.calc_damage(raw_atk, dfn_eff)
        hero.hp -= dmg
        hero.last_hit_by = source_name
        self.say("    >> %s kena %d dmg! (HP %d/%d)" % (hero.name, dmg, max(0, hero.hp), hero.max_hp))
        if hero.hp <= 0:
            # PRIORITAS 1: Revive Feather di Tas Battle — mencegah kematian
            # (dipakai otomatis oleh AI di detik terakhir)
            if "Revive Feather" in self.items:
                self.items.remove("Revive Feather")
                hero.hp = max(1, hero.max_hp * 2 // 5)
                self.say("    [ITEM] REVIVE FEATHER terpakai otomatis!")
                self.say("    [ITEM] %s bangkit dengan HP %d/%d!" % (hero.name, hero.hp, hero.max_hp))
            # PRIORITAS 2: Last Stand — sekali per battle, bertahan di 1 HP
            elif hero.has("Last Stand") and not hero.used_last_stand:
                hero.used_last_stand = True
                hero.hp = 1
                hero.buff_atk += 30
                self.say("    *** LAST STAND! %s bertahan di 1 HP, ATK +30%%! ***" % hero.name)
            else:
                self.handle_hero_death(hero, source_name)
        return dmg

    def handle_hero_death(self, hero, source):
        """Phoenix: sekali per battle revive 50% HP. Kalau tidak dipakai /
        tidak dimiliki: PERMADEATH — hero gugur, SEMUA equipment hancur."""
        if hero.has("Phoenix") and not hero.used_phoenix:
            hero.used_phoenix = True
            hero.hp = max(1, hero.max_hp // 2)
            self.say("    *** TRAIT PHOENIX! %s bangkit dari kematian (HP 50%%) ***" % hero.name)
            return
        hero.alive = False
        hero.hp = 0
        destroyed = [eq.describe() for eq in hero.equipment.values() if eq]
        hero.equipment = {"Senjata": None, "Zirah": None, "Aksesori": None}
        self.say("    XXX %s TELAH GUGUR secara permanen! XXX" % hero.name)
        if destroyed:
            self.say("    XXX Semua equipment %s hancur: %s" % (hero.name, "; ".join(destroyed)))
        else:
            self.say("    XXX Semua equipment %s hancur." % hero.name)

    def apply_damage_to_enemy(self, enemy, dmg, source_name):
        enemy.hp -= dmg
        self.say("    >> %s -> %s: %d dmg (HP %d/%d)" % (
            source_name, enemy.name, dmg, max(0, enemy.hp), enemy.max_hp))
        if enemy.hp <= 0 and enemy.alive:
            enemy.alive = False
            self.say("    ### %s DIKALAHKAN! ###" % enemy.name)

    # ------------------------- aksi hero -------------------------
    def hero_act(self, h):
        """AI Hero berbasis skill unik yang dimiliki hero (h.skills),
        tidak lagi dikunci oleh class. MP kurang / cooldown -> fallback attack."""
        enemies = self.living_enemies()
        if not enemies:
            return
        # Stun: lewatkan giliran
        if h.stun_turns > 0:
            h.stun_turns -= 1
            self.say("  [R%d] %s STUN, giliran dilewati." % (self.round, h.name))
            return
        # Ketidakstabilan Mental (Hero Synthesis): jika sanity < 40.0,
        # peluang 20% jiwa di dalam tubuh hero mengamuk / mengambil alih
        if getattr(h, "sanity", 100.0) < 40.0 and random.random() < 0.20:
            self._trigger_mental_instability(h, enemies)
            return
        # AI ITEM: sebelum aksi lain, hero "berpikir" apakah item bawaan
        # lebih bernilai dipakai sekarang (lihat _try_use_battle_item).
        if self._try_use_battle_item(h):
            return
        # Coba gunakan skill unik milik hero yang siap (cukup MP & tidak cooldown)
        if self.use_hero_skill(h, enemies):
            return
        # Fallback: serangan dasar ke musuh prioritas
        target = min(enemies, key=lambda e: (e.hp, -e.atk))
        self.basic_attack(h, target)

    def _soul_berserk_attack(self, h, enemies):
        """Serangan brutal Soul Berserk: target acak, ATK x1.35, abaikan 50% DEF."""
        if not enemies:
            return
        target = random.choice(enemies)
        base_atk, note = self.atk_with_perks(h, target)
        eff_dfn = int(target.dfn * 0.50)
        dmg = self.calc_damage(int(round(base_atk * 1.35)), eff_dfn)
        self.say("  [R%d] %s [SOUL BERSERK] menerjang %s secara brutal!%s" % (
            self.round, h.name, target.name, note))
        self.apply_damage_to_enemy(target, dmg, h.name)
        lifesteal_pct = (0.20 if h.has("Vampiric") else 0.0) + (0.10 if h.has("Bloodthirst") else 0.0)
        if lifesteal_pct > 0 and h.alive:
            heal = max(1, int(dmg * lifesteal_pct))
            h.hp = min(h.max_hp, h.hp + heal)
            self.say("    ~~ Lifesteal: %s pulih %d HP" % (h.name, heal))

    def _trigger_mental_instability(self, h, enemies):
        """Efek sanity kritis (< 40.0): 50% Soul Berserk / 50% Memory Echo."""
        if random.random() < 0.50:
            self.say("  [!] Jiwa di dalam tubuh %s mengamuk tak terkendali!" % h.name)
            self._soul_berserk_attack(h, enemies)
            return
        self.say("  [!] Fragmen ingatan tumbal mengambil alih tubuh %s!" % h.name)
        off_kinds = ("aoe_stun", "aoe_pierce", "aoe_slow", "pierce", "drain", "stun", "single")
        off_cands = []
        for sk_name in (getattr(h, "skills", None) or []):
            info = SKILLS.get(sk_name)
            if info and info.get("kind") in off_kinds:
                off_cands.append((sk_name, info))
        if not off_cands:
            # Fallback ke Soul Berserk bila hero tidak punya skill ofensif
            self._soul_berserk_attack(h, enemies)
            return
        sk_name, info = random.choice(off_cands)
        kind = info["kind"]
        mult = info["mult"]
        if h.has("Overcharge") and h.max_mp > 0 and h.mana > h.max_mp * 0.70:
            mult *= 1.30
        label = "%s (Memory Echo)" % sk_name.upper()
        # Eksekusi tanpa menguras MP (h.mana tetap utuh)
        if kind.startswith("aoe"):
            tier_s = info.get("tier", "Common")
            stun_c = 0.0
            if kind == "aoe_stun":
                stun_c = 0.25 if tier_s == "Legendary" else (0.18 if tier_s == "Epic" else 0.12)
            self.cast_aoe(h, mult, label, stun_chance=stun_c,
                          slow=(kind == "aoe_slow"), ignore_def=(kind == "aoe_pierce"))
            return
        target = random.choice(enemies)
        base_atk, note = self.atk_with_perks(h, target)
        eff_dfn = 0 if kind == "pierce" else target.dfn
        dmg = self.calc_damage(int(base_atk * mult), eff_dfn)
        extra = " (ignore DEF)" if kind == "pierce" else ""
        self.say("  [R%d] %s: %s%s ke %s%s" % (
            self.round, h.name, label, extra, target.name, note))
        if kind == "stun":
            tier_s = info.get("tier", "Common")
            stun_rate = 0.35 if tier_s in ("Epic", "Legendary") else (0.25 if tier_s == "Rare" else 0.20)
            if random.random() < stun_rate:
                target.stun_turns = 1
                self.say("    !! %s terkena STUN 1 ronde!" % target.name)
        self.apply_damage_to_enemy(target, dmg, h.name)
        if kind == "drain" and h.alive:
            drain_hp = max(1, int(dmg * 0.40))
            before = h.hp
            h.hp = min(h.max_hp, h.hp + drain_hp)
            self.say("    ++ %s menyerap %d HP (%d/%d)" % (
                h.name, h.hp - before, h.hp, h.max_hp))

    # ------------------------- AI: TAS BATTLE -------------------------
    def _try_use_battle_item(self, h):
        """AI hero 'berpikir' memakai item dari Tas Battle sebelum aksi
        lain. Mengembalikan True bila item terpakai (giliran terpakai).
        Keputusan per item:
          Potion HP      -> ada ally (atau diri) HP < 40% -> hero paling kritis
          Mana Philter   -> diri MP < 30% max (mage/buffer paling diuntungkan)
          Attack Elixir  -> ronde >= 2 & belum ada buff ATK aktif
          Guard Elixir   -> ronde >= 2 & belum ada buff DEF aktif
          Revive Feather -> TIDAK dipakai lewat jalur ini (dipakai otomatis
                            di detik terakhir saat hero akan mati)
        """
        if not self.items:
            return False
        allies = self.living_heroes()
        # ---- Potion HP ----
        if "Potion HP" in self.items:
            wounded = [a for a in allies if a.hp < a.max_hp * 0.4]
            if wounded:
                target = min(wounded, key=lambda a: a.hp / a.max_hp)
                self.items.remove("Potion HP")
                amount = target.max_hp // 2
                before = target.hp
                target.hp = min(target.max_hp, target.hp + amount)
                self.say("  [R%d] %s menggunakan POTION HP -> %s (+%d HP, %d/%d)" % (
                    self.round, h.name, target.name, target.hp - before,
                    target.hp, target.max_hp))
                return True
        # ---- Mana Philter ----
        if "Mana Philter" in self.items and h.max_mp > 0 and h.mana < h.max_mp * 0.3:
            self.items.remove("Mana Philter")
            h.mana = h.max_mp
            self.say("  [R%d] %s menggunakan MANA PHILTER -> dirinya (MP penuh!)" % (
                self.round, h.name))
            return True
        # ---- Attack Elixir (buff party belum ada, mulai ronde 2) ----
        if "Attack Elixir" in self.items and self.round >= 2 and \
                not any(a.buff_atk > 0 for a in allies):
            self.items.remove("Attack Elixir")
            for a in allies:
                a.buff_atk = max(a.buff_atk, 30)
            self.say("  [R%d] %s menggunakan ATTACK ELIXIR! ATK party +30%% (3 ronde)" % (
                self.round, h.name))
            return True
        # ---- Guard Elixir ----
        if "Guard Elixir" in self.items and self.round >= 2 and \
                not any(a.buff_def > 0 for a in allies):
            self.items.remove("Guard Elixir")
            for a in allies:
                a.buff_def = max(a.buff_def, 30)
            self.say("  [R%d] %s menggunakan GUARD ELIXIR! DEF party +30%% (3 ronde)" % (
                self.round, h.name))
            return True
        return False

    def use_hero_skill(self, h, enemies):
        """Evaluasi dan jalankan skill dari h.skills yang siap (off-cooldown & MP cukup).
        Urutan prioritas AI cerdas:
          1. Heal / Cleanse darurat (Mass Heal bila >=2 ally luka, Cleanse/Heal bila ally luka/stun)
          2. Taunt (khusus skill class Tanker bila belum ada taunt aktif pada diri sendiri)
          3. Buff party / Mana gift (War Cry / Attack / Guard / Speed / Mana Chorus)
          4. Skill ofensif / AoE / CC terkuat yang siap dipakai
        Return True bila skill digunakan, False bila tidak ada yang dipakai."""
        skills = getattr(h, "skills", None) or []
        if not skills:
            return False
        ready = []
        for sk_name in skills:
            info = SKILLS.get(sk_name)
            if not info:
                continue
            eff_cost = h.skill_mp_cost(info["mp_cost"]) if hasattr(h, "skill_mp_cost") else info["mp_cost"]
            if h.skill_cd.get(sk_name, 0) <= 0 and h.mana >= eff_cost:
                ready.append((sk_name, info, eff_cost))
        if not ready:
            return False

        allies = self.living_heroes()
        wounded = [a for a in allies if a.hp < a.max_hp * 0.60]
        stunned_allies = [a for a in allies if a.stun_turns > 0]

        # 1) Mass Heal, Cleanse Heal, & Single Heal
        for sk_name, info, eff_cost in ready:
            if info["kind"] == "mass_heal" and len(wounded) >= 2:
                h.mana -= eff_cost
                h.skill_cd[sk_name] = info["cd"]
                amount = int(info["mult"] * h.atk + 15)
                self.say("  [R%d] %s: %s (%d HP semua ally)" % (
                    self.round, h.name, sk_name.upper(), amount))
                for a in allies:
                    self.heal_unit(h, a, amount)
                return True
        for sk_name, info, eff_cost in ready:
            if info["kind"] == "cleanse_heal" and (wounded or stunned_allies):
                h.mana -= eff_cost
                h.skill_cd[sk_name] = info["cd"]
                cands = stunned_allies if stunned_allies else wounded
                target = min(cands, key=lambda a: a.hp / a.max_hp)
                target.stun_turns = 0
                amount = int(info["mult"] * h.atk + 20)
                self.say("  [R%d] %s: %s ke %s (pulih & murnikan stun)" % (
                    self.round, h.name, sk_name.upper(), target.name))
                self.heal_unit(h, target, amount)
                return True
        for sk_name, info, eff_cost in ready:
            if info["kind"] == "heal" and wounded:
                h.mana -= eff_cost
                h.skill_cd[sk_name] = info["cd"]
                target = min(wounded, key=lambda a: a.hp / a.max_hp)
                amount = int(info["mult"] * h.atk + 25)
                self.say("  [R%d] %s: %s ke %s" % (
                    self.round, h.name, sk_name.upper(), target.name))
                self.heal_unit(h, target, amount)
                return True

        # 2) Taunt (hanya dimiliki pool class Tanker)
        for sk_name, info, eff_cost in ready:
            if info["kind"] == "taunt" and h.taunt_turns <= 0:
                h.mana -= eff_cost
                h.skill_cd[sk_name] = info["cd"]
                h.taunt_turns = 2
                def_bonus = int(info["mult"]) if info["mult"] >= 10 else 30
                h.buff_def = max(h.buff_def, def_bonus)
                self.say("  [R%d] %s: %s! (musuh dipaksa menarget, DEF +%d%%)" % (
                    self.round, h.name, sk_name.upper(), def_bonus))
                return True

        # 3) Buff party & Mana Gift
        atk_active = any(a.buff_atk > 0 for a in allies)
        def_active = any(a.buff_def > 0 for a in allies)
        spd_active = any(a.buff_spd > 0 for a in allies)
        low_mp_allies = [a for a in allies if a.mana < a.max_mp * 0.65]
        for sk_name, info, eff_cost in ready:
            if info["kind"] == "buff_all" and (not atk_active or not spd_active):
                h.mana -= eff_cost
                h.skill_cd[sk_name] = info["cd"]
                pct = int(info["mult"])
                self.say("  [R%d] %s: %s! ATK +%d%% & SPD +20%% party (3 ronde)" % (
                    self.round, h.name, sk_name.upper(), pct))
                for a in allies:
                    a.buff_atk = max(a.buff_atk, pct)
                    a.buff_spd = max(a.buff_spd, 20)
                return True
            if info["kind"] == "buff_atk" and not atk_active:
                h.mana -= eff_cost
                h.skill_cd[sk_name] = info["cd"]
                pct = int(info["mult"])
                self.say("  [R%d] %s: %s! ATK party +%d%% (3 ronde)" % (
                    self.round, h.name, sk_name.upper(), pct))
                for a in allies:
                    a.buff_atk = max(a.buff_atk, pct)
                return True
            if info["kind"] == "buff_def" and not def_active:
                h.mana -= eff_cost
                h.skill_cd[sk_name] = info["cd"]
                pct = int(info["mult"])
                self.say("  [R%d] %s: %s! DEF party +%d%% (3 ronde)" % (
                    self.round, h.name, sk_name.upper(), pct))
                for a in allies:
                    a.buff_def = max(a.buff_def, pct)
                return True
            if info["kind"] == "buff_spd" and not spd_active:
                h.mana -= eff_cost
                h.skill_cd[sk_name] = info["cd"]
                pct = int(info["mult"])
                self.say("  [R%d] %s: %s! SPD party +%d%% (3 ronde)" % (
                    self.round, h.name, sk_name.upper(), pct))
                for a in allies:
                    a.buff_spd = max(a.buff_spd, pct)
                return True
            if info["kind"] == "mana_gift" and low_mp_allies:
                h.mana -= eff_cost
                h.skill_cd[sk_name] = info["cd"]
                mp_amt = int(info["mult"])
                self.say("  [R%d] %s: %s! (+%d MP ke seluruh party)" % (
                    self.round, h.name, sk_name.upper(), mp_amt))
                for a in allies:
                    a.mana = min(a.max_mp, a.mana + mp_amt)
                return True

        # 4) Skill ofensif (urutkan dari dampak / MP cost terbesar)
        off_kinds = ("aoe_stun", "aoe_pierce", "aoe_slow", "pierce", "drain", "stun", "single")
        off_ready = [(s, inf, c) for s, inf, c in ready if inf["kind"] in off_kinds]
        if not off_ready:
            return False
        off_ready.sort(key=lambda x: (-x[1]["mp_cost"], -x[1]["mult"]))
        sk_name, info, eff_cost = off_ready[0]
        kind = info["kind"]
        mult = info["mult"]
        # Trait Overcharge: saat MP > 70% sebelum cast, damage skill +30%
        if h.has("Overcharge") and h.max_mp > 0 and h.mana > h.max_mp * 0.70:
            mult *= 1.30
        cost = eff_cost
        label = sk_name.upper()

        # AoE skills (mendukung trait Double Cast untuk semua hero)
        if kind.startswith("aoe"):
            if h.has("Double Cast") and random.random() < 0.15:
                cost = 0
                label += " (Double Cast: gratis!)"
            h.mana -= cost
            h.skill_cd[sk_name] = info["cd"]
            tier_s = info.get("tier", "Common")
            stun_c = 0.0
            if kind == "aoe_stun":
                stun_c = 0.25 if tier_s == "Legendary" else (0.18 if tier_s == "Epic" else 0.12)
            is_slow = (kind == "aoe_slow")
            ignore_def = (kind == "aoe_pierce")
            self.cast_aoe(h, mult, label, stun_chance=stun_c, slow=is_slow, ignore_def=ignore_def)
            return True

        # Single-target offensive skills
        h.mana -= cost
        h.skill_cd[sk_name] = info["cd"]
        target = min(enemies, key=lambda e: (e.hp, -e.atk))
        base_atk, note = self.atk_with_perks(h, target)
        eff_dfn = 0 if kind == "pierce" else target.dfn
        dmg = self.calc_damage(int(base_atk * mult), eff_dfn)
        extra = " (ignore DEF)" if kind == "pierce" else ""
        self.say("  [R%d] %s: %s%s ke %s%s" % (
            self.round, h.name, label, extra, target.name, note))
        if kind == "stun":
            tier_s = info.get("tier", "Common")
            stun_rate = 0.35 if tier_s in ("Epic", "Legendary") else (0.25 if tier_s == "Rare" else 0.20)
            if random.random() < stun_rate:
                target.stun_turns = 1
                self.say("    !! %s terkena STUN 1 ronde!" % target.name)
        self.apply_damage_to_enemy(target, dmg, h.name)
        if kind == "drain" and h.alive:
            drain_hp = max(1, int(dmg * 0.40))
            before = h.hp
            h.hp = min(h.max_hp, h.hp + drain_hp)
            self.say("    ++ %s menyerap %d HP (%d/%d)" % (
                h.name, h.hp - before, h.hp, h.max_hp))
        return True

    def atk_with_perks(self, h, target):
        """Hitung ATK efektif + label trait ofensif (Focused Fire/Executioner/dll).
        Return tuple (atk_int, label_string) untuk log battle."""
        a = h.atk
        note = ""
        if h.has("Focused Fire"):
            a = int(a * 1.20)
            note += " [Focused Fire]"
        if target and target.hp > target.max_hp * 0.80 and h.has("First Strike"):
            a = int(a * 1.25)
            note += " [First Strike]"
        if target and (target.boss or target.elite) and h.has("Giant Slayer"):
            a = int(a * 1.25)
            note += " [Giant Slayer]"
        if target and target.boss and h.has("Godslayer"):
            a = int(a * 1.30)
            note += " [Godslayer]"
        if target and target.hp < target.max_hp * 0.25 and h.has("Executioner"):
            a = int(a * 1.50)
            note += " [EXECUTE]"
        return a, note

    def basic_attack(self, h, target, atk_override=None):
        """Serangan fisik biasa dengan semua pengecekan trait ofensif."""
        if atk_override is not None:
            a, note = atk_override if isinstance(atk_override, tuple) else (atk_override, "")
        else:
            a, note = self.atk_with_perks(h, target)
        # Unlucky: 15% serangan meleset (kecuali punya Precision)
        if h.has("Unlucky") and not h.has("Precision") and random.random() < 0.15:
            self.say("  [R%d] %s: serangan MELESET! %s" % (self.round, h.name, note))
            return
        dmg = self.calc_damage(a, target.dfn)
        self.say("  [R%d] %s menyerang %s%s" % (self.round, h.name, target.name, note))
        self.apply_damage_to_enemy(target, dmg, h.name)
        # Vampiric (20%) & Bloodthirst (10%): lifesteal dari serangan fisik
        lifesteal_pct = (0.20 if h.has("Vampiric") else 0.0) + (0.10 if h.has("Bloodthirst") else 0.0)
        if lifesteal_pct > 0 and h.alive:
            heal = max(1, int(dmg * lifesteal_pct))
            h.hp = min(h.max_hp, h.hp + heal)
            self.say("    ~~ Lifesteal: %s pulih %d HP" % (h.name, heal))

    def heal_unit(self, healer, target, amount):
        """Heal dengan trait Miracle Hand (+30%, 10% crit heal x2) & Celestial Grace (+25%)."""
        if healer.has("Celestial Grace") or target.has("Celestial Grace"):
            amount = int(amount * 1.25)
        if healer.has("Miracle Hand"):
            amount = int(amount * 1.3)
            if random.random() < 0.10:
                amount *= 2
                self.say("    ~~ CRIT HEAL!")
        before = target.hp
        target.hp = min(target.max_hp, target.hp + amount)
        self.say("    ++ %s pulih %d HP (%d/%d)" % (
            target.name, target.hp - before, target.hp, target.max_hp))

    def cast_aoe(self, h, mult, label, stun_chance=0.0, slow=False, ignore_def=False):
        """AoE skill: hit SEMUA musuh + peluang stun/slow/ignore DEF per musuh."""
        self.say("  [R%d] %s melepaskan %s! (AoE semua musuh)" % (self.round, h.name, label))
        for e in self.living_enemies():
            eff_dfn = 0 if ignore_def else e.dfn
            dmg = self.calc_damage(int(h.atk * mult), eff_dfn)
            self.apply_damage_to_enemy(e, dmg, "%s [%s]" % (h.name, label))
            if e.alive and stun_chance > 0 and random.random() < stun_chance:
                e.stun_turns = 1
                self.say("    !! %s terkena STUN 1 ronde!" % e.name)
            if e.alive and slow:
                e.slow_turns = 2
                self.say("    ~~ %s melambat (-30%% SPD, 2 ronde)" % e.name)

    # ------------------------- aksi musuh -------------------------
    def enemy_act(self, e):
        """AI musuh sederhana: serang hero dengan taunt dulu, selain itu
        random. Caster: 50% damage splash ke ally acak."""
        heroes = self.living_heroes()
        if not heroes:
            return
        if e.stun_turns > 0:
            e.stun_turns -= 1
            self.say("  [R%d] %s STUN, giliran dilewati." % (self.round, e.name))
            return
        # Prioritas: hero manapun dengan taunt aktif
        taunters = [h for h in heroes if h.taunt_turns > 0]
        target = random.choice(heroes) if not taunters else taunters[0]
        dmg = self.calc_damage(e.atk, target.dfn)
        self.say("  [R%d] %s menyerang %s" % (self.round, e.name, target.name))
        # Taunt mengurangi damage yang diterima Tanker via DEF-nya sendiri
        self.apply_damage_to_hero(target, e.atk, e.name)
        # Caster: splash 50% dmg ke hero lain acak
        if e.etype == "Caster" and target.alive:
            others = [x for x in heroes if x is not target and x.alive]
            if others and random.random() < 0.5:
                splash = self.calc_damage(int(e.atk * 0.5), 0)
                vic = random.choice(others)
                self.say("    >> Splash sihir %s -> %s" % (e.name, vic.name))
                self.apply_damage_to_hero(vic, e.atk // 2, e.name)

    # ---------------------------- ronde ----------------------------
    def run_round(self):
        """Satu ronde penuh: sort SPD desc (tie: party dulu) -> aksi ->
        cek kematian -> regen MP -> buff tick-down."""
        self.round += 1
        self.say("")
        self.say("======== RONDE %d ========" % self.round)
        # Urutan aksi: SPD menurun. Tie-break: hero sebelum musuh, lalu
        # urutan list (stabil via index) — penting untuk determinisme.
        units = [("hero", i, h) for i, h in enumerate(self.heroes) if h.alive]
        units += [("enemy", i, e) for i, e in enumerate(self.enemies) if e.alive]
        # SPD float tanpa rounding agar urutan adil; tie: party dulu
        units.sort(key=lambda u: (-u[2].spd if u[0] == "hero" else -(u[2].eff_spd + 0.01),
                                  0 if u[0] == "hero" else 1, u[1]))
        for kind, _, unit in units:
            if self.result:
                break
            if kind == "hero" and unit.alive:
                self.hero_act(unit)
            elif kind == "enemy" and unit.alive:
                self.enemy_act(unit)
            sleep(action_delay())
            # Cek kondisi akhir SETELAH SETIAP aksi
            if not self.living_enemies():
                self.result = "win"
                break
            if not self.living_heroes():
                self.result = "lose"
                break
        if not self.result:
            # End of round: regen MP, trait HP regen, tick buffs/cooldowns
            for h in self.living_heroes():
                h.mana = min(h.max_mp, h.mana + h.mp_regen)
                regen_pct = (0.05 if h.has("Vitality Aura") else 0.0) + \
                            (0.08 if h.has("Immortal Vessel") else 0.0)
                if regen_pct > 0 and h.hp < h.max_hp:
                    h.hp = min(h.max_hp, h.hp + max(1, int(h.max_hp * regen_pct)))
                if h.taunt_turns > 0:
                    h.taunt_turns -= 1
                    if h.taunt_turns == 0:
                        h.buff_def = 0  # buff taunt hilang bersama taunt
                h.buff_atk = max(0, h.buff_atk - 10) if h.buff_atk > 0 else 0
                h.buff_def = max(0, h.buff_def - 10) if h.buff_def > 0 and h.taunt_turns <= 0 else h.buff_def
                h.buff_spd = max(0, h.buff_spd - 10) if h.buff_spd > 0 else 0
                for k in list(h.skill_cd):
                    h.skill_cd[k] = max(0, h.skill_cd[k] - 1)
            for e in self.living_enemies():
                if e.stun_turns > 0:
                    e.stun_turns -= 1
                if e.slow_turns > 0:
                    e.slow_turns -= 1
            self.show_field()
            # Jeda GANTI RONDE tetap berjalan di semua mode (readability
            # antar ronde); hanya jeda antar aksi unit yang bisa dimatikan.
            sleep(BATTLE_DELAY)

    def run(self):
        """Loop utama battle. Return self.result: 'win'|'lose'|'escaped'.
        Kabur HANYA dimungkinkan lewat ask_escape() SEBELUM ronde pertama.
        Setelah battle berjalan — mode apapun (Adventure/Tower/Hidden Boss)
        — TIDAK ADA kabur: battle wajib berakhir Victory atau Total Party
        Permadeath (draw pada ronde 50 dihitung kalah)."""
        self.show_field()
        if self.ask_escape():
            return self.result
        while not self.result:
            if self.round >= ROUND_CAP:
                # Cap 50 ronde: draw dihitung kalah (aggro pertempuran terhenti)
                self.result = "lose"
                self.say("  Battle mencapai %d ronde. Imbang — dihitung KALAH." % ROUND_CAP)
                break
            self.run_round()
        self.say("")
        if self.result == "win":
            self.say("=*= KEMENANGAN! Semua musuh dikalahkan! =*=")
        elif self.result == "lose":
            if self.round >= ROUND_CAP:
                # Draw oleh round cap: tidak ada yang tumbang, tapi dihitung kalah
                self.say("=X= DRAW pada ronde %d — dihitung KALAH. =X=" % ROUND_CAP)
            else:
                self.say("=X= KALAH... Party telah tumbang. =X=")
        else:
            self.say("=~ Kamu berhasil kabur. =~")
        sleep(BATTLE_DELAY)
        return self.result


# ==================== SAVE PER-AKUN & MIGRASI LAMA ====================
def account_save_path(username):
    """Path savegame per-akun: saves/<username>.json. Tiap akun punya
    savegame terpisah — update game TIDAK menghapus progres karena data
    akun disimpan di file yang tidak pernah disentuh patcher versi."""
    safe = "".join(ch for ch in (username or "") if ch.isalnum() or ch in "-_")
    safe = safe or "player"
    return os.path.join(SAVES_DIR, safe + ".json")


def claim_legacy_save(username):
    """Migrasi save lama single-file (savegame.json dari versi < 2.2) ke
    akun yang sedang login — sekali saja. Return (state_dict | None).
    Setelah migrasi, file lama di-rename .migrated agar tidak ditawarkan
    ulang ke akun lain."""
    acc_path = account_save_path(username)
    if os.path.exists(acc_path) or not os.path.exists(SAVE_PATH):
        return None  # akun sudah punya save / tidak ada save lama
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return None
        print("  [MIGRASI] Savegame lama (single-file) ditemukan.")
        if ask_choice("  Pindahkan semua datanya ke akun '%s'? (y/n) > "
                      % username, ["y", "n"]) != "y":
            return None  # biarkan file lama; akun mulai fresh
        os.makedirs(SAVES_DIR, exist_ok=True)
        with open(acc_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=1, ensure_ascii=False)
        os.replace(SAVE_PATH, SAVE_PATH + ".migrated")
        print("  [MIGRASI] Semua progres lama dipindahkan ke akun '%s'. "
              "Tidak ada yang hilang." % username)
        return raw
    except Exception as e:
        print("  ! Migrasi save lama gagal (game tetap jalan): %s" % e)
        return None


# ========================= SPLASH & LOGIN =========================
def splash_screen():
    """Splash screen: judul + versi game."""
    print(line("=", 62))
    print(r"    ____  _    ____  _  _______ _   _ _____ __  __    _    ___ ".center(62))
    print(r"   |  _ \| |  / __ )/ \|__  /_ _| \ | | ____|  \/  |  / \  / _ \\".center(62))
    print(r"   | |_) | | |  _ \| _ \ / / | ||  \| |  _| | |\/| | / _ \| | | |".center(62))
    print(r"   |  __/| |_| |_) | |/ / /_ | || |\  | |___| |  | |/ ___ \ |_| |".center(62))
    print(r"   |_|    \____|____/_/\_\___|___|_| \_|_____|_|  |_/_/   \_\___/ ".center(62))
    print()
    print("  AUTO-BATTLE STRATEGY RPG".center(62))
    print("  Pick Me Up: Infinite Gacha".center(62))
    print(("  Versi %s — 3 Modul + Database SQLite" % VERSION).center(62))
    print(line("=", 62))
    sleep(0.8)


def ask_login_text(prompt):
    """Input teks login tahan Ctrl+C (EOF = keluar bersih)."""
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print()
        _eof_exit()


def login_menu():
    """Login / register. Password di-hash+salt di tabel accounts (SQLite).
    Return username yang berhasil login."""
    splash_screen()
    while True:
        header("LOGIN — PICK ME UP: INFINITE GACHA v%s" % VERSION)
        print("  1. Masuk")
        print("  2. Daftar akun baru")
        print("  0. Keluar")
        c = ask_choice("  Pilih > ", ["0", "1", "2"])
        if c == "0":
            print("  Sampai jumpa, Master!")
            sys.exit(0)
        if c == "2":
            u = ask_login_text("  Username baru (min 3 karakter) > ")
            p = ask_login_text("  Password (min 4 karakter)      > ")
            ok, msg = dbs.create_account(u, p)
            print("  " + msg)
            if ok:
                print("  Silakan login dengan akun baru Anda.")
            continue
        u = ask_login_text("  Username > ")
        p = ask_login_text("  Password > ")
        ok, msg = dbs.verify_account(u, p)
        print("  " + msg)
        if ok:
            return u
        # gagal -> loop kembali ke menu login
class SaveSystem:
    """Save/load JSON dengan VERSIONING + MIGRASI otomatis.
    Prinsip: JANGAN PERNAH crash saat load save versi lama — semua akses
    dibungkus try/except dan di-merge dengan default. Savegame versi 1.0.0
    (single-file) dimigrasi mulus ke 2.0.0 (arsitektur 3 modul + SQLite):
    key baru (equip_bag, equip_seq, dll) diisi nilai default fallback."""

    def __init__(self, path=SAVE_PATH):
        self.path = path
        self.version = VERSION

    def default_state(self):
        """State default v2.0.0. Migrasi = deep-merge dict ini ke data lama."""
        return {
            "game_version": VERSION,
            "coins": 2000,          # starter pack: cukup untuk 4 pull pertama
            "gems": 3,
            "roster": {},           # {nama: hero_dict}
            "party": [],            # list nama hero
            "inventory": {"Potion HP": 2, "Core": 0},
            "equip_bag": {},        # BARU v2.0.0: equipment lepas {uid: eq_dict}
            "equip_seq": 0,         # BARU v2.0.0: counter uid equipment
            "floors_cleared": 0,
            "free_gacha": 2,        # starter: 2 gacha gratis
            "pity": {},             # {target_star: attempt gagal beruntun}
            "battle_bag": [],       # Tas Battle: list nama item dibawa battle
            "settings": {"no_action_delay": False},  # pengaturan per-akun
            "total_synthesized": 0,  # Hero Synthesis: counter sintesis kumulatif
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    def save(self, state):
        """Simpan + auto backup 1 generasi (savegame.json.bak)."""
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    old = f.read()
                with open(self.path + ".bak", "w", encoding="utf-8") as f:
                    f.write(old)
        except Exception:
            pass  # backup gagal tidak boleh menggagalkan save
        state["game_version"] = self.version
        state["saved_at"] = datetime.now().isoformat(timespec="seconds")
        try:
            # Pastikan direktori saves/ ada (akun baru tanpa save lama)
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=1, ensure_ascii=False)
            return True
        except Exception as e:
            print("  ! Gagal menyimpan: %s" % e)
            return False

    def load(self):
        """Load + migrasi otomatis. Return (state, migrated: bool, msg).
        Save lama (1.0.0 ke bawah) tetap bisa dimainkan tanpa reset."""
        if not os.path.exists(self.path):
            st = self.default_state()
            return st, False, "Save baru dibuat."
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            # File korup: coba backup; kalau gagal, mulai fresh
            try:
                with open(self.path + ".bak", "r", encoding="utf-8") as f:
                    raw = json.load(f)
                print("  ! Save utama korup, dipulihkan dari .bak")
            except Exception:
                print("  ! Save korup (%s), memulai game baru." % e)
                return self.default_state(), False, "save korup"
        if not isinstance(raw, dict):
            raw = {}
        migrated = False
        old_ver = str(raw.get("game_version", "0.0.0"))
        if old_ver != self.version:
            migrated = True
        # Deep-merge default ke data lama: key hilang otomatis terisi default
        state = deep_merge(self.default_state(), raw if isinstance(raw, dict) else {})
        # ---------- Migrasi hero lama: ensure_fields ----------
        roster = state.get("roster")
        if not isinstance(roster, dict):
            state["roster"] = {}
            roster = state["roster"]
        fixed_roster = {}
        for name, hd in roster.items():
            try:
                if not isinstance(hd, dict):
                    continue
                hd = ensure_hero_fields(hd)   # isi field baru dg default
                fixed_roster[str(hd.get("name", name))] = hd
            except Exception:
                continue  # hero rusak di-skip, game tetap jalan
        state["roster"] = fixed_roster
        # ---------- Migrasi party lama: buang nama yang tidak ada ----------
        party = state.get("party")
        if not isinstance(party, list):
            state["party"] = []
        else:
            state["party"] = [str(n) for n in party
                              if isinstance(n, str) and n in state["roster"]]
        # inventory, pity, equip_bag harus dict (key baru v2.0.0 = fallback {})
        for key in ("inventory", "pity", "equip_bag"):
            if not isinstance(state.get(key), dict):
                state[key] = dict(self.default_state()[key]) if key == "inventory" else {}
        state["equip_seq"] = _safe_int(state.get("equip_seq"), 0)
        # coins/gems numeric
        state["coins"] = _safe_int(state.get("coins"), 2000)
        state["gems"] = _safe_int(state.get("gems"), 0)
        state["free_gacha"] = _safe_int(state.get("free_gacha"), 0)
        state["floors_cleared"] = _safe_int(state.get("floors_cleared"), 0)
        state["total_synthesized"] = max(0, _safe_int(state.get("total_synthesized"), 0))
        if migrated:
            print("  [MIGRASI] Savegame v%s dimigrasi ke v%s otomatis "
                  "(roster, progres lantai, dan inventaris dipertahankan)."
                  % (old_ver, self.version))
        # ---------- Migrasi lintas-versi (tanpa menghapus apa pun) ----------
        # v1.0.0/v2.0.0 menyimpan material promosi sebagai "StarFragment".
        # v2.2.0 memakai skema Soulstone: fragmen lama dikonversi setara
        # 1:1 menjadi Low Soulstone (material 1★->2★) agar progres tidak
        # hilang saat update.
        inv = state.get("inventory")
        if isinstance(inv, dict) and _safe_int(inv.get("StarFragment"), 0) > 0:
            n_frag = _safe_int(inv.pop("StarFragment"), 0)
            inv["Low Soulstone"] = _safe_int(inv.get("Low Soulstone"), 0) + n_frag
            print("  [MIGRASI] %d StarFragment -> %d Low Soulstone (skema material baru)."
                  % (n_frag, n_frag))
        # Versi dinaikkan segera: state di memori selalu representasi versi
        # sekarang, sehingga save berikutnya konsisten.
        state["game_version"] = self.version
        return state, migrated, "ok"


def deep_merge(default, old):
    """Deep-merge sederhana: nilai dari 'old' menang, tapi key yang hilang
    diisi dari 'default'. dict nested di-merge rekursif (untuk inventory)."""
    out = dict(default)
    for k, v in old.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _to_float(v, default=0.0):
    """Konversi float tahan kotor (save rusak tidak boleh crash)."""
    try:
        return float(v)
    except Exception:
        return default


def ensure_hero_fields(hd):
    """Migrasi 1 hero: field baru yang tidak ada di save lama diisi default
    (growth_multiplier, perks, skills, base_stats, growth_stats, mp_regen,
    equipment, alive, blueprints, dll)."""
    name = str(hd.get("name") or "Tanpa Nama")
    star = max(1, min(MAX_STAR, _safe_int(hd.get("star"), 1)))
    gm = float(hd.get("growth_multiplier", 1.0) or 1.0)
    hero_cls = hd.get("cls") or hd.get("class") or "Dealer"
    if hero_cls not in CLASSES:
        hero_cls = "Dealer"
    mig_rng = random.Random("pmu_hero_mig::" + name)
    raw_bs = hd.get("base_stats")
    if isinstance(raw_bs, (list, tuple)) and len(raw_bs) == 5:
        try:
            base_stats = [float(x) for x in raw_bs]
        except Exception:
            base_stats = list(roll_random_base_stats(hero_cls, star, mig_rng))
    else:
        base_stats = list(roll_random_base_stats(hero_cls, star, mig_rng))
    raw_gs = hd.get("growth_stats")
    if isinstance(raw_gs, (list, tuple)) and len(raw_gs) == 5:
        try:
            growth_stats = [float(x) for x in raw_gs]
        except Exception:
            growth_stats = list(roll_random_growth_stats(star, mig_rng))
    else:
        growth_stats = list(roll_random_growth_stats(star, mig_rng))
    raw_mpr = hd.get("mp_regen")
    mp_regen_val = _safe_int(raw_mpr, 0) if raw_mpr is not None else 0
    if mp_regen_val <= 0:
        mp_regen_val = roll_random_mp_regen(star, mig_rng)
    raw_skills = [s for s in (hd.get("skills") or []) if s in SKILLS]
    if not raw_skills:
        raw_skills = roll_random_skills(hero_cls, star, gm >= 1.5, mig_rng)
    raw_traits = hd.get("traits") if hd.get("traits") is not None else (hd.get("perks") or [])
    valid_traits = [p for p in raw_traits if p in PERKS]
    defaults = {
        "name": name,
        "star": star,
        "cls": hero_cls,
        "level": max(1, _safe_int(hd.get("level"), 1)),
        "xp": _safe_int(hd.get("xp"), 0),
        "growth_multiplier": gm,
        "traits": list(valid_traits),
        "perks": list(valid_traits),
        "skills": raw_skills,
        "base_stats": base_stats,
        "growth_stats": growth_stats,
        "mp_regen": mp_regen_val,
        "equipment": hd.get("equipment") or {"Senjata": None, "Zirah": None, "Aksesori": None},
        "alive": bool(hd.get("alive", True)),
        "hp": _safe_int(hd.get("hp"), 0),
        "blueprints": _safe_int(hd.get("blueprints"), 0),
        # Hero Synthesis (Tahap 1): default aman untuk save lama v2.2.0
        "sanity": 100.0,
        "ego": 50.0,
        "synth_count": 0,
        "absorbed_souls": 0,
    }
    out = dict(hd)
    for k, v in defaults.items():
        out.setdefault(k, v)   # setdefault = TIDAK menimpa nilai lama yang valid
    # Normalisasi field yang tipe-nya salah (mis. star string "3")
    out["star"] = defaults["star"]
    out["level"] = defaults["level"]
    out["growth_multiplier"] = defaults["growth_multiplier"]
    out["traits"] = defaults["traits"]
    out["perks"] = defaults["perks"]
    out["skills"] = defaults["skills"]
    out["base_stats"] = defaults["base_stats"]
    out["growth_stats"] = defaults["growth_stats"]
    out["mp_regen"] = defaults["mp_regen"]
    # Hero Synthesis: normalisasi tipe data (string "80" -> 80.0, korup -> default)
    # dengan klem ke rentang resmi: sanity 0-100, ego 10-100, counter >= 0.
    out["sanity"] = round(max(0.0, min(100.0, _to_float(out.get("sanity"), 100.0))), 1)
    out["ego"] = round(max(10.0, min(100.0, _to_float(out.get("ego"), 50.0))), 1)
    out["synth_count"] = max(0, _safe_int(out.get("synth_count"), 0))
    out["absorbed_souls"] = max(0, _safe_int(out.get("absorbed_souls"), 0))
    return out


# =============================== GAME ===============================
class Game:
    """Menu utama & orkestrasi semua system. State = dict serialisable
    (disimpan via SaveSystem), object Hero dibuat ulang saat load.
    Generator hero & gacha datang dari generate_hero.py; data dari SQLite."""

    def __init__(self, username="player"):
        # Pastikan database siap (idempotent — tidak pernah duplikat seed)
        dbs.init_db()
        self.username = username
        # SAVE PER-AKUN: setiap akun punya savegame sendiri di saves/.
        # Save lama single-file (versi < 2.2) dimigrasi SEKALI ke akun
        # pertama yang login, sehingga update tidak menghapus progres.
        acc_path = account_save_path(username)
        claim_legacy_save(username)   # tawarkan migrasi save lama (sekali)
        self.save = SaveSystem(path=acc_path)
        self.state, _, _ = self.save.load()
        # Jaring pengaman: salin database (termasuk accounts) tiap boot —
        # bila file db rusak/terhapus, akun bisa dipulihkan dari .bak.
        dbs.backup_db()
        self.apply_settings()   # terapkan pengaturan tersimpan (battle delay)
        self.gen = HeroGenerator()
        # Cache objek hero: roster() mengembalikan OBJEK YANG SAMA selama
        # sesi, sehingga mutasi (XP, luka, level, equipment, star) selalu
        # ter-serialisasi saat autosave — tidak ada perubahan yang hilang.
        self._hero_cache = {}
        self.gen.register_existing(self.load_roster_objects())
        self.gacha = GachaSystem(self.gen)
        self.party = Party()
        self.party.members = list(self.state.get("party") or [])

    # ------------------------- roster helpers -------------------------
    def load_roster_objects(self):
        out = {}
        for name, hd in self.state["roster"].items():
            h = self._hero_cache.get(name)
            if h is None:
                try:
                    h = Hero.from_dict(hd)
                except Exception:
                    continue
                self._hero_cache[name] = h
            out[name] = h
        return out

    def drop_hero_cache(self, name):
        """Hapus hero dari cache (saat mati permanen / diorban)."""
        self._hero_cache.pop(name, None)

    def roster(self):
        return self.load_roster_objects()

    def all_heroes(self):
        return list(self.roster().values())

    def sync_party(self):
        """Buang dari party hero yang sudah mati permanen / hilang."""
        r = self.roster()
        self.party.members = [n for n in self.party.members
                              if n in r and r[n].alive]
        self.state["party"] = list(self.party.members)

    def alive_party(self):
        r = self.roster()
        return [r[n] for n in self.party.members if n in r and r[n].alive]

    # ------------------------- pengaturan -------------------------
    def apply_settings(self):
        """Terapkan pengaturan tersimpan (per-akun) ke mode global battle.
        Dipanggil saat load & setiap kali toggle di menu Pengaturan."""
        global BATTLE_FAST
        st = self.state.get("settings") or {}
        BATTLE_FAST = bool(st.get("no_action_delay", False))

    def settings_menu(self):
        """Menu Pengaturan. Pengaturan tersimpan di savegame per-akun
        (settings.no_action_delay) dan otomatis ikut dimigrasi saat update
        (deep-merge default)."""
        while True:
            st = self.state.setdefault("settings", {})
            header("PENGATURAN (tersimpan per-akun)")
            cur = "AKTIF (tanpa jeda antar aksi)" if st.get("no_action_delay") \
                else "NORMAL (jeda %.1fs antar aksi)" % BATTLE_DELAY
            print("  Kecepatan battle : %s" % cur)
            print("  (jeda ganti ronde tetap ada di kedua mode)")
            print("\n  1. Toggle: Battle Tanpa Delay Antar Aksi")
            print("  0. Kembali")
            c = ask_choice("  Pilih > ", ["0", "1"])
            if c == "0":
                return
            if c == "1":
                st["no_action_delay"] = not st.get("no_action_delay", False)
                self.apply_settings()
                print("  Battle Tanpa Delay Antar Aksi: %s"
                      % ("AKTIF" if st["no_action_delay"] else "MATI"))
                self.autosave()

    # --------------------------- save ---------------------------
    def autosave(self):
        self.state["party"] = list(self.party.members)
        r = self.roster()
        self.state["roster"] = {n: h.to_dict() for n, h in r.items()}
        self.save.save(self.state)

    # --------------------------- utama (LOBBY) ---------------------------
    def auto_heal_lobby(self):
        """Fitur otomatis: setiap kali kembali ke Lobby, SEMUA hero pulih
        penuh — HP penuh DAN MP/mana penuh. Saat masuk battle berikutnya
        semua hero sudah membawa MP maksimal (permintaan user: mana tidak
        direset 0 lagi, tapi di-restore di Lobby)."""
        r = self.roster()
        restored = []
        for h in r.values():
            if h.alive and (h.hp < h.max_hp or h.mana < h.max_mp):
                restored.append(h.name)
        for h in r.values():
            if h.alive:
                h.refresh()
                h.mana = h.max_mp   # MP penuh saat masuk battle
        if restored:
            print("  [Lobby] %d hero ter-restore penuh (HP & MP): %s" % (
                len(restored), ", ".join(n[:20] for n in restored[:5]) +
                ("..." if len(restored) > 5 else "")))
        return len(restored)

    def battle_capacity(self):
        """Kapasitas Tas Battle = 2 x jumlah hero di party (maks party 5
        -> maks 10 item bawaan)."""
        return 2 * len(self.party.members)

    def run(self):
        header("PICK ME UP: INFINITE GACHA — AUTO-BATTLE RPG v%s" % VERSION)
        print("  Ketik nomor menu. Battle berjalan otomatis (auto-battle).")
        print("  PERINGATAN: hero yang gugur di battle MATI PERMANEN!")
        while True:
            # AUTO-HEAL: masuk/kembali ke Lobby memulihkan semua hero
            self.auto_heal_lobby()
            self.sync_party()
            r = self.roster()
            alive = [h for h in r.values() if h.alive]
            cap = self.battle_capacity()
            header("LOBBY")
            print("  Coins: %d   |   Gems: %d   |   Hero hidup: %d   |   Floor tertinggi: %d"
                  % (self.state["coins"], self.state["gems"], len(alive),
                     self.state["floors_cleared"]))
            print("  Party (%d/%d hero): %s" % (
                len(self.party.members), PARTY_MAX,
                ", ".join(self.party.members) if self.party.members else "(kosong!)"))
            print("  Tas Battle: %d/%d item terpasang" % (
                len(self.state.get("battle_bag", [])), cap))
            print("""
  1. Gacha               5. Floor Climbing (Tower)
  2. Manage Hero         6. Shop
  3. Inventory           7. Save  |  8. Exit
  4. Adventure / Hunt    9. Pengaturan""")
            c = ask_choice("  Pilih > ",
                           ["1", "2", "3", "4", "5", "6", "7", "8", "9"])
            if c == "1":
                self.gacha_menu()
            elif c == "2":
                self.manage_hero_menu()
            elif c == "3":
                self.inventory_menu()
            elif c == "4":
                self.adventure()
            elif c == "5":
                self.tower_menu()
            elif c == "6":
                self.shop_menu()
            elif c == "7":
                self.autosave()
                print("  Tersimpan ke %s" % self.save.path)
            elif c == "8":
                self.autosave()
                print("  Auto-save. Sampai jumpa, Master!")
                return
            elif c == "9":
                self.settings_menu()

    # ============================ GACHA ============================
    def gacha_menu(self):
        header("GACHA — TEMUKAN HERO BARU")
        print("  Setiap hero menyimpan potensinya sendiri — rawat dengan")
        print("  baik dan lihat akibatnya.")
        while True:
            print("\n  Coins: %d | Gems: %d | Gacha gratis: %d" % (
                self.state["coins"], self.state["gems"], self.state["free_gacha"]))
            print("  1. Gacha 1x (500 coins / 1 gem)")
            print("  2. Gacha 10x (4500 coins / 9 gem)")
            print("  3. Pakai gacha gratis (%d tersisa)" % self.state["free_gacha"])
            print("  0. Kembali")
            c = ask_choice("  Pilih > ", ["0", "1", "2", "3"])
            if c == "0":
                return
            if c == "1":
                self.do_gacha(1)
            elif c == "2":
                self.do_gacha(10)
            elif c == "3":
                if self.state["free_gacha"] <= 0:
                    print("  ! Tidak ada gacha gratis.")
                    continue
                self.state["free_gacha"] -= 1
                star = self.gacha.roll_star()
                h = self.gen.create(star)
                self.state["roster"][h.name] = h.to_dict()
                self.announce(h)
            self.autosave()

    def do_gacha(self, n):
        heroes, msgs = self.gacha.pull_multi(self.state, n)
        if heroes:
            print("\n  === HASIL %dx GACHA ===" % n)
            for h in heroes:
                self.announce(h)
        for m in msgs:
            print("  ! " + m)

    def announce(self, h):
        tag = {"Mage": " (!) MAGE LANGKA!", "Healer": " (healer)"}.get(h.cls, "")
        # RAHASIA: tidak ada penanda hidden potential maupun tier traits/skills
        # di hasil gacha — pemain hanya melihat nama trait & skill yang didapat.
        traits_list = getattr(h, "traits", None) or getattr(h, "perks", None) or []
        print("  [%s] %s %s%s | HP:%d ATK:%d DEF:%d SPD:%d | Traits: %s | Skills: %s" % (
            "*" * h.star, h.name, h.cls, tag,
            h.max_hp, h.atk, h.dfn, h.spd,
            ", ".join(traits_list) if traits_list else "-",
            ", ".join(h.skills) if getattr(h, "skills", None) else "-"))
        sleep(0.25)

    # ======================= MANAGE HERO (v2.0) =======================
    def manage_hero_menu(self):
        """SELURUH roster ditampilkan sekaligus (1,2,3,... TANPA pagination).
        0 = kembali. Pilih nomor -> submenu hero."""
        while True:
            r = self.roster()
            header("MANAGE HERO — ROSTER (%d hero, tanpa halaman)" % len(r))
            if not r:
                print("  (roster kosong — lakukan Gacha dulu)")
                return
            keys = sorted(r.keys())
            for i, name in enumerate(keys, 1):
                h = r[name]
                in_party = " [PARTY]" if name in self.party.members else ""
                print("  %3d. %-28s %s %-7s L%-3d %s%s" % (
                    i, name[:28], "*" * h.star, h.cls, h.level,
                    "HIDUP" if h.alive else "[GUGUR]", in_party))
            print("   0. Kembali | masukkan nomor hero untuk opsi lanjutan")
            c = ask_choice("  Pilih > ", ["0"] + [str(i) for i in range(1, len(keys) + 1)])
            if c == "0":
                return
            self.hero_menu(r[keys[int(c) - 1]])

    def hero_menu(self, h):
        """Submenu setelah memilih hero: 1. Detail  2. Tambah/Keluarkan party
        3. Kembali."""
        while True:
            if h.name not in self.roster():
                return   # hero sudah tiada (mis. tertelan Ego Override)
            print("\n  Hero: %s (%s %s)" % (h.name, "*" * h.star, h.cls))
            print("  1. Detail Hero")
            print("  2. %s" % ("Keluarkan dari Party" if h.name in self.party.members
                                  else "Tambah ke Party"))
            print("  3. Kembali")
            c = ask_choice("  Pilih > ", ["0", "1", "2", "3"])
            if c == "0" or c == "3":
                return
            if c == "1":
                self.hero_detail_menu(h)
            elif c == "2":
                if not h.alive:
                    print("  ! Hero yang gugur tidak bisa masuk party.")
                    continue
                if h.name in self.party.members:
                    self.party.remove(h.name)
                    print("  %s keluar dari party." % h.name)
                else:
                    ok, msg = self.party.add(h, self.roster())
                    print("  " + msg)
                self.autosave()

    def hero_detail_menu(self, h):
        """Layar Detail Hero: Stat, Kondisi Mental & Vessel, Traits, Skills,
        Equipment terpasang — plus opsi Ganti/Pasang/Lepas equipment,
        Promote Star, dan Synthesize Hero langsung dari layar ini."""
        while True:
            if h.name not in self.roster():
                return   # bila hero wadah tertelan Ego Override saat sintesis
            header("DETAIL HERO")
            for ln in h.detail_lines():
                print("  " + ln)
            # Detail tiap Trait milik hero (TANPA menampilkan tier — tier rahasia!)
            print("\n  Detail Traits Hero:")
            traits_list = getattr(h, "traits", None) or getattr(h, "perks", None) or []
            if traits_list:
                for idx_t, tr_name in enumerate(traits_list, 1):
                    t_info = TRAITS.get(tr_name)
                    if t_info:
                        print("   %d. %-18s : %s" % (idx_t, tr_name, t_info[1]))
                    else:
                        print("   %d. %s" % (idx_t, tr_name))
            else:
                print("   (tidak ada trait)")
            # Detail tiap Skill milik hero (TANPA menampilkan tier — tier rahasia!)
            print("\n  Detail Skill Hero:")
            if getattr(h, "skills", None):
                for idx_s, sk_name in enumerate(h.skills, 1):
                    sinfo = SKILLS.get(sk_name)
                    if sinfo:
                        eff_mp = h.skill_mp_cost(sinfo["mp_cost"]) if hasattr(h, "skill_mp_cost") else sinfo["mp_cost"]
                        origin = sinfo.get("cls", "Universal")
                        print("   %d. %-18s [%s | %d MP | CD %d] : %s" % (
                            idx_s, sk_name, origin, eff_mp,
                            sinfo["cd"], sinfo["description"]))
                    else:
                        print("   %d. %s" % (idx_s, sk_name))
            else:
                print("   (tidak ada skill)")
            print("\n  Equipment terpasang:")
            slots = list(h.equipment.keys())
            for i, s in enumerate(slots, 1):
                eq = h.equipment.get(s)
                print("   %d. %-9s: %s" % (i, s, eq.describe() if eq else "(kosong)"))
            print("\n  1. Ganti / Pasang Equipment        2. Lepas Equipment")
            print("  3. Promote Star (Soulstone/Book)   4. Synthesize Hero")
            print("  0. Kembali")
            c = ask_choice("  Pilih > ", ["0", "1", "2", "3", "4", "5"])
            if c == "0":
                return
            if c == "5":
                return
            if c == "1":
                self.equip_item_flow(h)
            elif c == "2":
                self.unequip_flow(h)
            elif c == "3":
                # Promote Star langsung untuk hero ini: cek kecukupan
                # material & coins di inventory sebelum bintang naik.
                self.promotion_menu(h)
            elif c == "4":
                self.synthesis_menu(hero=h)

    def equip_item_flow(self, hero):
        """Pilih slot -> pilih item dari equip_bag (inventory equipment) ->
        pasang. Item yang sebelumnya terpasang kembali ke bag."""
        bag = self.state.get("equip_bag", {})
        slots = list(hero.equipment.keys())
        sidx = ask_int("  Slot mana? (1-%d, 0=batal) > " % len(slots), 0, len(slots), 0)
        if sidx == 0:
            return
        slot = slots[sidx - 1]
        cands = [(uid, eq) for uid, eq in sorted(bag.items())
                 if isinstance(eq, dict) and eq.get("slot") == slot]
        if not cands:
            print("  ! Tidak ada %s di inventory. Dapatkan dari drop/Shop." % slot)
            return
        print("  %s tersedia di inventory:" % slot)
        for i, (uid, eq) in enumerate(cands, 1):
            e = Equipment.from_dict(eq)
            print("   %d. %s" % (i, e.describe()))
        idx = ask_int("  Pasang nomor? (0=batal) > ", 0, len(cands), 0)
        if idx == 0:
            return
        uid, eqd = cands[idx - 1]
        old = hero.equipment.get(slot)
        hero.equipment[slot] = Equipment.from_dict(eqd)
        del bag[uid]
        if old is not None:
            new_uid = str(self.state.get("equip_seq", 0) + 1)
            self.state["equip_seq"] = int(new_uid)
            bag[new_uid] = old.to_dict()
            print("  (%s lama dikembalikan ke inventory)" % slot)
        print("  >> Terpasang: %s" % hero.equipment[slot].describe())
        # HP clamp setelah stat berubah (equip HP mempengaruhi max_hp)
        hero.hp = min(hero.hp, hero.max_hp)
        self.autosave()

    def unequip_flow(self, hero):
        """Lepas equipment terpasang -> masuk equip_bag."""
        slots = [s for s, eq in hero.equipment.items() if eq is not None]
        if not slots:
            print("  ! Tidak ada equipment terpasang.")
            return
        for i, s in enumerate(slots, 1):
            print("   %d. %-9s: %s" % (i, s, hero.equipment[s].describe()))
        idx = ask_int("  Lepas nomor? (0=batal) > ", 0, len(slots), 0)
        if idx == 0:
            return
        slot = slots[idx - 1]
        eq = hero.equipment.get(slot)
        # Set None (jangan pop key!): slot harus tetap ada agar bisa
        # dipilih lagi di menu Ganti / Pasang Equipment.
        hero.equipment[slot] = None
        bag = self.state.setdefault("equip_bag", {})
        uid = str(self.state.get("equip_seq", 0) + 1)
        self.state["equip_seq"] = int(uid)
        bag[uid] = eq.to_dict()
        hero.hp = min(hero.hp, hero.max_hp)
        print("  %s dilepas & masuk inventory." % eq.describe())
        self.autosave()

    # ======================= INVENTORY (v2.0) =======================
    def inventory_menu(self):
        """SELURUH item (equipment di bag + consumable/material) tampil
        sekaligus dengan nomor iterasi, TANPA pagination. 0 = kembali.
        Pilih nomor -> Deskripsi & Stat Bonus -> 1. Pakai  2. Buang  3. Kembali."""
        while True:
            bag = self.state.get("equip_bag", {})
            inv = self.state.get("inventory", {})
            header("INVENTORY (semua item, tanpa halaman)")
            entries = []  # (label_tampilan, jenis, payload)
            for uid, eqd in sorted(bag.items(), key=lambda kv: _safe_int(kv[0])):
                e = Equipment.from_dict(eqd)
                entries.append(("eq", uid, e))
            for nm, cnt in sorted(inv.items()):
                if cnt and cnt > 0:
                    entries.append(("item", nm, cnt))
            if not entries:
                print("  (inventory kosong)")
                return
            for i, (kind, a, b) in enumerate(entries, 1):
                if kind == "eq":
                    print("  %3d. [EQUIP] %s" % (i, b.describe()))
                else:
                    print("  %3d. [x%-2d ] %s" % (i, b, a))
            bag = self.state.get("battle_bag", [])
            print("\n  Tas Battle: %d/%d item bawaan — %s" % (
                len(bag), self.battle_capacity(), ", ".join(bag) or "kosong"))
            print("   0. Kembali  |  T. Kelola Tas Battle  |  nomor = detail item")
            c = ask_choice("  Pilih > ",
                           ["0", "T", "t"] + [str(i) for i in range(1, len(entries) + 1)])
            if c == "0":
                return
            if c in ("T", "t"):
                self.battle_bag_flow()
                continue
            kind, a, b = entries[int(c) - 1]
            if kind == "eq":
                self.item_detail_flow(("eq", a, b))
            else:
                self.item_detail_flow(("item", a, b))

    def item_detail_flow(self, entry):
        """Detail item + aksi: 1. Pakai/Pasangkan  2. Buang  3. Kembali."""
        kind, a, b = entry
        while True:
            if kind == "eq":
                e = b
                print("\n  === DETAIL ITEM ===")
                print("  Nama    : %s" % e.name)
                print("  Jenis   : Equipment %s" % e.slot)
                print("  Tier    : %s (T%d)" % (TIER_LABEL.get(e.tier, "?"), e.tier))
                print("  Stat    : %s" % (e.describe().split("] ", 1)[-1]))
                print("  Deskripsi: Equipment drop battle / Shop. Dipasang ke hero")
                print("             lewat Manage Hero -> Detail Hero -> Ganti Equipment.")
                acts = ["1", "2", "3"]
                print("\n  1. Pakai / Pasangkan ke hero")
                print("  2. Buang (Trash)")
                print("  3. Kembali")
                c = ask_choice("  Pilih > ", acts)
                if c == "1":
                    self.equip_from_bag(a, e)
                    return  # kembali ke inventory (list sudah berubah)
                if c == "2":
                    if ask_choice("  Yakin buang %s? (y/n) > " % e.name, ["y", "n"]) == "y":
                        del self.state["equip_bag"][a]
                        print("  %s dibuang." % e.name)
                        self.autosave()
                        return
                elif c == "3":
                    return
            else:
                nm, cnt = a, b
                desc = ITEM_DESCS.get(nm, "Item.")
                print("\n  === DETAIL ITEM ===")
                print("  Nama    : %s (x%d)" % (nm, cnt))
                print("  Deskripsi: %s" % desc)
                opts = ["1", "2", "3"]
                if nm in dbs.CRAFT_RECIPES:
                    mat, qty = dbs.CRAFT_RECIPES[nm]
                    print("  Craft   : %dx %s -> 1x %s" % (qty, nm, mat))
                    opts.append("4")
                print("\n  1. Pakai")
                print("  2. Buang (Trash)")
                print("  3. Kembali")
                if "4" in opts:
                    print("  4. Craft Material")
                c = ask_choice("  Pilih > ", opts)
                if c == "1":
                    self.use_consumable(nm)
                    return
                if c == "2":
                    if ask_choice("  Yakin buang %d x %s? (y/n) > " % (cnt, nm), ["y", "n"]) == "y":
                        self.state["inventory"][nm] = 0
                        print("  %s dibuang semua." % nm)
                        self.autosave()
                        return
                elif c == "3":
                    return
                elif c == "4":
                    self.craft_menu()
                    return  # stok berubah -> daftar inventory dibangun ulang

    def equip_from_bag(self, uid, eq):
        """Pakai equipment dari inventory: pilih hero target -> pasang ke slot."""
        r = self.roster()
        cands = [h for h in sorted(r.values(), key=lambda x: x.name) if h.alive]
        if not cands:
            print("  ! Tidak ada hero hidup.")
            return
        print("  Pasang %s ke hero:" % eq.describe())
        for i, h in enumerate(cands, 1):
            print("   %d. %-28s %s %s" % (i, h.name[:28], "*" * h.star, h.cls))
        idx = ask_int("  Hero nomor? (0=batal) > ", 0, len(cands), 0)
        if idx == 0:
            return
        hero = cands[idx - 1]
        slot = eq.slot
        old = hero.equipment.get(slot)
        hero.equipment[slot] = eq
        del self.state["equip_bag"][uid]
        if old is not None:
            new_uid = str(self.state.get("equip_seq", 0) + 1)
            self.state["equip_seq"] = int(new_uid)
            self.state.setdefault("equip_bag", {})[new_uid] = old.to_dict()
        hero.hp = min(hero.hp, hero.max_hp)
        print("  >> %s dipasangkan ke %s." % (eq.name, hero.name))
        self.autosave()

    def use_consumable(self, nm):
        """Gunakan item consumable (saat ini: Potion HP)."""
        inv = self.state["inventory"]
        if nm == "Potion HP":
            r = self.roster()
            wounded = [h for h in sorted(r.values(), key=lambda x: x.name)
                       if h.alive and h.hp < h.max_hp]
            if not wounded:
                print("  ! Semua hero dalam kondisi prima.")
                return
            for i, h in enumerate(wounded, 1):
                print("   %d. %-28s %s" % (i, h.name[:28], bar(h.hp, h.max_hp)))
            idx = ask_int("  Potion untuk hero nomor? (0=batal) > ", 0, len(wounded), 0)
            if idx == 0:
                return
            if _safe_int(inv.get(nm), 0) <= 0:
                print("  ! %s habis." % nm)
                return
            h = wounded[idx - 1]
            inv[nm] = _safe_int(inv.get(nm), 0) - 1
            h.hp = min(h.max_hp, h.hp + h.max_hp // 2)
            print("  %s meminum Potion HP. %s" % (h.name, bar(h.hp, h.max_hp)))
        else:
            print("  ! %s tidak bisa dipakai langsung (material/ticket)." % nm)
            return
        self.autosave()

    # ======================= BATTLE WRAPPER =======================
    def pre_battle_check(self):
        """Pastikan party hidup ada sebelum battle. Return list hero atau None."""
        self.sync_party()
        heroes = self.alive_party()
        if not heroes:
            print("  ! Tidak ada hero hidup di party! Isi party dulu / heal.")
            return None
        return heroes

    def cleanup_after_battle(self, heroes):
        """Setelah battle: buang hero mati permanen dari roster & party."""
        r = self.roster()
        dead = [h.name for h in heroes if not h.alive]
        for n in dead:
            self.state["roster"].pop(n, None)
            self.drop_hero_cache(n)
        self.sync_party()
        return dead

    def sacrifice_hero_cleanup(self, hero_name, salvage_equip=True):
        """Hero Synthesis (Tahap 1): hapus PERMANEN hero tumbal dari game.
        Langkah: (1) lepas semua equipment -> kembali ke equip_bag (bila
        salvage_equip=True; slot di-set None — JANGAN .pop() key slot, gotcha
        seksi 16: key slot hilang tidak bisa dipilih lagi di menu Ganti/Pasang);
        (2) keluarkan dari Party; (3) pop dari roster + drop_hero_cache agar
        identity map Game._hero_cache tetap sinkron (gotcha seksi 12);
        (4) sinkronkan gen.register_existing bila gen tersedia.
        Return dict ringkasan: {'found', 'salvaged', 'removed_from_party'}."""
        summary = {"found": False, "salvaged": 0, "removed_from_party": False}
        r = self.roster()
        hero = r.get(hero_name)
        if hero is None:
            return summary   # hero tidak ada — diam-diam, tidak crash
        summary["found"] = True
        # 1) Salvage equipment terpasang -> equip_bag (slot = None, bukan pop!)
        if salvage_equip:
            bag = self.state.setdefault("equip_bag", {})
            for slot, eq in list(hero.equipment.items()):
                if eq is not None:
                    uid = str(self.state.get("equip_seq", 0) + 1)
                    self.state["equip_seq"] = int(uid)
                    bag[uid] = eq.to_dict()
                    hero.equipment[slot] = None   # set None, JANGAN pop key
                    summary["salvaged"] += 1
        # 2) Keluarkan dari Party bila ada
        if hero_name in self.party.members:
            self.party.remove(hero_name)
            self.state["party"] = list(self.party.members)
            summary["removed_from_party"] = True
        # 3) Hapus dari roster + identity map (WAJIB keduanya)
        self.state["roster"].pop(hero_name, None)
        self.drop_hero_cache(hero_name)
        # 4) Sinkronkan generator: nama & fingerprint tumbal bebas dipakai lagi
        if getattr(self, "gen", None) is not None:
            try:
                self.gen.names.discard(hero_name)
                self.gen.fingerprints = set()
                self.gen.names = set()
                self.gen.register_existing(self.roster())
            except Exception:
                pass   # tidak boleh menggagalkan penghapusan
        return summary

    def post_battle_events(self, mode, heroes):
        """HIDDEN BOSS EVENT (Emergency Raid): peluang 15% setelah battle
        Adventure/Tower. Opsi kabur hanya SEBELUM battle (loss 10% coins);
        jika memilih FIGHT, tidak bisa kabur di tengah pertempuran."""
        if random.random() >= HIDDEN_BOSS_CHANCE:
            return
        heroes = [h for h in heroes if h.alive]
        if not heroes:
            return
        header("!!! HIDDEN BOSS MUNCUL (EMERGENCY RAID) !!!")
        boss = Enemy.make(level=int(self.party.avg_level(self.roster())) + 3,
                          mode="hidden", boss=True)
        print("  %s (Level %d) menghalangi jalan pulang!" % (boss.name, boss.level))
        print("  1. FIGHT  (risk permadeath tinggi, drop Gem/Core langka,")
        print("             setelah dipilih TIDAK BISA kabur sampai battle selesai)")
        print("  2. ESCAPE (kehilangan %d%% coins — opsi terakhir sebelum battle)" %
              int(HIDDEN_ESCAPE_LOSS * 100))
        c = ask_choice("  Pilih > ", ["1", "2"])
        if c == "2":
            lost = int(self.state["coins"] * HIDDEN_ESCAPE_LOSS)
            self.state["coins"] -= lost
            print("  Kamu kabur. Kehilangan %d coins." % lost)
            return
        print("  (!) Pertarungan sampai satu pihak tumbang. TIDAK ADA KABUR.")
        eng = BattleEngine(heroes, [boss], can_escape=False,
                           battle_items=self.battle_bag())
        res = eng.run()
        if res == "win":
            self.state["gems"] += random.randint(1, 2)
            if random.random() < 0.60:
                self.state["inventory"]["Core"] = _safe_int(
                    self.state["inventory"].get("Core"), 0) + 1
                print("  + 1 Core (material langka)!")
            # Book of Oath/Fate dari Hidden Boss TINGKAT TINGGI (party L60+).
            # Sangat-sangat langka (0.1%-1%) dan TIDAK dapat di-craft.
            avg_lvl = int(self.party.avg_level(self.roster()))
            if avg_lvl >= 60:
                if random.random() < 0.01:
                    self.state["inventory"]["Book of Fate"] = \
                        _safe_int(self.state["inventory"].get("Book of Fate"), 0) + 1
                    print("  + 1 BOOK OF FATE! (Hidden Boss tinggi, 1%)")
                elif random.random() < 0.005:
                    self.state["inventory"]["Book of Oath"] = \
                        _safe_int(self.state["inventory"].get("Book of Oath"), 0) + 1
                    print("  + 1 BOOK OF OATH! (Hidden Boss tinggi, 0.5%)")
            bonus = 200 * max(1, boss.level // 2)
            self.state["coins"] += bonus
            print("  + 1-2 Gems, +%d coins" % bonus)
        else:
            print("  ...Party gagal melawan Hidden Boss.")

    # ========================= ADVENTURE (SESI) =========================
    # Tabel encounter Adventure (total 100%) — RAHASIA: persentase tidak
    # pernah ditampilkan ke pemain, hanya dipakai internal untuk roll.
    ENC_TABLE = [("hidden", 5),    # 5% Hidden Boss (lebih langka dari high)
                 ("high", 10),     # 10% High Level Monster
                 ("normal", 50),   # 50% Monster level rata-rata party
                 ("low", 35)]      # 35% Low Level Monster
    ENC_LABEL = {"hidden": "HIDDEN BOSS", "high": "HIGH LEVEL MONSTER",
                 "normal": "MONSTER STANDAR", "low": "MONSTER LEMAH"}

    def adventure(self):
        """Sesi Adventure dengan PELUANG ENCOUNTER: tiap pencarian musuh
        di-roll dari tabel 5% Hidden Boss / 10% High Level / 50% Standar
        (level party) / 35% Low Level. BANYAK monster ACAK 1-3 (tidak ada
        angka pasti per jenis). Info musuh (nama, level, HP) selalu
        ditampilkan dengan opsi 1. Lawan, 2. Cari lawan lain, 3. Kabur.
        Menang -> reward -> TETAP di adventure (encounter berikutnya)."""
        while True:   # sesi adventure — keluar hanya lewat opsi Kabur / kalah
            heroes = self.pre_battle_check()
            if not heroes:
                return
            avg = max(1, int(round(self.party.avg_level(self.roster()))))
            kind = weighted_choice(self.ENC_TABLE)
            # Jumlah monster benar-benar acak 1-3 untuk SEMUA jenis
            n = random.randint(1, 3)
            if kind == "hidden":
                lev = avg + 1
                enemies = [Enemy.make(level=lev, mode="hidden", boss=True)]
            elif kind == "high":
                lev = avg + random.randint(2, 4)   # di atas level party
                enemies = [Enemy.make(level=lev, mode="adventure")
                           for _ in range(n)]
            elif kind == "low":
                lev = max(1, avg - random.randint(1, 3))   # di bawah party
                enemies = [Enemy.make(level=lev, mode="adventure")
                           for _ in range(n)]
            else:   # normal: level rata-rata party
                lev = avg
                enemies = [Enemy.make(level=lev, mode="adventure")
                           for _ in range(n)]
            header("ADVENTURE — Encounter: %s" % self.ENC_LABEL[kind])
            # Info lengkap musuh sebelum memutuskan
            print("  Party: %s" % ", ".join(
                "%s L%d (%d/%d HP)" % (h.name[:14], h.level, h.hp, h.max_hp)
                for h in heroes))
            print("  Musuh ditemukan (%d unit):" % len(enemies))
            for e in enemies:
                tag = " [BOSS]" if e.boss else (" [ELITE]" if e.elite else "")
                print("   - %-22s Level %-3d HP %d%s" % (
                    e.name[:22], e.level, e.max_hp, tag))
            print("  Total HP musuh: %d" % sum(e.max_hp for e in enemies))
            print("\n  1. Lawan    2. Cari lawan lain    3. Kabur (kembali ke Lobby)")
            c = ask_choice("  Pilih > ", ["1", "2", "3"])
            if c == "2":
                print("  ~ Mencari lawan lain... ~")
                continue
            if c == "3":
                print("  ~ Kamu meninggalkan Adventure dan kembali ke Lobby. ~")
                return
            # Opsi 1: Lawan. Keputusan kabur SUDAH diambil di menu ini —
            # di dalam battle tidak ada kabur (aturan sama dengan Tower).
            eng = BattleEngine(heroes, enemies, can_escape=False,
                               battle_items=self.battle_bag())
            res = eng.run()
            dead = self.cleanup_after_battle(heroes)
            if dead:
                print("  !! Hero gugur permanen: %s" % ", ".join(dead))
            if res == "win":
                # MENANG: reward lalu TETAP di adventure (encounter berikutnya)
                self.reward_adventure(heroes, enemies, lev)
                if kind == "hidden":
                    self.state["gems"] += 1
                    print("  + 1 Gem (mengalahkan HIDDEN BOSS di Adventure!)")
                self.autosave()
                if not self.alive_party():
                    print("  ! Tidak ada hero hidup tersisa. Adventure berakhir.")
                    return
                print("  ~ Adventure berlanjut... mencari musuh berikutnya. ~")
                continue
            # KALAH: party tumbang -> sesi berakhir paksa
            self.autosave()
            print("  Adventure berakhir. Kembali ke Lobby...")
            return

    def recover_party_sanity(self, heroes, amount=5.0):
        """Pulihkan sanity hero party yang hidup usai memenangkan battle."""
        healed = 0
        for h in heroes:
            if h.alive and getattr(h, "sanity", 100.0) < 100.0:
                h.sanity = min(100.0, round(float(h.sanity) + float(amount), 1))
                healed += 1
        if healed > 0:
            print("  ~ Ketegangan jiwa mereda: kondisi mental %d hero membaik." % healed)
        return healed

    def reward_adventure(self, heroes, enemies, lev):
        """Reward menang Adventure: XP (36 x lev), coins 35 x lev,
        drop Potion 30%, drop Equipment 8% (masuk inventory), + pulih sanity."""
        xp_each = 36 * max(1, lev)
        coins = 35 * max(1, lev)
        print("\n  === REWARD ===")
        for h in heroes:
            if h.alive:
                ups = h.gain_xp(xp_each)
                msg = ("  + %s: %d XP" % (h.name, xp_each))
                if ups:
                    msg += "  << LEVEL UP -> L%d!" % h.level
                    h.refresh()
                print(msg)
        self.recover_party_sanity(heroes, 5.0)
        self.state["coins"] += coins
        print("  + %d coins" % coins)
        # Drop potion 30%
        if random.random() < 0.30:
            n = random.randint(1, 2)
            inv = self.state["inventory"]
            inv["Potion HP"] = min(5, _safe_int(inv.get("Potion HP"), 0) + n)
            print("  + %d Potion HP" % n)
        # Drop equipment 8% -> masuk equip_bag (dipasang lewat menu Inventory)
        if random.random() < 0.08:
            eq = Equipment.random()
            self.add_equipment_to_bag(eq)
            print("  + EQUIPMENT: %s (masuk Inventory)" % eq.describe())
        sleep(BATTLE_DELAY)

    def add_equipment_to_bag(self, eq):
        """Simpan equipment ke equip_bag (inventory) dengan uid baru."""
        bag = self.state.setdefault("equip_bag", {})
        uid = str(self.state.get("equip_seq", 0) + 1)
        self.state["equip_seq"] = int(uid)
        bag[uid] = eq.to_dict()
        return uid

    # ====================== FLOOR CLIMBING ======================
    def tower_menu(self):
        while True:
            header("FLOOR CLIMBING — TOWER OF TRIALS")
            f = max(1, _safe_int(self.state.get("floors_cleared"), 0) + 1)
            # Rekomendasi party = level musuh lantai - 2 (supaya jujur;
            # level musuh tower dihitung di tower_floor: 2*F).
            rec = max(1, 2 * f - 2)
            print("  Lantai berikutnya: %d (rekomendasi party L%d)" % (f, rec))
            print("  REWARD: Raw Boss Material & Soulstone (material promosi),")
            print("  Gems, equipment langka. Lantai clear BISA diulang (farm).")
            print("  PERINGATAN: TIDAK ADA KABUR di Tower. Permadeath aktif!")
            print("\n  1. Masuk lantai berikutnya   2. Ulangi lantai (farm)")
            print("  3. Promosi bintang (Soulstone/Book)   4. Craft Material")
            print("  5. Synthesis Chamber                  0. Kembali")
            c = ask_choice("  Pilih > ", ["0", "1", "2", "3", "4", "5"])
            if c == "0":
                return
            if c in ("1", "2"):
                cleared = _safe_int(self.state.get("floors_cleared"), 0)
                if c == "2":
                    # Farm lantai lama; validasi input agar tidak infinite loop
                    if cleared < 1:
                        print("  ! Belum ada lantai yang ter-clear untuk diulang.")
                        continue
                    cf = ask_int("  Ulangi lantai berapa? (1-%d) > " % cleared, 1, cleared, cleared)
                else:
                    cf = f
                self.tower_floor(cf, first_clear=(c == "1"))
            elif c == "3":
                self.promotion_menu()
            elif c == "4":
                self.craft_menu()
            elif c == "5":
                self.synthesis_menu()

    def tower_floor(self, floor, first_clear=False):
        """NO ESCAPE: begitu konfirmasi masuk, pertempuran WAJIB berakhir
        Victory atau Total Party Permadeath. can_escape=False absolut."""
        heroes = self.pre_battle_check()
        if not heroes:
            return
        # Level musuh tower:
        #   lantai biasa  = 2 x floor (F2 -> L4, F3 -> L6)
        #   BOSS floor (kelipatan 5) = boss 3 x floor + 2 minion 2 x floor
        #   (permintaan user: boss lebih menakutkan, minion tetap 2F)
        is_boss_floor = (floor % 5 == 0)
        if is_boss_floor:
            lev = max(1, 3 * floor)          # level BOSS
        else:
            lev = max(1, 2 * floor)          # level musuh biasa
        header("TOWER FLOOR %d%s — Musuh L%d" % (floor, " [BOSS]" if is_boss_floor else "", lev))
        print("  (!) TIDAK ADA OPSI KABUR. Battle hanya selesai jika satu")
        print("      pihak tumbang total. Hero gugur = mati permanen.")
        enemies = []
        if is_boss_floor:
            # Boss (3xF) + 2 minion (2xF) di kelipatan 5; boss HP lebih besar
            enemies.append(Enemy.make(level=lev, mode="tower", boss=True))
            enemies += [Enemy.make(level=max(1, 2 * floor), mode="tower")
                        for _ in range(2)]
        else:
            enemies = [Enemy.make(level=lev, mode="tower") for _ in range(3)]
        for e in enemies:
            print("  - %s (L%d%s)" % (e.name, e.level, " [BOSS]" if e.boss else ""))
        eng = BattleEngine(heroes, enemies, can_escape=False,
                           battle_items=self.battle_bag())
        res = eng.run()
        if res == "win":
            self.reward_tower(heroes, floor, first_clear)
            if first_clear and floor > _safe_int(self.state.get("floors_cleared"), 0):
                self.state["floors_cleared"] = floor
        else:
            print("  Tower menelanmu... (progress floor dipertahankan)")
        dead = self.cleanup_after_battle(heroes)
        if dead:
            print("  !! Hero gugur permanen: %s" % ", ".join(dead))
        # Hidden boss event juga bisa muncul di tower (setelah clear)
        if res == "win":
            self.post_battle_events("tower", heroes)
        self.autosave()

    def reward_tower(self, heroes, floor, first_clear):
        """Reward tower v2.2: Raw Boss Material dari boss floor (kelipatan 5,
        drop ~5%, dipastikan minimal 1 per clear boss), coins, gem, equipment.
        Book of Oath/Fate: END-GAME, HANYA boss floor 80+ (0.5%/1%) dan
        Hidden Boss tingkat tinggi (party rata-rata L60+)."""
        lev_f = max(1, 2 * floor)   # level musuh lantai ini
        coins = 35 * lev_f
        print("\n  === FLOOR %d CLEAR! ===" % floor)
        inv = self.state["inventory"]
        # ---- Raw Boss Material (boss floor kelipatan 5) ----
        if floor % 5 == 0:
            # Material yang cocok untuk rentang lantai ini
            if floor < 10:
                raw = "Stone Vessel"
            elif floor < 20:
                raw = "Spirit Ore"
            elif floor < 40:
                raw = "Runic Core"
            else:
                raw = "Ectoplasm Crystal"
            # Drop rate murni 5% — raw material memang langka; progres
            # crafting bergantung keberuntungan farming boss floor.
            if random.random() < 0.05:
                inv[raw] = _safe_int(inv.get(raw), 0) + 1
                print("  + %s (raw boss material, 5%%!)" % raw)
        # ---- Book of Oath / Fate: HANYA floor 80+, sangat-sangat langka ----
        if floor >= 80:
            if random.random() < 0.01:
                inv["Book of Fate"] = _safe_int(inv.get("Book of Fate"), 0) + 1
                print("  + 1 BOOK OF FATE! (1% — material 6★→7★)")
            elif random.random() < 0.005:
                inv["Book of Oath"] = _safe_int(inv.get("Book of Oath"), 0) + 1
                print("  + 1 BOOK OF OATH! (0.5% — material 5★→6★)")
        self.state["coins"] += coins
        print("  + %d coins" % coins)
        # XP tower (x3 per GDD), berbasis level musuh lantai
        xp_each = 36 * lev_f
        for h in heroes:
            if h.alive:
                ups = h.gain_xp(xp_each)
                if ups:
                    print("  + %s LEVEL UP -> L%d!" % (h.name, h.level))
                    h.refresh()
        self.recover_party_sanity(heroes, 5.0)
        # Gem: dijamin di F%5, 12% selainnya
        if floor % 5 == 0:
            self.state["gems"] += 1
            print("  + 1 Gem (jaminan boss floor)")
        elif random.random() < 0.12:
            self.state["gems"] += 1
            print("  + 1 Gem")
        # Equipment rare: 55% di F%5, 100% epic di F%10 -> masuk Inventory
        if floor % 10 == 0:
            eq = Equipment.random(tier=random.choice([3, 4, 5]))
            self.add_equipment_to_bag(eq)
            print("  + EQUIPMENT EPIC: %s (masuk Inventory)" % eq.describe())
        elif floor % 5 == 0 and random.random() < 0.55:
            eq = Equipment.random(tier=random.choice([3, 4]))
            self.add_equipment_to_bag(eq)
            print("  + Equipment Rare: %s (masuk Inventory)" % eq.describe())
        if floor % 10 == 0:
            inv["Core"] = _safe_int(inv.get("Core"), 0) + 1
            print("  + 1 Core (material epic+)")
        sleep(BATTLE_DELAY)

    # ==================== PROMOSI BINTANG (1->7) ====================
    def promotion_menu(self, hero=None):
        """Star promotion v2.2 (skema Soul & Essence): tiap tier butuh
        material spesifik (Low/Intermediate/High Soulstone, Perfect Soul
        Essence, Book of Oath, Book of Fate) + coins. Success rate + pity.
        hero=None -> pilih sendiri dari menu (Tower); hero diberikan ->
        promosi langsung hero tersebut (dari layar Detail Hero)."""
        header("PROMOSI BINTANG (1S -> 7S) — SOUL & ESSENCE")
        inv = self.state["inventory"]
        r = self.roster()
        print("  Coins: %d" % self.state["coins"])
        print("  Material di inventory:")
        for s, (mat, qty, cost, rate) in sorted(PROMO_TABLE.items()):
            have = _safe_int(inv.get(mat), 0)
            print("   ->%dS: %dx %s (punya %d) | %d coins | %d%%" % (
                s, qty, mat, have, cost, int(rate * 100)))
        # Mode A: hero sudah ditentukan (dari Detail Hero) -> target = star+1
        # Mode B: hero=None -> tanya target lalu pilih hero dari daftar
        if hero is not None:
            if hero.star >= MAX_STAR:
                print("  ! %s sudah mencapai %d-star (maksimum)." % (hero.name, MAX_STAR))
                return
            target = hero.star + 1
            print("  Hero: %s (%s) -> menuju %d-star" % (
                hero.name, "*" * hero.star, target))
        else:
            target = ask_int("  Naik ke star berapa? (2-7, 0=batal) > ", 0, MAX_STAR, 0)
            if target == 0:
                return
        mat_need, qty_need, coin_need, base_rate = PROMO_TABLE[target]
        if hero is None:
            cands = [h for h in sorted(r.values(), key=lambda x: x.name)
                     if h.alive and h.star == target - 1]
            if not cands:
                print("  ! Tidak ada hero hidup %d-star untuk dipromosikan." % (target - 1))
                return
            for i, h in enumerate(cands, 1):
                print("   %d. %-30s %s %s L%d" % (i, h.name[:30], "*" * h.star, h.cls, h.level))
            idx = ask_int("  Pilih hero (0=batal) > ", 0, len(cands), 0)
            if idx == 0:
                return
            hero = cands[idx - 1]
        # Cek kecukupan MATERIAL & coins SEBELUM menaikkan bintang
        if _safe_int(inv.get(mat_need), 0) < qty_need:
            print("  ! Material kurang: butuh %dx %s (punya %d)."
                  % (qty_need, mat_need, _safe_int(inv.get(mat_need), 0)))
            print("    Dapatkan dari Boss Floor (kelipatan 5) lalu craft di menu Tower/Inventory.")
            return
        if self.state["coins"] < coin_need:
            print("  ! Coins kurang (butuh %d)." % coin_need)
            return
        # Sacrifice: pilih hero LAIN (tier tinggi saja; 2★/3★ bebas biaya hero)
        sacs = []
        if target >= 4:
            sac_need = target - 3   # 4S->1, 5S->2, 6S->3, 7S->4 hero sacrifice
            for _ in range(sac_need):
                others = [h2 for h2 in sorted(r.values(), key=lambda x: x.name)
                          if h2.alive and h2 is not hero
                          and h2.name not in [s.name for s in sacs]]
                if not others:
                    print("  ! Tidak ada hero lain untuk dishacrifice."); return
                for i, h2 in enumerate(others[:12], 1):
                    print("   s%d. %-30s %s %s L%d" % (i, h2.name[:30], "*" * h2.star,
                                                       h2.cls, h2.level))
                sidx = ask_int("  Sacrifice #%d (0=batal) > " % (len(sacs) + 1),
                               0, min(12, len(others)), 0)
                if sidx == 0:
                    return
                sacs.append(others[sidx - 1])
        # Pity system: gagal beruntun +5% (cap 95%)
        pity = _safe_int(self.state.get("pity", {}).get(str(target)), 0)
        rate = min(0.95, base_rate + 0.05 * pity)
        print("  Biaya: %dx %s, %d coins%s | Sukses: %.0f%%" % (
            qty_need, mat_need, coin_need,
            (", %d sacrifice" % len(sacs)) if sacs else "", rate * 100))
        if ask_choice("  Lanjut? (y/n) > ", ["y", "n"]) == "n":
            return
        inv[mat_need] = _safe_int(inv.get(mat_need), 0) - qty_need
        self.state["coins"] -= coin_need
        for s in sacs:
            # Sacrifice DIHANCURKAN permanen (permadeath economy)
            self.state["roster"].pop(s.name, None)
            self.drop_hero_cache(s.name)
            self.party.remove(s.name)
            print("  %s telah diorban..." % s.name)
        if random.random() < rate:
            if hasattr(hero, "promote_star"):
                hero.promote_star(target)
            else:
                hero.star = target
                hero.refresh()
            self.state["pity"][str(target)] = 0
            print("  *** SUKSES! %s kini %s! Batas stat & rise-rate meningkat. ***" % (
                hero.name, "*" * target))
        else:
            self.state["pity"][str(target)] = pity + 1
            print("  ...GAGAL. Material & sacrifice hilang, coins -50%%. Pity +%d%%." %
                  (5 * (pity + 1)))
            self.state["coins"] = int(self.state["coins"] * 0.5)
        self.autosave()

    # ==================== HERO SYNTHESIS CHAMBER ====================
    def synthesis_menu(self, hero=None):
        """Synthesis Chamber: menyatukan Hero Wadah (Base) dengan Hero Tumbal
        (Material). Tumbal lenyap permanen (equipment diselamatkan ke equip_bag).
        RAHASIA: DILARANG menampilkan persentase peluang, angka GM, nilai ego,
        maupun tier dari Trait/Skill di layar ini."""
        header("SYNTHESIS CHAMBER — PENYATUAN JIWA")
        r = self.roster()
        alive_heroes = [h for h in sorted(r.values(), key=lambda x: x.name) if h.alive]
        if len(alive_heroes) < 2:
            print("  ! Butuh minimal 2 hero hidup di roster untuk memasuki Synthesis Chamber.")
            return

        # 1) Tentukan Hero Wadah (Base)
        if hero is not None:
            if not hero.alive or hero.name not in r:
                print("  ! Hero wadah tidak valid atau sudah gugur.")
                return
            base_hero = r[hero.name]
        else:
            print("  Pilih HERO WADAH (Base) yang akan menerima serapan jiwa:")
            for i, cand in enumerate(alive_heroes, 1):
                in_p = " [PARTY]" if cand.name in self.party.members else ""
                print("  %3d. %-26s %s %-7s L%-2d | Mental: %-14s | Vessel: %d/%d%s" % (
                    i, cand.name[:26], "*" * cand.star, cand.cls, cand.level,
                    cand.mental_status_label(), cand.synth_count, cand.vessel_cap(), in_p))
            print("    0. Kembali / Batal")
            c_base = ask_choice(
                "  Pilih Hero Wadah > ",
                ["0"] + [str(i) for i in range(1, len(alive_heroes) + 1)],
            )
            if c_base == "0":
                return
            base_hero = alive_heroes[int(c_base) - 1]

        # 2) Tampilkan ringkasan Hero Wadah + peringatan overload bila vessel penuh
        cap = base_hero.vessel_cap()
        print("\n  --- HERO WADAH TERPILIH ---")
        print("  Nama   : %s (%s %s, Level %d)" % (
            base_hero.name, "*" * base_hero.star, base_hero.cls, base_hero.level))
        print("  Mental : %s  |  Kapasitas Vessel: %d/%d  |  Jiwa Terserap: %d" % (
            base_hero.mental_status_label(), base_hero.synth_count, cap,
            base_hero.absorbed_souls))
        print("  Traits : %s" % (", ".join(base_hero.traits) if base_hero.traits else "-"))
        print("  Skills : %s" % (", ".join(base_hero.skills) if base_hero.skills else "-"))
        if base_hero.synth_count >= cap:
            print("\n  [!] PERINGATAN KAPASITAS VESSEL:")
            print("      Tubuh %s telah mencapai batas daya tampung bintang ini (%d/%d)!" % (
                base_hero.name, base_hero.synth_count, cap))
            print("      Memaksakan sintesis akan memicu SOUL OVERLOAD — daya serap merosot")
            print("      tajam dan guncangan mental meningkat berlipat ganda!")

        # 3) Pilih Hero Tumbal (Material)
        mat_cands = [h for h in alive_heroes if h.name != base_hero.name]
        if not mat_cands:
            print("  ! Tidak ada hero lain yang dapat dijadikan tumbal.")
            return
        print("\n  Pilih HERO TUMBAL (Material) yang akan dikorbankan:")
        for i, mc in enumerate(mat_cands, 1):
            in_p = " [PARTY]" if mc.name in self.party.members else ""
            eq_n = sum(1 for eq in mc.equipment.values() if eq is not None)
            eq_tag = (" [Equip:%d]" % eq_n) if eq_n else ""
            print("  %3d. %-26s %s %-7s L%-2d | Traits: %s%s%s" % (
                i, mc.name[:26], "*" * mc.star, mc.cls, mc.level,
                ", ".join(mc.traits) if mc.traits else "-", in_p, eq_tag))
        print("    0. Kembali / Batal")
        c_mat = ask_choice(
            "  Pilih Hero Tumbal > ",
            ["0"] + [str(i) for i in range(1, len(mat_cands) + 1)],
        )
        if c_mat == "0":
            return
        mat_hero = mat_cands[int(c_mat) - 1]

        # 4) Konfirmasi akhir
        print("\n  === KONFIRMASI RITUAL SYNTHESIS ===")
        print("  Wadah (Base)     : %s (%s %s L%d)" % (
            base_hero.name, "*" * base_hero.star, base_hero.cls, base_hero.level))
        print("  Tumbal (Material): %s (%s %s L%d)" % (
            mat_hero.name, "*" * mat_hero.star, mat_hero.cls, mat_hero.level))
        print("  (!) PERINGATAN: Jiwa tumbal akan LENYAP PERMANEN dalam Synthesis Chamber.")
        print("      Seluruh equipment yang terpasang akan dilepas otomatis ke Inventory.")
        c_ok = ask_choice("  Jalankan sintesis sekarang? (y/n, 0=batal) > ",
                          ["0", "y", "n", "Y", "N"])
        if c_ok == "0":
            print("  Sintesis dibatalkan.")
            return
        if c_ok.lower() == "n":
            print("  Sintesis dibatalkan.")
            return

        # 5) Eksekusi sintesis & pembersihan tumbal
        base_was_in_party = (base_hero.name in self.party.members)
        mental_before = base_hero.mental_status_label()
        res = base_hero.synthesize_with(mat_hero)
        survivor = res["survivor"]
        deceased = res["deceased"]

        print("\n" + line("-", 62))
        print("  Rantai cahaya mengunci %s dan %s di tengah Synthesis Chamber..." % (
            base_hero.name, mat_hero.name))
        sleep(BATTLE_DELAY)
        if res["ego_override"]:
            mental_before = "bergejolak"
            print("  [!!!] ANOMALI SYNTHESIS CHAMBER — EGO OVERRIDE! [!!!]")
            print("  Jiwa %s menolak hancur! Kehendaknya yang buas membalikkan" % survivor.name)
            print("  aliran rantai jiwa dan justru MENELAN tubuh %s bulat-bulat!" % deceased.name)
        else:
            print("  Cahaya biru meredup... esensi %s terserap sepenuhnya ke dalam %s." % (
                deceased.name, survivor.name))
        if res["overload"]:
            print("  [!] SOUL OVERLOAD: Kapasitas vessel meluap, kesadaran %s retak hebat!" % (
                survivor.name))

        cleanup = self.sacrifice_hero_cleanup(deceased.name, salvage_equip=True)
        if res["ego_override"] and base_was_in_party:
            if survivor.name not in self.party.members and len(self.party.members) < PARTY_MAX:
                self.party.add(survivor, self.roster())
                self.state["party"] = list(self.party.members)

        # 6) Tampilkan hasil pada survivor (TANPA ego, GM, tier, atau persentase)
        print("\n  === HASIL PENYATUAN JIWA ===")
        print("  Survivor       : %s (%s %s)" % (
            survivor.name, "*" * survivor.star, survivor.cls))
        if res["level_after"] > res["level_before"]:
            print("  Level          : L%d -> L%d (+%d XP jiwa)" % (
                res["level_before"], res["level_after"], res["xp_gain"]))
        else:
            print("  Level          : L%d (+%d XP jiwa, XP %d/%d)" % (
                survivor.level, res["xp_gain"], survivor.xp, survivor.xp_needed()))

        sg = res["stat_gains"]
        b_parts = []
        for k, lbl, fmt in (("hp", "HP", "+%.1f"), ("atk", "ATK", "+%.1f"),
                            ("def", "DEF", "+%.1f"), ("spd", "SPD", "+%.2f"),
                            ("mp", "MP", "+%.1f")):
            if sg.get(k, 0) > 0:
                b_parts.append("%s %s" % (lbl, fmt % sg[k]))
        print("  Serapan Base   : %s" % (", ".join(b_parts) if b_parts else "(batas maksimum tercapai)"))

        gg = res["growth_gains"]
        g_parts = []
        for k, lbl, fmt in (("hp", "HP", "+%.2f"), ("atk", "ATK", "+%.2f"),
                            ("def", "DEF", "+%.2f"), ("spd", "SPD", "+%.3f"),
                            ("mp", "MP", "+%.2f")):
            if gg.get(k, 0) > 0:
                g_parts.append("%s %s/Lv" % (lbl, fmt % gg[k]))
        print("  Serapan Rise   : %s" % (", ".join(g_parts) if g_parts else "(batas maksimum tercapai)"))

        if res["inherited_skills"]:
            print("  Skill Diwarisi : %s" % ", ".join(res["inherited_skills"]))
        if res["inherited_traits"]:
            print("  Trait Diwarisi : %s" % ", ".join(res["inherited_traits"]))

        print("  Kondisi Mental : %s -> %s  |  Vessel: %d/%d  |  Jiwa Terserap: %d" % (
            mental_before, survivor.mental_status_label(),
            survivor.synth_count, survivor.vessel_cap(), survivor.absorbed_souls))
        if cleanup["salvaged"] > 0:
            print("  Salvage Equip  : %d equipment milik %s dikembalikan ke Inventory." % (
                cleanup["salvaged"], deceased.name))
        print(line("-", 62))

        self.state["total_synthesized"] = _safe_int(self.state.get("total_synthesized"), 0) + 1
        self.gen.register_existing(self.roster())
        self.autosave()

    # ==================== CRAFT MATERIAL (Soul & Essence) ====================
    def craft_menu(self):
        """Crafting Raw Boss Material -> Soulstone matang. Dapat diakses dari
        menu Tower dan dari Inventory (saat memilih raw material)."""
        inv = self.state["inventory"]
        header("CRAFT MATERIAL — SOUL & ESSENCE")
        print("  Kumpulkan Raw Boss Material dari Boss Floor (kelipatan 5)")
        print("  lalu jadikan Soulstone di sini. Book of Oath/Fate TIDAK bisa")
        print("  di-craft — hanya drop dari Boss Floor 80+ & Hidden Boss tinggi.")
        craftable = [(raw, mat, qty) for raw, (mat, qty) in dbs.CRAFT_RECIPES.items()]
        if not craftable:
            print("  (belum ada resep)")
            return
        print()
        for i, (raw, mat, qty) in enumerate(craftable, 1):
            have = _safe_int(inv.get(raw), 0)
            print("  %d. %dx %s  ->  1x %s   (punya %d %s)" % (
                i, qty, raw, mat, have, raw))
        print("  0. Kembali")
        c = ask_choice("  Craft nomor? > ",
                       ["0"] + [str(i) for i in range(1, len(craftable) + 1)])
        if c == "0":
            return
        raw, mat, qty = craftable[int(c) - 1]
        have = _safe_int(inv.get(raw), 0)
        if have < qty:
            print("  ! %s kurang: butuh %d, punya %d." % (raw, qty, have))
            return
        times = ask_int("  Craft berapa kali? (maks %d, 0=batal) > " % (have // qty),
                        0, have // qty, 1)
        if times <= 0:
            return
        inv[raw] = have - times * qty
        inv[mat] = _safe_int(inv.get(mat), 0) + times
        print("  *** CRAFT: %dx %s -> %dx %s! ***" % (
            times * qty, raw, times, mat))
        self.autosave()

    # ============================ SHOP ============================
    def shop_menu(self):
        """Shop: potion, gacha ticket, equipment (masuk Inventory),
        StarFragment."""
        while True:
            header("SHOP")
            inv = self.state["inventory"]
            bag = self.state.get("equip_bag", {})
            print("  Coins: %d | Gems: %d | Items: %d | Equipment di bag: %d" % (
                self.state["coins"], self.state["gems"],
                sum(1 for v in inv.values() if v), len(bag)))
            print("  1. Potion HP (heal 50% HP max) — 300 coins")
            print("  2. Gacha Ticket (1 pull gratis) — 1200 coins")
            print("  3. Equipment Mystery Box — 2500 coins (masuk Inventory)")
            print("  0. Kembali")
            c = ask_choice("  Pilih > ", ["0", "1", "2", "3"])
            if c == "0":
                return
            if c == "1":
                if self.buy(300):
                    inv["Potion HP"] = min(5, _safe_int(inv.get("Potion HP"), 0) + 1)
                    print("  + 1 Potion HP")
            elif c == "2":
                if self.buy(1200):
                    self.state["free_gacha"] = _safe_int(self.state.get("free_gacha"), 0) + 1
                    print("  + 1 Gacha Ticket (free pull)")
            elif c == "3":
                if self.buy(2500):
                    eq = Equipment.random()
                    self.add_equipment_to_bag(eq)
                    print("  Dapat: %s (masuk Inventory)" % eq.describe())
            self.autosave()

    def buy(self, price):
        if self.state["coins"] < price:
            print("  ! Coins tidak cukup.")
            return False
        self.state["coins"] -= price
        return True

    # ==================== TAS BATTLE (item bawaan) ====================
    # Kapasitas = 2 x jumlah hero di party (1 hero -> 2 item, 5 hero -> 10).
    # Item yang dibawa dipakai OTOMATIS oleh AI hero di dalam battle.
    BATTLE_ITEMS = {
        # nama item -> (efek, label)
        "Potion HP": ("heal50", "Pulihkan 50%% HP max satu hero"),
        "Attack Elixir": ("atk30", "ATK +30%% 3 ronde satu hero"),
        "Guard Elixir": ("def30", "DEF +30%% 3 ronde satu hero"),
        "Mana Philter": ("mana", "Isi penuh MP satu hero"),
        "Revive Feather": ("revive", "Bangkitkan hero gugur 40%% HP"),
    }

    def battle_bag(self):
        """List item bawaan battle (tersimpan per-akun)."""
        return self.state.setdefault("battle_bag", [])

    def battle_bag_flow(self):
        """Kelola Tas Battle dari menu Inventory: lihat isi & kapasitas,
        tambah item dari inventory, kembalikan item ke inventory."""
        bag = self.battle_bag()
        inv = self.state["inventory"]
        cap = self.battle_capacity()
        while True:
            header("TAS BATTLE — kapasitas %d item (2 x %d hero party)"
                   % (cap, len(self.party.members)))
            print("  Item di sini dipakai OTOMATIS oleh hero saat battle")
            print("  (AI memutuskan kapan & ke siapa item paling berguna).")
            if bag:
                for i, nm in enumerate(bag, 1):
                    print("  %2d. %-16s : %s" % (i, nm, self.BATTLE_ITEMS.get(
                        nm, ("", ""))[1]))
            else:
                print("  (tas kosong)")
            print("\n  1. Bawa item dari Inventory   2. Kembalikan item")
            print("  0. Kembali")
            c = ask_choice("  Pilih > ", ["0", "1", "2"])
            if c == "0":
                self.autosave()
                return
            if c == "1":
                # hanya item yang dikenal efek battle-nya & stok ada
                cands = [nm for nm in sorted(self.BATTLE_ITEMS)
                         if _safe_int(inv.get(nm), 0) > 0]
                if not cands:
                    print("  ! Tidak ada item battle di Inventory.")
                    continue
                for i, nm in enumerate(cands, 1):
                    print("   %d. %-16s (stok %d) : %s" % (
                        i, nm, _safe_int(inv.get(nm), 0),
                        self.BATTLE_ITEMS[nm][1]))
                idx = ask_int("  Bawa item nomor? (0=batal) > ", 0, len(cands), 0)
                if idx == 0:
                    continue
                nm = cands[idx - 1]
                if len(bag) >= cap:
                    print("  ! Tas penuh (%d/%d). Kembalikan item dulu / tambah hero ke party."
                          % (len(bag), cap))
                    continue
                inv[nm] = _safe_int(inv.get(nm), 0) - 1
                bag.append(nm)
                print("  >> %s masuk Tas Battle (%d/%d)." % (nm, len(bag), cap))
            elif c == "2":
                if not bag:
                    print("  ! Tas kosong.")
                    continue
                idx = ask_int("  Kembalikan nomor? (0=batal) > ", 0, len(bag), 0)
                if idx == 0:
                    continue
                nm = bag.pop(idx - 1)
                inv[nm] = _safe_int(inv.get(nm), 0) + 1
                print("  %s kembali ke Inventory." % nm)
            self.autosave()


# =============================== MAIN ===============================
def main():
    # SPLASH + LOGIN: tiap akun (username & password unik di tabel accounts)
    # memiliki savegame sendiri di saves/ — update game tidak pernah
    # menghapus progres akun (file save tidak pernah disentuh patcher).
    username = login_menu()
    print()
    print(line("=", 62))
    print("  AUTO-BATTLE STRATEGY RPG — PICK ME UP: INFINITE GACHA".center(62))
    print(("  v%s — 3 modul + database SQLite | Akun: %s" % (VERSION, username)).center(62))
    print(line("=", 62))
    game = Game(username)
    try:
        game.run()
    except KeyboardInterrupt:
        # Exit bersih dengan auto-save saat Ctrl+C
        try:
            game.autosave()
            print("\n\n  [Interrupted] Auto-save... Sampai jumpa!")
        except Exception:
            print("\n  Keluar.")
        sys.exit(0)


if __name__ == "__main__":
    main()
