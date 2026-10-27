# ======================================================================
#  GENERATE HERO — Modul Generator Hero & Gacha (Terpisah)
#  Game: Auto-Battle Strategy RPG "Pick Me Up: Infinite Gacha" (CLI)
# ----------------------------------------------------------------------
#  Tugas modul ini:
#    - Menarik data dari game_database.db (via database_setup.py)
#    - Logika gacha: 1S 84.9% | 2S 10% | 3S 4% | 4S 1% | 5S 0.1%
#    - Hidden Potential 1-star: 7% peluang growth multiplier 1.5-2.5x
#      + perk Rare/Legendary ekstra (1-star bisa melampaui 4-star!)
#    - Mage: class langka ~3% dari total roll (AoE + CC game changer)
#    - ANTI-DUPLIKAT: nama & kombinasi (nama, growth, perks) wajib unik
#    - Mengembalikan instance Hero siap pakai untuk main.py
#  Python 3 stdlib ONLY (selain database_setup.py milik project ini).
# ======================================================================
import random

import database_setup as db

# ------------------------- KONSTANTA GACHA -------------------------
# Rate persis sesuai spek (bobot per 1000): akurat untuk 0.1%.
GACHA_RATES = [(1, 849), (2, 100), (3, 40), (4, 10), (5, 1)]
# Hidden potential: hanya 1-star. 7% -> Tier A (GM 1.5-2.5x + perk bagus).
HIDDEN_CHANCE = 0.07
HIDDEN_GM_RANGE = (1.5, 2.5)
# Tier perk: Common 60% / Rare 30% / Epic 9% / Legendary 1%
TIER_WEIGHT = {"Common": 60, "Rare": 30, "Epic": 9, "Legendary": 1}
# Harga gacha (coins / gems)
PRICE_COINS = {1: 500, 10: 4500}
PRICE_GEMS = {1: 1, 10: 9}

MAX_LEVEL = 99
MAX_STAR = 7

# Cache data database dimuat SEKALI di import (statistik tidak berubah
# saat runtime; menghemat ribuan query per battle).
_CLASS_STATS = db.load_class_stats()
_STAR_MULTS = db.load_star_mults()
_PERKS = db.load_perks()
_SKILLS = db.load_skills()
_ITEMS = db.load_items()

CLASSES = list(_CLASS_STATS.keys()) if _CLASS_STATS else \
    ["Tanker", "Dealer", "Archer", "Healer", "Buffer", "Mage"]


def reload_db_data():
    """Paksa muat ulang cache dari database (mis. setelah re-seed manual)."""
    global _CLASS_STATS, _STAR_MULTS, _PERKS, _SKILLS, _ITEMS, CLASSES
    _CLASS_STATS = db.load_class_stats()
    _STAR_MULTS = db.load_star_mults()
    _PERKS = db.load_perks()
    _SKILLS = db.load_skills()
    _ITEMS = db.load_items()
    CLASSES = list(_CLASS_STATS.keys()) if _CLASS_STATS else CLASSES


def weighted_choice(pairs, rng=None):
    """Roulette-wheel selection: [(item, bobot), ...] -> 1 item.
    Titik kumulatif float -> akurat untuk bobot pecahan kecil (0.1%)."""
    rng = rng or random
    total = sum(w for _, w in pairs)
    r = rng.uniform(0, total)
    acc = 0.0
    for item, w in pairs:
        acc += w
        if r <= acc:
            return item
    return pairs[-1][0]


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


# ============================ EQUIPMENT ============================
class Equipment:
    """Item yang bisa dipakai hero. Kurva stat per tier mengikuti
    items_master di database (template), dengan sedikit random saat drop."""

    def __init__(self, slot, name, tier, atk=0, dfn=0, hp=0):
        self.slot = slot
        self.name = name
        self.tier = tier          # 1..5 (Common..Legendary)
        self.atk = atk
        self.dfn = dfn
        self.hp = hp

    def to_dict(self):
        return {"slot": self.slot, "name": self.name, "tier": self.tier,
                "atk": self.atk, "dfn": self.dfn, "hp": self.hp}

    @classmethod
    def from_dict(cls, d):
        # try/except ketat: save lama/rusak tidak boleh bikin crash
        try:
            return cls(str(d.get("slot", "Senjata")), str(d.get("name", "?")),
                       _safe_int(d.get("tier", 1), 1), _safe_int(d.get("atk", 0)),
                       _safe_int(d.get("dfn", 0)), _safe_int(d.get("hp", 0)))
        except Exception:
            return cls("Senjata", "Item Misterius", 1)

    @classmethod
    def from_master(cls, row):
        """Buat Equipment dari baris items_master (dict dari database)."""
        return cls(row.get("slot") or "Senjata", row.get("name") or "?",
                   _safe_int(row.get("tier"), 1), _safe_int(row.get("atk")),
                   _safe_int(row.get("dfn")), _safe_int(row.get("hp")))

    @classmethod
    def random(cls, tier=None, rng=None):
        """Generate equipment acak saat drop. Nama dari items_master
        (database), stat mengikuti kurva per tier + random kecil."""
        rng = rng or random
        if tier is None:
            tier = weighted_choice([(1, 50), (2, 30), (3, 14), (4, 5), (5, 1)], rng)
        slot = rng.choice(("Senjata", "Zirah", "Aksesori"))
        # Nama kandidat dari database (fallback konstanta seed)
        cands = [it for it in _ITEMS
                 if it.get("category") == "equipment"
                 and it.get("slot") == slot and _safe_int(it.get("tier")) == tier]
        if cands:
            name = rng.choice(cands)["name"]
        else:
            name = "%s T%d" % (slot, tier)
        atk = dfn = hp = 0
        # Offset stat per slot: Senjata = ofensif, Zirah = defensif, Aksesori = campuran
        if slot == "Senjata":
            atk = 3 * tier + rng.randint(0, 2 * tier)
            dfn = rng.randint(0, tier)
        elif slot == "Zirah":
            dfn = 3 * tier + rng.randint(0, 2 * tier)
            hp = 8 * tier + rng.randint(0, 5 * tier)
        else:
            atk = 2 * tier + rng.randint(0, tier)
            dfn = 1 * tier + rng.randint(0, tier)
            hp = 5 * tier + rng.randint(0, 3 * tier)
        return cls(slot, name, tier, atk, dfn, hp)

    def describe(self):
        from database_setup import TIER_LABEL
        parts = []
        if self.atk: parts.append("ATK+%d" % self.atk)
        if self.dfn: parts.append("DEF+%d" % self.dfn)
        if self.hp:  parts.append("HP+%d" % self.hp)
        return "%s [%s T%d] %s" % (self.slot, TIER_LABEL.get(self.tier, "?"), self.tier,
                                   ", ".join(parts) if parts else "kosong")


# =============================== TRAIT & SKILL ===============================
class Trait:
    """Representasi trait (dahulu perk; data dari tabel perks di database).
    RAHASIA: tier hanya dipakai internal saat roll, TIDAK ditampilkan di UI."""

    def __init__(self, name):
        self.name = name
        tier, desc = _PERKS.get(name, ("Common", "Tanpa efek"))
        self.tier = tier
        self.desc = desc

    @staticmethod
    def all_names():
        return list(_PERKS.keys())

    @staticmethod
    def tier_of(name):
        return _PERKS.get(name, ("Common", ""))[0]


# Alias backward-compatibility
Perk = Trait


class Skill:
    """Representasi skill (data dari tabel skills di database).
    Pool terdiri dari 30 skill per class (6x30=180) + 60 skill Universal (total 240).
    RAHASIA: tier skill hanya untuk bobot roll, TIDAK ditampilkan di UI."""

    def __init__(self, name):
        self.name = name
        info = _SKILLS.get(name) or {
            "cls": "Universal", "tier": "Common", "mp_cost": 15, "cd": 3,
            "kind": "single", "mult": 1.5, "description": "Skill",
        }
        self.cls = info.get("cls", "Universal")
        self.tier = info["tier"]
        self.mp_cost = info["mp_cost"]
        self.cd = info["cd"]
        self.kind = info["kind"]
        self.mult = info["mult"]
        self.desc = info["description"]

    @staticmethod
    def all_names():
        return list(_SKILLS.keys())

    @staticmethod
    def info_of(name):
        return _SKILLS.get(name)


def _roll_skewed_value(lo, hi, star=1, band_weights_map=None, rng=None):
    """Roll nilai acak di rentang [lo, hi] dengan distribusi miring (skewed):
      - Makin tinggi nilai stat/rise-rate, makin kecil persentasenya.
      - Makin tinggi star (1..7), makin besar persentase mendapat band tinggi.
      - Hero 1-star tetap bisa mendapat nilai maksimum (hi) namun persentasenya
        sangat kecil."""
    rng = rng or random
    s = max(1, min(MAX_STAR, _safe_int(star, 1)))
    w_map = band_weights_map or db.STAR_STAT_BAND_WEIGHTS
    weights = w_map.get(s, w_map[1])
    bands = db.STAT_BANDS
    b_idx = weighted_choice(list(enumerate(weights)), rng)
    b_lo, b_hi = bands[b_idx]
    # Di dalam pita tertinggi (Band 4: 80%-100%), ada peluang kecil menyentuh
    # puncak [96%-100%] termasuk tepat nilai maksimum (hi).
    if b_idx == len(bands) - 1 and rng.random() < 0.15:
        if rng.random() < 0.25:
            pos = 1.0
        else:
            pos = 0.96 + 0.04 * rng.random()
    else:
        # Eksponen > 1 membuat nilai yang lebih tinggi di dalam band lebih langka
        u = rng.random() ** 1.25
        pos = b_lo + (b_hi - b_lo) * u
    val = lo + (hi - lo) * pos
    return max(lo, min(hi, val))


def roll_random_base_stats(hero_cls="Dealer", star=1, rng=None):
    """Roll tuple (hp, atk, def, spd, mp) base stat acak:
      - Minimum tiap stat berbeda-beda tergantung class (STAT_BASE_MIN_BY_CLASS).
      - Maksimum tiap stat SAMA untuk semua class & star (STAT_BASE_MAX).
      - Makin tinggi stat, persentasenya makin kecil.
      - Makin tinggi star, makin besar peluang mendapat stat sangat tinggi."""
    # Kompatibilitas pemanggilan lama: roll_random_base_stats(rng)
    if hasattr(hero_cls, "random") and not isinstance(hero_cls, str):
        rng = hero_cls
        hero_cls = "Dealer"
        star = 1
    elif hasattr(star, "random") and not isinstance(star, (int, float)):
        rng = star
        star = 1
    rng = rng or random
    min_map = db.STAT_BASE_MIN_BY_CLASS.get(
        hero_cls, db.STAT_BASE_MIN_BY_CLASS["Dealer"])
    max_map = db.STAT_BASE_MAX
    return (
        round(_roll_skewed_value(min_map["hp"],  max_map["hp"],  star, db.STAR_STAT_BAND_WEIGHTS, rng), 1),
        round(_roll_skewed_value(min_map["atk"], max_map["atk"], star, db.STAR_STAT_BAND_WEIGHTS, rng), 1),
        round(_roll_skewed_value(min_map["def"], max_map["def"], star, db.STAR_STAT_BAND_WEIGHTS, rng), 1),
        round(_roll_skewed_value(min_map["spd"], max_map["spd"], star, db.STAR_STAT_BAND_WEIGHTS, rng), 2),
        round(_roll_skewed_value(min_map["mp"],  max_map["mp"],  star, db.STAR_STAT_BAND_WEIGHTS, rng), 1),
    )


def roll_random_growth_stats(star=1, rng=None):
    """Roll tuple (hp, atk, def, spd, mp) rise rate stat per level:
      - Minimum dan maksimum rise rate SAMA untuk semua star & class (STAT_GROWTH_RANGE).
      - Yang berbeda tiap star HANYA persentase mendapat rise rate yang bagus.
      - Makin tinggi star, makin besar peluang dapat rise rate tinggi; hero 1-star
        juga bisa dapat rise rate maksimum namun persentasenya sangat kecil."""
    # Kompatibilitas pemanggilan lama: roll_random_growth_stats(rng)
    if hasattr(star, "random") and not isinstance(star, (int, float)):
        rng = star
        star = 1
    rng = rng or random
    r = db.STAT_GROWTH_RANGE
    return (
        round(_roll_skewed_value(r["hp"][0],  r["hp"][1],  star, db.STAR_GROWTH_BAND_WEIGHTS, rng), 2),
        round(_roll_skewed_value(r["atk"][0], r["atk"][1], star, db.STAR_GROWTH_BAND_WEIGHTS, rng), 2),
        round(_roll_skewed_value(r["def"][0], r["def"][1], star, db.STAR_GROWTH_BAND_WEIGHTS, rng), 2),
        round(_roll_skewed_value(r["spd"][0], r["spd"][1], star, db.STAR_GROWTH_BAND_WEIGHTS, rng), 3),
        round(_roll_skewed_value(r["mp"][0],  r["mp"][1],  star, db.STAR_GROWTH_BAND_WEIGHTS, rng), 2),
    )


def roll_random_mp_regen(star=1, rng=None):
    """Roll MP regen per ronde secara acak (3..8), makin tinggi makin langka."""
    if hasattr(star, "random") and not isinstance(star, (int, float)):
        rng = star
        star = 1
    rng = rng or random
    lo, hi = db.MP_REGEN_RANGE
    val = _roll_skewed_value(float(lo), float(hi), star, db.STAR_STAT_BAND_WEIGHTS, rng)
    return max(lo, min(hi, int(round(val))))


def _pick_from_skill_pool(pool_dict, count, used_leg, rng):
    """Helper internal: ambil `count` skill unik dari `pool_dict` berdasarkan TIER_WEIGHT."""
    chosen_list = []
    for _ in range(count):
        tier = weighted_choice(list(TIER_WEIGHT.items()), rng)
        if tier == "Legendary" and used_leg:
            tier = "Epic"
        cands = [s for s, info in pool_dict.items()
                 if info["tier"] == tier and s not in chosen_list]
        if not cands:
            cands = [s for s, info in pool_dict.items()
                     if s not in chosen_list and not (info["tier"] == "Legendary" and used_leg)]
        if not cands:
            cands = [s for s in pool_dict if s not in chosen_list]
        if not cands:
            continue
        sk = rng.choice(cands)
        chosen_list.append(sk)
        if pool_dict[sk]["tier"] == "Legendary":
            used_leg = True
    return chosen_list, used_leg


def roll_random_skills(hero_cls="Dealer", star=1, rare_bonus=False, rng=None):
    """Roll skill untuk 1 hero:
      - 1-2 skill dari pool class hero tersebut (30 skill per class)
      - 0-3 skill dari pool Universal (60 skill universal, TANPA Taunt)
    Jumlah & kualitas bergantung pada keberuntungan (TIER_WEIGHT)."""
    rng = rng or random
    if hero_cls not in _CLASS_STATS:
        hero_cls = "Dealer"
    cls_pool = {s: info for s, info in _SKILLS.items() if info.get("cls") == hero_cls}
    uni_pool = {s: info for s, info in _SKILLS.items() if info.get("cls") == "Universal"}

    # 1) Roll 1-2 Class Skills
    n_cls = weighted_choice([(1, 60), (2, 40)], rng)
    if star >= 5 or (rare_bonus and rng.random() < 0.5):
        n_cls = 2
    n_cls = min(2, max(1, n_cls))
    used_leg = False
    cls_skills, used_leg = _pick_from_skill_pool(cls_pool, n_cls, used_leg, rng)
    if not cls_skills and cls_pool:
        cls_skills = [rng.choice(list(cls_pool.keys()))]

    # 2) Roll 0-3 Universal Skills (tergantung keberuntungan)
    n_uni = weighted_choice([(0, 25), (1, 40), (2, 25), (3, 10)], rng)
    if star >= 5:
        n_uni = max(1, n_uni)
    if rare_bonus and n_uni < 3 and rng.random() < 0.5:
        n_uni += 1
    n_uni = min(3, max(0, n_uni))
    uni_skills, used_leg = _pick_from_skill_pool(uni_pool, n_uni, used_leg, rng)

    return cls_skills + uni_skills


# =============================== HERO ===============================
EQUIP_SLOTS = db.EQUIP_SLOTS


class Hero:
    """Satu hero. Semua stat final dihitung dari: base_stats unik hero x star mult
    + growth_stats unik hero x (level-1) x growth_multiplier, lalu modifier trait/equip.
    Kini tiap hero benar-benar unik: base_stats, growth_stats, mp_regen, traits,
    dan skills (1-2 skill class + 0-3 skill universal) di-roll secara acak!
    Star awal TIDAK membatasi power akhir karena growth_multiplier
    (hidden potential) bisa menaikkan kurva 1-star secara drastis."""

    def __init__(self, name, star, cls, level=1, growth_multiplier=1.0,
                 perks=None, skills=None, base_stats=None, growth_stats=None,
                 mp_regen_val=None, traits=None):
        self.name = name
        self.star = int(star)
        self.cls = cls
        self.level = max(1, int(level))
        self.xp = 0
        self.growth_multiplier = float(growth_multiplier)
        raw_traits = traits if traits is not None else perks
        self.traits = list(raw_traits) if raw_traits else []
        # Alias perks -> mengarah ke list traits yang sama untuk kompatibilitas
        self.perks = self.traits
        # Stat dasar & rise rate unik per individu hero:
        #   - Base stat: minimum per class, maksimum universal, peluang tinggi sesuai star
        #   - Rise rate (growth_stats): min & max sama di semua star, peluang tinggi sesuai star
        if isinstance(base_stats, (list, tuple)) and len(base_stats) == 5:
            self.base_stats = tuple(float(x) for x in base_stats)
        else:
            self.base_stats = roll_random_base_stats(self.cls, self.star)
        if isinstance(growth_stats, (list, tuple)) and len(growth_stats) == 5:
            self.growth_stats = tuple(float(x) for x in growth_stats)
        else:
            self.growth_stats = roll_random_growth_stats(self.star)
        if mp_regen_val is not None:
            self.mp_regen_base = max(1, _safe_int(mp_regen_val, 4))
        else:
            self.mp_regen_base = roll_random_mp_regen(self.star)
        # Skill acak unik per individu hero (1-2 class skill + 0-3 universal skill)
        valid_skills = [str(s) for s in (skills or []) if s in _SKILLS]
        self.skills = valid_skills if valid_skills else roll_random_skills(self.cls, self.star)
        self.equipment = {"Senjata": None, "Zirah": None, "Aksesori": None}
        self.alive = True
        self.blueprints = 0
        # Battle state (direset tiap battle oleh BattleEngine)
        self.hp = self.max_hp
        self.mana = 0.0
        self.taunt_turns = 0     # ronde tersisa musuh dipaksa menarget hero ini
        self.buff_atk = 0        # % buff ATK
        self.buff_def = 0        # % buff DEF
        self.buff_spd = 0        # % buff SPD
        self.stun_turns = 0
        self.skill_cd = {}       # {nama_skill: sisa cooldown}
        self.used_last_stand = False
        self.used_phoenix = False
        self.last_hit_by = None  # nama musuh terakhir yang memukul (untuk log)
        self.refresh()

    # ---------- Akses data class dari cache database ----------
    @property
    def _cstats(self):
        # Fallback aman bila class tidak dikenal (save rusak)
        return _CLASS_STATS.get(self.cls) or _CLASS_STATS["Dealer"]

    def _star_mults(self):
        # (base_mult, growth_mult) untuk star saat ini; clamp 1..7
        s = max(1, min(MAX_STAR, int(self.star)))
        return _STAR_MULTS.get(s, (1.0, 1.0))

    # ---------- Fingerprint unik: (nama, base, growth, traits, skills) ----------
    def fingerprint(self):
        b = self.base_tuple()
        g = self.growth_tuple()
        return (self.name, b, g, tuple(sorted(self.traits)), tuple(sorted(self.skills)))

    def base_tuple(self):
        """Tuple base stat unik hero (dibulatkan 2 desimal)."""
        return tuple(round(v, 2) for v in self.base_stats)

    def growth_tuple(self):
        """Tuple rise rate efektif per hero x GM (dibulatkan 3 desimal)."""
        gm = self.effective_gm()
        return tuple(round(v * gm, 3) for v in self.growth_stats)

    def effective_gm(self):
        """GM efektif = hidden potential GM + Chosen One (+0.3) + Late Bloomer (+0.5 mulai L30)."""
        gm = self.growth_multiplier
        if "Chosen One" in self.traits:
            gm += 0.3
        if "Late Bloomer" in self.traits and self.level >= 30:
            gm += 0.5
        return gm

    def has(self, trait_name):
        return trait_name in self.traits

    def has_skill(self, skill_name):
        return skill_name in self.skills

    def skill_mp_cost(self, base_cost):
        """Hitung MP cost efektif setelah trait pengurang biaya MP."""
        cost = float(base_cost)
        if self.has("Spell Weaver"):
            cost *= 0.85
        if self.has("Infinite Mana"):
            cost *= 0.80
        return max(1, int(round(cost)))

    # ----------------------- Stat dasar per level -----------------------
    def _base_stat(self, idx):
        """Stat mentah = base_stats[idx] + growth_stats[idx]*(level-1)*GM.
        Maksimum base_stats dan rentang growth_stats (rise rate) SAMA lintas
        semua star; perbedaan star diatur melalui persentase peluang saat roll."""
        b = self.base_stats[idx]
        g = self.growth_stats[idx]
        return b + g * (self.level - 1) * self.effective_gm()

    def promote_star(self, target_star, rng=None):
        """Promosi bintang hero: naikkan star ke target_star dan re-roll peningkatan
        base_stats & rise rate (growth_stats) mengikuti distribusi persentase star baru,
        namun tetap dibatasi maksimum universal (STAT_BASE_MAX & STAT_GROWTH_RANGE)."""
        rng = rng or random
        self.star = max(1, min(MAX_STAR, int(target_star)))
        cand_b = roll_random_base_stats(self.cls, self.star, rng)
        cand_g = roll_random_growth_stats(self.star, rng)
        keys = ("hp", "atk", "def", "spd", "mp")
        decs_b = (1, 1, 1, 2, 1)
        decs_g = (2, 2, 2, 3, 2)
        new_b = []
        new_g = []
        for i, k in enumerate(keys):
            b_max = db.STAT_BASE_MAX[k]
            b_min = db.STAT_BASE_MIN_BY_CLASS.get(
                self.cls, db.STAT_BASE_MIN_BY_CLASS["Dealer"])[k]
            cur_b = self.base_stats[i]
            step_b = (b_max - b_min) * rng.uniform(0.04, 0.10)
            val_b = min(b_max, max(cur_b + step_b, cand_b[i]))
            new_b.append(round(val_b, decs_b[i]))

            g_min, g_max = db.STAT_GROWTH_RANGE[k]
            cur_g = self.growth_stats[i]
            step_g = (g_max - g_min) * rng.uniform(0.04, 0.10)
            val_g = min(g_max, max(cur_g + step_g, cand_g[i]))
            new_g.append(round(val_g, decs_g[i]))
        self.base_stats = tuple(new_b)
        self.growth_stats = tuple(new_g)
        self.refresh()

    def _final_stat(self, idx, use_equip=True):
        v = self._base_stat(idx)
        # Trait stat modifier
        if idx == 1:  # ATK
            if self.has("Glass Cannon"):    v *= 1.40
            if self.has("Unlucky"):         v *= 1.40
            if self.has("Chosen One"):      v *= 1.10
            if self.has("Sharp Edge"):      v *= 1.15
            if self.has("Reckless Charge"): v *= 1.25
            if self.has("Thick Armor"):     v *= 0.90
            if self.has("Fierce Grip"):     v *= 1.12
            if self.has("Bloodthirst"):     v *= 1.20
            if self.has("Wind Runner"):     v *= 1.10
            if self.has("Precision"):       v *= 1.18
            if self.has("Warlord"):         v *= 1.22
            if self.has("Soul Harvester"):  v *= 1.20
            if self.has("Shadow Step"):     v *= 1.15
            if self.has("Godslayer"):       v *= 1.35
            if self.has("Celestial Grace"): v *= 1.18
            if self.has("Berserk") and getattr(self, "hp", v) < self.max_hp * 0.5:
                v *= 1.35
            if self.has("Counter Stance") and getattr(self, "hp", v) < self.max_hp:
                v *= 1.10
        if idx == 2:  # DEF
            if self.has("Iron Wall"):       v *= 1.50
            if self.has("Glass Cannon"):    v *= 0.70
            if self.has("Chosen One"):      v *= 1.10
            if self.has("Stone Skin"):      v *= 1.20
            if self.has("Nimble Feet"):     v *= 1.05
            if self.has("Thick Armor"):     v *= 1.30
            if self.has("Battle Hardened"): v *= 1.10
            if self.has("Titan Blood"):     v *= 1.12
            if self.has("Counter Stance"):  v *= 1.15
            if self.has("Warlord"):         v *= 1.15
            if self.has("Aegis Heart"):     v *= 1.35
            if self.has("Dragon Scales"):   v *= 1.30
            if self.has("Immortal Vessel"): v *= 1.25
            if self.has("Celestial Grace"): v *= 1.18
            if self.has("Unyielding") and getattr(self, "hp", v) < self.max_hp * 0.5:
                v *= 1.35
        if idx == 3:  # SPD
            if self.has("Iron Wall"):       v *= 0.85
            if self.has("Quick Step"):      v *= 1.15
            if self.has("Chosen One"):      v *= 1.10
            if self.has("Nimble Feet"):     v *= 1.10
            if self.has("Light Armor"):     v *= 1.12
            if self.has("Wind Runner"):     v *= 1.22
            if self.has("Shadow Step"):     v *= 1.28
            if self.has("Celestial Grace"): v *= 1.18
        # Equipment & buff battle additif
        if use_equip:
            eq_atk = eq_def = 0
            for eq in self.equipment.values():
                if eq is None:
                    continue
                if idx == 1: eq_atk += eq.atk
                elif idx == 2: eq_def += eq.dfn
            v += eq_atk + eq_def
        if idx == 3:  # buff SPD hanya saat battle
            v *= (1 + self.buff_spd / 100.0)
        return max(1, int(round(v)))

    @property
    def max_hp(self):
        hp = self._base_stat(0)
        if self.has("Iron Wall"):       hp *= 1.10
        if self.has("Chosen One"):      hp *= 1.10
        if self.has("Sturdy Body"):     hp *= 1.18
        if self.has("Reckless Charge"): hp *= 0.90
        if self.has("Battle Hardened"): hp *= 1.10
        if self.has("Fierce Grip"):     hp *= 1.08
        if self.has("Titan Blood"):     hp *= 1.28
        if self.has("Warlord"):         hp *= 1.20
        if self.has("Aegis Heart"):     hp *= 1.15
        if self.has("Dragon Scales"):   hp *= 1.30
        if self.has("Immortal Vessel"): hp *= 1.45
        if self.has("Celestial Grace"): hp *= 1.18
        hp += self._equipment_hp()
        return max(1, int(round(hp)))

    def _equipment_hp(self):
        return sum(eq.hp for eq in self.equipment.values() if eq is not None)

    @property
    def atk(self):
        # ATK dengan buff battle (additif %, dihitung dari ATK termasuk equip)
        return max(1, int(round(self._final_stat(1) * (1 + self.buff_atk / 100.0))))

    @property
    def dfn(self):
        # DEF final + buff DEF battle (Guard Hymn / Taunt) — additif %
        return max(1, int(round(self._final_stat(2) * (1 + self.buff_def / 100.0))))

    @property
    def spd(self):
        return self._final_stat(3)

    @property
    def max_mp(self):
        mp = self._base_stat(4)
        if self.has("Chosen One"):      mp *= 1.10
        if self.has("Deep Mind"):       mp *= 1.25
        if self.has("Light Armor"):     mp *= 1.10
        if self.has("Arcane Well"):     mp *= 1.40
        if self.has("Soul Harvester"):  mp *= 1.30
        if self.has("Infinite Mana"):   mp *= 1.50
        if self.has("Celestial Grace"): mp *= 1.18
        return max(1, int(round(mp)))

    @property
    def mp_regen(self):
        r = self.mp_regen_base
        if self.has("Calm Spirit"):   r += 2
        if self.has("Arcane Well"):   r += 3
        if self.has("Mana Surge"):    r *= 2
        if self.has("Infinite Mana"): r = int(round(r * 2.5))
        return r

    def refresh(self):
        """Sinkron HP ke max (setelah level up / diluar battle)."""
        self.hp = self.max_hp
        self.mana = 0.0

    # ----------------------------- XP -----------------------------
    def xp_needed(self):
        return int(round(40 * (self.level ** 1.5)))

    def gain_xp(self, amount):
        """XP dengan carry-over; bisa naik banyak level sekaligus.
        Late Bloomer: +1.5% per level kumulatif (bentuk lain: GM +0.5 mulai L30)."""
        if amount <= 0:
            return []
        self.xp += int(amount)
        ups = []
        while self.level < MAX_LEVEL and self.xp >= self.xp_needed():
            self.xp -= self.xp_needed()
            self.level += 1
            ups.append(self.level)
        if self.level >= MAX_LEVEL:
            self.xp = 0
        return ups

    # ------------------------- Serialisasi -------------------------
    def to_dict(self):
        return {
            "name": self.name, "star": self.star, "cls": self.cls,
            "level": self.level, "xp": self.xp,
            "growth_multiplier": self.growth_multiplier,
            "traits": list(self.traits),
            "perks": list(self.traits),   # dipertahankan untuk backward compatibility
            "skills": list(self.skills),
            "base_stats": list(self.base_stats),
            "growth_stats": list(self.growth_stats),
            "mp_regen": self.mp_regen_base,
            "equipment": {s: (e.to_dict() if e else None) for s, e in self.equipment.items()},
            "alive": self.alive,
            "hp": self.hp,   # persist wound state (Heal/Rest jadi berarti)
            "blueprints": _safe_int(getattr(self, "blueprints", 0), 0),
        }

    @classmethod
    def from_dict(cls, d):
        """Load hero dari save (versi lama apapun) dengan default aman.
        Field baru yang hilang (growth_multiplier, traits/perks, skills, base_stats,
        growth_stats, mp_regen, dll) diisi default unik & deterministik."""
        if not isinstance(d, dict):
            d = {}
        try:
            name = str(d.get("name") or "Tanpa Nama")
            star = int(d.get("star", 1))
        except Exception:
            name, star = "Tanpa Nama", 1
        star = max(1, min(MAX_STAR, star))
        hero_cls = str(d.get("cls") or d.get("class") or "Dealer")
        if hero_cls not in _CLASS_STATS:   # guard: save rusak -> fallback class valid
            hero_cls = "Dealer"
        try:
            level = max(1, min(MAX_LEVEL, int(d.get("level", 1))))
        except Exception:
            level = 1
        try:
            gm = float(d.get("growth_multiplier", 1.0))
        except Exception:
            gm = 1.0
        raw_traits = d.get("traits") if d.get("traits") is not None else (d.get("perks") or [])
        traits = [str(p) for p in raw_traits if p in _PERKS]
        # RNG deterministik berbasis nama untuk migrasi save lama tanpa stat/skill acak
        mig_rng = random.Random("pmu_hero_mig::" + name)
        raw_bs = d.get("base_stats")
        if isinstance(raw_bs, (list, tuple)) and len(raw_bs) == 5:
            try:
                base_stats = tuple(float(x) for x in raw_bs)
            except Exception:
                base_stats = roll_random_base_stats(hero_cls, star, mig_rng)
        else:
            base_stats = roll_random_base_stats(hero_cls, star, mig_rng)
        raw_gs = d.get("growth_stats")
        if isinstance(raw_gs, (list, tuple)) and len(raw_gs) == 5:
            try:
                growth_stats = tuple(float(x) for x in raw_gs)
            except Exception:
                growth_stats = roll_random_growth_stats(star, mig_rng)
        else:
            growth_stats = roll_random_growth_stats(star, mig_rng)
        raw_mpr = d.get("mp_regen")
        mp_regen_val = _safe_int(raw_mpr, 0) if raw_mpr is not None else 0
        if mp_regen_val <= 0:
            mp_regen_val = roll_random_mp_regen(star, mig_rng)
        raw_skills = d.get("skills") or []
        skills = [str(s) for s in raw_skills if s in _SKILLS]
        if not skills:
            skills = roll_random_skills(hero_cls, star, gm >= 1.5, mig_rng)
        h = cls(name, star, hero_cls, level, gm, traits,
                skills=skills, base_stats=base_stats,
                growth_stats=growth_stats, mp_regen_val=mp_regen_val)
        h.xp = _safe_int(d.get("xp", 0), 0)
        h.alive = bool(d.get("alive", True))
        eq = d.get("equipment") or {}
        if isinstance(eq, dict):
            for slot in EQUIP_SLOTS:
                item = eq.get(slot)
                if isinstance(item, dict):
                    h.equipment[slot] = Equipment.from_dict(item)
        # Pulihkan HP luka dari save (klamp 0..max); save lama tanpa "hp"
        # otomatis dapat HP penuh (default refresh) — migrasi mulus.
        try:
            saved_hp = int(d.get("hp", h.max_hp))
        except Exception:
            saved_hp = h.max_hp
        h.hp = max(0, min(h.max_hp, saved_hp))
        if h.hp == 0 and h.alive:
            h.hp = 1   # guard: hero hidup tidak boleh HP 0 dari save rusak
        # ensure_fields: field baru versi berikutnya (future-proof)
        h.blueprints = _safe_int(d.get("blueprints", 0), 0)
        return h

    def detail_lines(self):
        """Detail hero untuk layar Detail Hero di menu Manage Hero.
        RAHASIA:
          - hidden potential (growth_multiplier) SENGAJA tidak ditampilkan.
          - tier dari Traits maupun Skills SENGAJA tidak ditampilkan di UI."""
        eqs = [e.describe() for e in self.equipment.values() if e]
        sk_parts = []
        for s in self.skills:
            info = _SKILLS.get(s)
            if info:
                sk_parts.append("%s (%d MP, CD %d)" % (
                    s, self.skill_mp_cost(info["mp_cost"]), info["cd"]))
            else:
                sk_parts.append(s)
        return [
            "Nama   : %s" % self.name,
            "Class  : %s  |  Star: %s  |  Level: %d  (XP %d/%d)" % (
                self.cls, "*" * self.star, self.level, self.xp, self.xp_needed()),
            "Status : %s" % ("HIDUP" if self.alive else "GUGUR"),
            "Traits : %s" % (", ".join(self.traits) if self.traits else "(tidak ada)"),
            "Skills : %s" % (" | ".join(sk_parts) if sk_parts else "(tidak ada)"),
            "HP %d/%d  ATK %d  DEF %d  SPD %d  MP %d/%d  (regen %d/ronde)" % (
                self.hp, self.max_hp, self.atk, self.dfn, self.spd,
                int(self.mana), self.max_mp, self.mp_regen),
            "Rise/Lv: HP +%.2f  ATK +%.2f  DEF +%.2f  SPD +%.3f  MP +%.2f" % (
                self.growth_stats[0], self.growth_stats[1], self.growth_stats[2],
                self.growth_stats[3], self.growth_stats[4]),
            "Equip  : %s" % ("; ".join(eqs) if eqs else "(kosong)"),
        ]

    def talent_label(self):
        gm = self.growth_multiplier
        if gm >= 2.0: return "A - Terpilih (%.1fx)" % gm
        if gm >= 1.5: return "B - Bakat (%.1fx)" % gm
        return "C - Normal (%.1fx)" % gm


# ========================= HERO GENERATOR =========================
class HeroGenerator:
    """Generator hero prosedural — nama & data ditarik dari SQLite.
    ATURAN UNIK: tidak ada dua hero dengan (nama, growth, perks) identik.
    Duplikat -> regenerasi (maks 200 percobaan, lalu suffix serial)."""
    MAX_TRY = 200

    def __init__(self, db_path=None):
        self.db_path = db_path
        self.fingerprints = set()   # set of (name, growth_tuple, perks_tuple)
        self.names = set()          # nama terpakai — roster di-key by name

    def register_existing(self, roster):
        """Saat load save: daftarkan fingerprint + nama hero yang sudah ada."""
        for h in roster.values():
            self.fingerprints.add(h.fingerprint())
            self.names.add(h.name)

    def _roll_name(self, rng):
        """Tarik 1 kombinasi nama acak dari tabel hero_names (database)."""
        return db.pick_name_row(self.db_path, rng)

    def _roll_hidden(self, rng):
        """Roll hidden potential (HANYA 1-star): 7% Tier A -> GM 1.5-2.5x
        + peluang perk Rare/Legendary ekstra. Inilah kenapa 1-star bisa
        melampaui 4-star bila dirawat (star bukan batas kekuatan)."""
        if rng.random() < HIDDEN_CHANCE:
            return rng.uniform(*HIDDEN_GM_RANGE), True
        return 1.0, False

    def _roll_perks(self, star, rare_bonus, rng):
        """Roll 1-3 perk (pool & tier dari tabel perks di database).
        Tier: Common 60% / Rare 30% / Epic 9% / Legendary 1%.
        Max 1 Legendary per hero. 5-star dijamin minimal 1 Rare+."""
        n = weighted_choice([(1, 50), (2, 40), (3, 10)], rng)
        n = min(3, max(1, n))  # spesifikasi: perk per hero 1-3, tidak boleh lebih
        if star >= 5:
            n = max(n, 2)
        perks = []
        used_leg = False
        for _ in range(n):
            tier = weighted_choice(list(TIER_WEIGHT.items()), rng)
            if tier == "Legendary" and used_leg:
                tier = "Epic"
            pool = [p for p, (t, _) in _PERKS.items() if t == tier and p not in perks]
            if not pool:
                continue
            perks.append(rng.choice(pool))
            if tier == "Legendary":
                used_leg = True
        if star >= 5 and len(perks) < 3 and not any(
                _PERKS[p][0] in ("Rare", "Epic", "Legendary") for p in perks):
            pool = [p for p, (t, _) in _PERKS.items() if t == "Rare"]
            perks.append(rng.choice(pool))
        if rare_bonus and len(perks) < 3 and rng.random() < 0.5:
            pool = [p for p, (t, _) in _PERKS.items()
                    if t in ("Rare", "Legendary") and p not in perks]
            if pool:
                p = rng.choice(pool)
                if p not in perks:
                    if _PERKS[p][0] == "Legendary" and used_leg:
                        pass
                    else:
                        perks.append(p)
                        if _PERKS[p][0] == "Legendary":
                            used_leg = True
        return perks

    # Alias untuk konsistensi nama baru Traits
    _roll_traits = _roll_perks

    def _roll_skills(self, cls, star, rare_bonus, rng):
        """Roll 1-2 skill class + 0-3 skill universal untuk hero."""
        return roll_random_skills(cls, star, rare_bonus, rng)

    def _roll_stats(self, cls, star, rng):
        """Roll base_stats, growth_stats, dan mp_regen acak untuk hero
        sesuai class (minimum stat dasar) dan star (bobot persentase)."""
        return (
            roll_random_base_stats(cls, star, rng),
            roll_random_growth_stats(star, rng),
            roll_random_mp_regen(star, rng),
        )

    def create(self, star, cls=None, rng=None):
        """Buat hero unik dari data database. Return instance Hero.
        Setiap hero memiliki stat dasar, growth, mp_regen, traits (1-3),
        dan skills (1-2 class skill + 0-3 universal skill) yang unik."""
        rng = rng or random
        if cls is None or cls not in _CLASS_STATS:
            cls = self.roll_class(rng)
        star = max(1, min(MAX_STAR, int(star)))
        rare_extra = False
        if star == 1:
            gm, rare_extra = self._roll_hidden(rng)
        else:
            # Hero 5-star pasti kuat: GM > 1 + jaminan trait/skill bagus
            gm = 1.0
            if star >= 5:
                gm = rng.uniform(1.1, 1.4)
        for _ in range(self.MAX_TRY):
            first, last, title = self._roll_name(rng)
            # 65% pakai polos (tanpa gelar) bila baris DB punya gelar
            if title and rng.random() >= 0.35:
                title = None
            name = "%s %s" % (first, last)
            if title:
                name += " the %s" % title
            if name in self.names:
                continue  # nama sudah dipakai hero lain -> regenerasi
            traits = self._roll_traits(star, rare_extra, rng)
            skills = self._roll_skills(cls, star, rare_extra, rng)
            b_stats, g_stats, mpr = self._roll_stats(cls, star, rng)
            hero = Hero(name, star, cls, 1, gm, traits,
                        skills=skills, base_stats=b_stats,
                        growth_stats=g_stats, mp_regen_val=mpr)
            fp = hero.fingerprint()
            if fp not in self.fingerprints:
                self.fingerprints.add(fp)
                self.names.add(name)
                return hero
        # Fallback extrem: gelar ganda + suffix serial deterministik agar
        # selalu unik — roster di-key by name, nama duplikat = hero tertimpa.
        base_f, base_l, base_t = self._roll_name(rng)
        for i in range(100, 100000):
            name = "%s %s the %s [%d]" % (base_f, base_l, base_t or "Wandering", i)
            if name in self.names:
                continue
            traits = self._roll_traits(star, rare_extra, rng)
            skills = self._roll_skills(cls, star, rare_extra, rng)
            b_stats, g_stats, mpr = self._roll_stats(cls, star, rng)
            hero = Hero(name, star, cls, 1, gm, traits,
                        skills=skills, base_stats=b_stats,
                        growth_stats=g_stats, mp_regen_val=mpr)
            self.fingerprints.add(hero.fingerprint())
            self.names.add(name)
            return hero

    def roll_class(self, rng=None):
        """Class di-roll dari bobot tabel class_stats (database).
        Mage diberi bobot 3 vs 20 class lain -> ~3% dari total roll."""
        rng = rng or random
        pairs = [(c, _CLASS_STATS[c]["gacha_weight"]) for c in CLASSES]
        return weighted_choice(pairs, rng)


# =========================== GACHA SYSTEM ===========================
class GachaSystem:
    """Gacha 1x/10x. Rates: 1S 84.9%, 2S 10%, 3S 4%, 4S 1%, 5S 0.1%.
    Mage ~3% dari total roll (bobot class dari database)."""
    RATES = GACHA_RATES
    PRICE_COINS = PRICE_COINS
    PRICE_GEMS = PRICE_GEMS

    def __init__(self, hero_gen):
        self.gen = hero_gen

    def roll_star(self, rng=None):
        return weighted_choice([(s, w) for s, w in GACHA_RATES], rng)

    def roll_class(self, star=None, rng=None):
        """Class dicek terpisah dari star agar probabilitas Mage = 3% GLOBAL."""
        return self.gen.roll_class(rng)

    def price_coins(self, n):
        return PRICE_COINS.get(n, n * 500)

    def price_gems(self, n):
        return PRICE_GEMS.get(n, n)

    def pull(self, state):
        """Satu pull: cek biaya -> generate hero unik -> simpan ke roster.
        Return (hero | None, pesan)."""
        cost_c = self.price_coins(1)
        cost_g = self.price_gems(1)
        if state["coins"] >= cost_c:
            state["coins"] -= cost_c
        elif state["gems"] >= cost_g:
            state["gems"] -= cost_g
        else:
            return None, "Coins/Gems tidak cukup! (butuh %d coins atau %d gem)" % (cost_c, cost_g)
        star = self.roll_star()
        hero = self.gen.create(star)
        state["roster"][hero.name] = hero.to_dict()   # roster menyimpan dict
        return hero, None

    def pull_multi(self, state, n):
        """Pull n kali sekaligus. Berhenti saat dana habis (tidak crash)."""
        heroes, msgs = [], []
        for i in range(n):
            h, err = self.pull(state)
            if h:
                heroes.append(h)
            elif err:
                msgs.append(err)
                break
        return heroes, msgs
