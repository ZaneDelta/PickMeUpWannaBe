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
# Ranking numerik tier internal (urutan kekuatan trait/skill). RAHASIA:
# hanya untuk logika internal (roll, Hero Synthesis), TIDAK ditampilkan di UI.
TIER_RANK = {"Common": 0, "Rare": 1, "Epic": 2, "Legendary": 3}
# Harga gacha (coins / gems)
PRICE_COINS = {1: 500, 10: 4500}
PRICE_GEMS = {1: 1, 10: 9}

MAX_LEVEL = 99
MAX_STAR = 7

# Cache data database dimuat SEKALI di import (statistik tidak berubah
# saat runtime; menghemat ribuan query per battle).
_CLASS_STATS = db.load_class_stats()
_STAR_MULTS = db.load_star_mults()
_TRAITS = db.load_traits()
_PERKS = _TRAITS
_SKILLS = db.load_skills()
_ITEMS = db.load_items()

get_overload_success_rate = db.get_overload_success_rate
HERO_SELL_CONFIG = getattr(db, "HERO_SELL_CONFIG", {})

CLASSES = list(_CLASS_STATS.keys()) if _CLASS_STATS else \
    ["Tanker", "Dealer", "Archer", "Healer", "Buffer", "Mage"]


def reload_db_data():
    """Paksa muat ulang cache dari database (mis. setelah re-seed manual)."""
    global _CLASS_STATS, _STAR_MULTS, _TRAITS, _PERKS, _SKILLS, _ITEMS, CLASSES
    _CLASS_STATS = db.load_class_stats()
    _STAR_MULTS = db.load_star_mults()
    _TRAITS = db.load_traits()
    _PERKS = _TRAITS
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


def _clamp_float(v, default, lo, hi):
    """Float aman dari save: gagal diparse -> default; hasil diklem [lo, hi]."""
    try:
        x = float(v)
    except Exception:
        return default
    return max(lo, min(hi, x))


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
class AbilityTag(str):
    """Subclass `str` yang tetap 100% kompatibel sebagai string nama skill/trait
    (untuk equality `==`, `in`, `join`, JSON dump, dsb.) SEKALIGUS mendukung
    akses dict-like (`.get("cursed")`, `["cursed"]`, `"cursed" in item`) untuk
    atribut metadata seperti `cursed`, `name`, `tier`, dan `description`."""

    def __new__(tag_type, name, cursed=False, tier="Common", description="", **extra):
        if isinstance(name, dict):
            cursed = bool(name.get("cursed", cursed))
            tier = str(name.get("tier", tier))
            description = str(name.get("description", name.get("desc", description)))
            extra_copy = {k: v for k, v in name.items()
                          if k not in ("name", "cursed", "tier", "description", "desc")}
            extra_copy.update(extra)
            extra = extra_copy
            name = str(name.get("name", ""))
        elif isinstance(name, AbilityTag):
            cursed = bool(getattr(name, "cursed", cursed))
            tier = str(getattr(name, "tier", tier))
            description = str(getattr(name, "description", description))
            extra_copy = dict(getattr(name, "_extra", {}))
            extra_copy.update(extra)
            extra = extra_copy
            name = str(name)
        obj = super().__new__(tag_type, str(name))
        obj.cursed = bool(cursed)
        obj.tier = str(tier)
        obj.description = str(description)
        obj.desc = obj.description
        obj._extra = dict(extra)
        return obj

    def _meta_dict(self):
        d = {
            "name": str(self),
            "cursed": bool(self.cursed),
            "tier": self.tier,
            "description": self.description,
            "desc": self.description,
        }
        d.update(self._extra)
        return d

    def get(self, key, default=None):
        return self._meta_dict().get(key, default)

    def __getitem__(self, key):
        if isinstance(key, str):
            m = self._meta_dict()
            if key in m:
                return m[key]
            raise KeyError(key)
        return super().__getitem__(key)

    def __contains__(self, item):
        if item in ("name", "cursed", "tier", "description", "desc") or item in self._extra:
            return True
        return super().__contains__(item)

    def keys(self):
        return self._meta_dict().keys()

    def items(self):
        return self._meta_dict().items()

    def values(self):
        return self._meta_dict().values()

    def to_dict(self):
        return self._meta_dict()


def _extract_ability_name(item):
    if isinstance(item, dict):
        return str(item.get("name", ""))
    if hasattr(item, "name") and not isinstance(item, str):
        return str(item.name)
    return str(item or "")


def _is_cursed_trait(item):
    if isinstance(item, dict) and "cursed" in item:
        return bool(item.get("cursed"))
    if isinstance(item, AbilityTag):
        return bool(item.cursed)
    if hasattr(item, "cursed") and not isinstance(item, str):
        return bool(item.cursed)
    nm = _extract_ability_name(item)
    if nm in db.CURSED_TRAITS_POOL:
        return True
    t_info = _TRAITS.get(nm)
    return bool(t_info and t_info[0] == "Cursed")


def _is_cursed_skill(item):
    if isinstance(item, dict) and "cursed" in item:
        return bool(item.get("cursed"))
    if isinstance(item, AbilityTag):
        return bool(item.cursed)
    if hasattr(item, "cursed") and not isinstance(item, str):
        return bool(item.cursed)
    nm = _extract_ability_name(item)
    if nm in db.CURSED_SKILLS_POOL:
        return True
    s_info = _SKILLS.get(nm)
    if s_info:
        return bool(s_info.get("cursed", False) or s_info.get("tier") == "Cursed"
                    or str(s_info.get("kind", "")).startswith("cursed_"))
    return False


def _make_trait_tag(item):
    nm = _extract_ability_name(item)
    t_info = _TRAITS.get(nm, ("Common", "Tanpa efek"))
    tier = t_info[0]
    desc = t_info[1]
    cursed = _is_cursed_trait(item)
    if isinstance(item, dict):
        tier = str(item.get("tier", tier))
        desc = str(item.get("description", item.get("desc", desc)))
    return AbilityTag(nm, cursed=cursed, tier=tier, description=desc)


def _make_skill_tag(item):
    nm = _extract_ability_name(item)
    s_info = _SKILLS.get(nm) or {
        "cls": "Universal", "tier": "Common", "mp_cost": 15, "cd": 3,
        "kind": "single", "mult": 1.5, "description": "Skill", "cursed": False,
    }
    cursed = _is_cursed_skill(item)
    tier = str(s_info.get("tier", "Common"))
    desc = str(s_info.get("description", "Skill"))
    extra = {
        "cls": s_info.get("cls", "Universal"),
        "mp_cost": int(s_info.get("mp_cost", 15)),
        "cd": int(s_info.get("cd", 3)),
        "kind": s_info.get("kind", "single"),
        "mult": float(s_info.get("mult", 1.5)),
    }
    if isinstance(item, dict):
        tier = str(item.get("tier", tier))
        desc = str(item.get("description", item.get("desc", desc)))
        for k in ("cls", "mp_cost", "cd", "kind", "mult"):
            if k in item:
                extra[k] = item[k]
    return AbilityTag(nm, cursed=cursed, tier=tier, description=desc, **extra)


class Trait:
    """Representasi trait (data dari tabel traits di database).
    RAHASIA: tier normal hanya dipakai internal saat roll, TIDAK ditampilkan di UI."""

    def __init__(self, name):
        nm = _extract_ability_name(name)
        self.name = nm
        tier, desc = _TRAITS.get(nm, ("Common", "Tanpa efek"))
        self.tier = tier
        self.desc = desc
        self.description = desc
        self.cursed = _is_cursed_trait(name)

    def get(self, key, default=None):
        return self.to_dict().get(key, default)

    def __getitem__(self, key):
        return self.to_dict()[key]

    def to_dict(self):
        return {
            "name": self.name,
            "tier": self.tier,
            "description": self.desc,
            "desc": self.desc,
            "cursed": bool(self.cursed),
        }

    @staticmethod
    def all_names(include_cursed=False):
        if include_cursed:
            return list(_TRAITS.keys())
        return [k for k in _TRAITS.keys() if not _is_cursed_trait(k)]

    @staticmethod
    def tier_of(name):
        return _TRAITS.get(_extract_ability_name(name), ("Common", ""))[0]


# Alias backward-compatibility
Perk = Trait


class Skill:
    """Representasi skill (data dari tabel skills di database).
    Pool terdiri dari 30 skill per class (6x30=180) + 60 skill Universal (total 240)
    + 15 Cursed Skills (khusus kegagalan Soul Overload).
    RAHASIA: tier skill normal hanya untuk bobot roll, TIDAK ditampilkan di UI."""

    def __init__(self, name):
        nm = _extract_ability_name(name)
        self.name = nm
        info = _SKILLS.get(nm) or {
            "cls": "Universal", "tier": "Common", "mp_cost": 15, "cd": 3,
            "kind": "single", "mult": 1.5, "description": "Skill", "cursed": False,
        }
        self.cls = info.get("cls", "Universal")
        self.tier = info["tier"]
        self.mp_cost = info["mp_cost"]
        self.cd = info["cd"]
        self.kind = info["kind"]
        self.mult = info["mult"]
        self.desc = info["description"]
        self.description = info["description"]
        self.cursed = _is_cursed_skill(name)

    def get(self, key, default=None):
        return self.to_dict().get(key, default)

    def __getitem__(self, key):
        return self.to_dict()[key]

    def to_dict(self):
        return {
            "name": self.name,
            "cls": self.cls,
            "tier": self.tier,
            "mp_cost": self.mp_cost,
            "cd": self.cd,
            "kind": self.kind,
            "mult": self.mult,
            "description": self.desc,
            "desc": self.desc,
            "cursed": bool(self.cursed),
        }

    @staticmethod
    def all_names(include_cursed=False):
        if include_cursed:
            return list(_SKILLS.keys())
        return [k for k in _SKILLS.keys() if not _is_cursed_skill(k)]

    @staticmethod
    def info_of(name):
        return _SKILLS.get(_extract_ability_name(name))


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
    Jumlah & kualitas bergantung pada keberuntungan (TIER_WEIGHT).
    PENTING: Cursed skills (cursed == True) TIDAK PERNAH masuk pool gacha normal."""
    rng = rng or random
    if hero_cls not in _CLASS_STATS:
        hero_cls = "Dealer"
    cls_pool = {
        s: info for s, info in _SKILLS.items()
        if info.get("cls") == hero_cls
        and not info.get("cursed", False)
        and info.get("tier") != "Cursed"
    }
    uni_pool = {
        s: info for s, info in _SKILLS.items()
        if info.get("cls") == "Universal"
        and not info.get("cursed", False)
        and info.get("tier") != "Cursed"
    }

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

    return [_make_skill_tag(s) for s in (cls_skills + uni_skills)]


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
                 mp_regen_val=None, traits=None,
                 sanity=100.0, ego=50.0, synth_count=0, absorbed_souls=0):
        self.name = name
        self.star = int(star)
        self.cls = cls
        self.hero_class = cls
        self.level = max(1, int(level))
        self.xp = 0
        self.growth_multiplier = float(growth_multiplier)
        raw_traits = traits if traits is not None else perks
        self.traits = [_make_trait_tag(t) for t in (raw_traits or [])]
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
        valid_skills = []
        for s in (skills or []):
            s_tag = _make_skill_tag(s)
            if str(s_tag) in _SKILLS:
                valid_skills.append(s_tag)
        self.skills = valid_skills if valid_skills else roll_random_skills(self.cls, self.star)
        self.equipment = {"Senjata": None, "Zirah": None, "Aksesori": None}
        self.alive = True
        self.blueprints = 0
        # --- Hero Synthesis (Tahap 1): kondisi jiwa & kapasitas vessel ---
        # sanity         : kondisi mental 0.0-100.0 (berkurang saat mensintesis)
        # ego            : kekuatan ego jiwa 10.0-100.0 (RAHASIA — internal saja,
        #                  TIDAK pernah ditampilkan di UI)
        # synth_count    : jumlah sintesis pada star saat ini (direset saat
        #                  promote_star -> kapasitas vessel baru di star lebih tinggi)
        # absorbed_souls : total tumbal yang pernah diserap (kumulatif permanen)
        self.sanity = _clamp_float(sanity, 100.0, 0.0, 100.0)
        self.ego = _clamp_float(ego, 50.0, 10.0, 100.0)
        self.synth_count = max(0, _safe_int(synth_count, 0))
        self.absorbed_souls = max(0, _safe_int(absorbed_souls, 0))
        # Battle state (direset tiap battle oleh BattleEngine)
        self.hp = self.max_hp
        self.mana = 0.0
        self.taunt_turns = 0     # ronde tersisa musuh dipaksa menarget hero ini
        self.buff_atk = 0        # % buff/debuff ATK
        self.buff_def = 0        # % buff/debuff DEF
        self.buff_spd = 0        # % buff/debuff SPD
        self.zero_def_turns = 0  # ronde tersisa DEF = 0 (Flesh Sacrifice)
        self.cursed_aura_active = False  # aktif bila ada rekan party lain ber-trait Cursed Aura
        self.stun_turns = 0
        self.skill_cd = {}       # {nama_skill: sisa cooldown}
        self.used_last_stand = False
        self.used_phoenix = False
        self.last_hit_by = None  # nama musuh terakhir yang memukul (untuk log)
        self.refresh()

    @property
    def perks(self):
        """Alias kompatibilitas mundur: mengarah langsung ke list self.traits."""
        return self.traits

    @perks.setter
    def perks(self, val):
        self.traits[:] = [_make_trait_tag(t) for t in (val or [])]

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
        return (
            self.name,
            b,
            g,
            tuple(sorted(str(t) for t in self.traits)),
            tuple(sorted(str(s) for s in self.skills)),
        )

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
        """Hitung MP cost efektif setelah trait pengurang/pelipat biaya MP."""
        cost = float(base_cost)
        if self.has("Spell Weaver"):
            cost *= 0.85
        if self.has("Infinite Mana"):
            cost *= 0.80
        if self.has("Mana Parasite"):
            cost *= 2.0
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
        # Hero Synthesis: star baru = kapasitas vessel baru. Hitungan
        # sintesis direset agar hero mendapat ruang kapasitas penuh
        # pada bintang yang lebih tinggi (VESSEL_CAP_BY_STAR star baru).
        self.synth_count = 0
        self.refresh()

    def can_inherit_skill(self, skill_obj):
        """Validasi skill boleh diwariskan ke hero ini saat Hero Synthesis.
        Aturan yang ditegakkan (TANPA batasan jumlah skill):
          1. Duplikasi nama skill TIDAK boleh (hero sudah memilikinya -> False).
          2. Skill berjenis 'taunt' (provokasi/aggro — seluruh pool Tanker)
             HANYA boleh dimiliki class Tanker dan TIDAK PERNAH bisa
             diwariskan ke class lain.
          3. Cursed Skill (cursed == True) TIDAK BISA diwariskan lewat jalur
             pewarisan normal (hanya muncul dari kegagalan Soul Overload).
          4. Skill tidak dikenal (tidak ada di tabel skills) -> False.
        skill_obj: instance Skill, dict, ATAU string nama skill. Return bool."""
        if isinstance(skill_obj, dict):
            sk_name = str(skill_obj.get("name", ""))
            if skill_obj.get("cursed", False):
                return False
            sk = Skill(sk_name)
        elif isinstance(skill_obj, str):
            if getattr(skill_obj, "cursed", False):
                return False
            sk = Skill(str(skill_obj))
        elif isinstance(skill_obj, Skill):
            sk = skill_obj
        else:
            return False
        if sk.name in self.skills:
            return False   # cegah duplikasi nama skill
        info = _SKILLS.get(sk.name)
        if not info:
            return False   # skill tidak dikenal -> tidak valid
        if sk.cursed or info.get("cursed", False) or info.get("tier") == "Cursed":
            return False   # Cursed Skill tidak bisa diwariskan
        if sk.kind == "taunt" and self.cls != "Tanker":
            return False   # Taunt/aggro HANYA untuk class Tanker
        return True

    def can_inherit_trait(self, trait_obj):
        """Validasi trait boleh diwariskan ke hero ini saat Hero Synthesis
        (TANPA batasan jumlah trait dan TANPA batasan jumlah Legendary):
          1. Duplikasi nama trait TIDAK boleh.
          2. Cursed Trait (cursed == True) TIDAK BISA diwariskan lewat jalur
             pewarisan normal (hanya muncul dari kegagalan Soul Overload).
          3. Trait harus ada di tabel traits."""
        if isinstance(trait_obj, dict):
            tr_name = str(trait_obj.get("name", ""))
            if trait_obj.get("cursed", False):
                return False
            tr = Trait(tr_name)
        elif isinstance(trait_obj, str):
            if getattr(trait_obj, "cursed", False):
                return False
            tr = Trait(str(trait_obj))
        elif isinstance(trait_obj, Trait):
            tr = trait_obj
        else:
            return False
        if tr.name in self.traits:
            return False
        if tr.name not in _TRAITS:
            return False
        if tr.cursed or _is_cursed_trait(tr.name):
            return False
        return True

    def try_inherit_trait(self, new_trait_obj):
        """Wariskan trait ke hero saat Hero Synthesis (No-Cap System):
          - TANPA batasan jumlah trait (bisa menumpuk 4, 5, 10+ traits).
          - TANPA batasan maksimal 1 trait Legendary saat sintesis.
          - Duplikat nama trait ditolak.
          - Cursed Trait (cursed == True) ditolak dari jalur pewarisan normal.
        new_trait_obj: instance Trait, dict, ATAU string nama trait.
        Return (ok: bool, pesan: str)."""
        if isinstance(new_trait_obj, dict):
            tr_name = str(new_trait_obj.get("name", ""))
            is_cursed = bool(new_trait_obj.get("cursed", False))
        elif isinstance(new_trait_obj, Trait):
            tr_name = new_trait_obj.name
            is_cursed = new_trait_obj.cursed
        elif isinstance(new_trait_obj, str):
            tr_name = str(new_trait_obj)
            is_cursed = bool(getattr(new_trait_obj, "cursed", False))
        else:
            return False, "Trait tidak valid."
        if not tr_name or tr_name not in _TRAITS:
            return False, "Trait tidak dikenal."
        if is_cursed or _is_cursed_trait(tr_name):
            return False, "Cursed Trait tidak dapat diwariskan."
        if tr_name in self.traits:
            return False, "Trait '%s' sudah dimiliki." % tr_name
        self.traits.append(_make_trait_tag(tr_name))
        return True, "Trait '%s' diwariskan (total %d trait)." % (tr_name, len(self.traits))

    def clamp_stats(self):
        """Klem stat hero ke batas atas master (STAT_BASE_MAX & batas atas
        STAT_GROWTH_RANGE), dengan lantai keamanan positif (1.0 untuk base_stats
        dan 0.01 untuk growth_stats) TANPA memaksa naik ke STAT_BASE_MIN_BY_CLASS
        agar vessel yang rusak akibat kegagalan Soul Overload tetap menyimpan
        stat yang hancur."""
        maxs = db.STAT_BASE_MAX
        keys = db.STAT_KEYS
        decs_b = (1, 1, 1, 2, 1)
        decs_g = (2, 2, 2, 3, 2)
        new_b = []
        new_g = []
        for i, k in enumerate(keys):
            new_b.append(round(max(1.0, min(maxs[k], float(self.base_stats[i]))), decs_b[i]))
            _, g_hi = db.STAT_GROWTH_RANGE[k]
            new_g.append(round(max(0.01, min(g_hi, float(self.growth_stats[i]))), decs_g[i]))
        self.base_stats = tuple(new_b)
        self.growth_stats = tuple(new_g)
        return self.base_stats, self.growth_stats

    def vessel_cap(self):
        """Batas aman jumlah sintesis pada bintang saat ini (master data)."""
        caps = db.SYNTHESIS_CONFIG["VESSEL_CAP_BY_STAR"]
        s = max(1, min(MAX_STAR, int(self.star)))
        return int(caps.get(s, 3))

    def get_overload_success_rate(self):
        """Peluang keberhasilan sintesis (RAHASIA — tidak ditampilkan di UI):
        1.0 selama synth_count < vessel_cap, dan menurun drastis mengikuti
        OVERLOAD_SUCCESS_CURVE saat melampaui kapasitas vessel."""
        return db.get_overload_success_rate(self.synth_count, self.vessel_cap())

    def mental_status_label(self):
        """Deskripsi kondisi mental hero berdasarkan sanity (tanpa bocoran angka rahasia)."""
        if self.sanity >= 80.0:
            return "Stabil"
        if self.sanity >= 40.0:
            return "Gelisah"
        return "Retak / Kritis"

    def synthesize_with(self, material_hero, rng=None):
        """Proses inti Hero Synthesis antara self (Hero Wadah/Base) dan
        material_hero (Hero Tumbal/Material) memakai konstanta SYNTHESIS_CONFIG.
        Menangani:
          1. Ego Override / Reverse Absorption (kasus Han Islat)
          2. Soul Overload Curve & Vessel Breakdown saat melampaui VESSEL_CAP_BY_STAR
          3. Cabang GAGAL Overload: decay stat & GM 30%-99% (tanpa batas min class),
             60% kehancuran tiap skill/trait non-cursed, 50% infeksi Cursed Skill &
             50% infeksi Cursed Trait, serta penalti sanity 3.0x
          4. Cabang BERHASIL (Normal maupun Overload Sukses): pewarisan Skill & Trait
             tanpa batas (Full Inherit / Individual Roll), sistem Resonansi
             ('full' / 'partial' / 'normal') tanpa potongan 85%, transfer XP,
             serta pengurangan sanity (1.0x normal / 1.5x overload sukses)
        Return dict ringkasan lengkap hasil sintesis."""
        if material_hero is self:
            raise ValueError("Hero tidak dapat disintesis dengan dirinya sendiri.")
        rng = rng or random
        cfg = db.SYNTHESIS_CONFIG

        # 1) Cek Ego Override / Reverse Absorption (RAHASIA)
        ego_ratio_req = float(cfg["EGO_OVERRIDE_RATIO"])
        ego_override = False
        if material_hero.ego >= self.ego * ego_ratio_req:
            override_chance = min(
                0.85,
                max(0.05, 0.25 + (material_hero.ego - self.ego) / 100.0),
            )
            if rng.random() < override_chance:
                ego_override = True

        if ego_override:
            survivor = material_hero
            deceased = self
        else:
            survivor = self
            deceased = material_hero

        # 2) Cek Kapasitas Vessel & Roll Keberhasilan Soul Overload
        cap = survivor.vessel_cap()
        overload = survivor.synth_count >= cap
        success_rate = survivor.get_overload_success_rate()
        if overload:
            overload_success = (rng.random() < success_rate)
        else:
            overload_success = True
        overload_failed = not overload_success

        dec_star = max(1, min(MAX_STAR, int(deceased.star)))
        sur_star = max(1, min(MAX_STAR, int(survivor.star)))
        decs_b = (1, 1, 1, 2, 1)
        decs_g = (2, 2, 2, 3, 2)

        inherited_skills = []
        inherited_traits = []
        broken_skills = []
        broken_traits = []
        gained_cursed_skills = []
        gained_cursed_traits = []

        # =====================================================================
        # CABANG A: SOUL OVERLOAD GAGAL (VESSEL BREAKDOWN)
        # =====================================================================
        if overload_failed:
            level_before = survivor.level
            level_after = survivor.level
            xp_gain = 0
            resonance = "failed"

            old_b = tuple(survivor.base_stats)
            old_g = tuple(survivor.growth_stats)
            old_gm = float(survivor.growth_multiplier)

            decay_lo, decay_hi = cfg.get("OVERLOAD_FAIL_STAT_DECAY_RANGE", (0.30, 0.99))
            decayed_b = []
            decayed_g = []
            for i in range(len(db.STAT_KEYS)):
                drop_b = rng.uniform(decay_lo, decay_hi)
                val_b = max(1.0, round(old_b[i] * (1.0 - drop_b), decs_b[i]))
                decayed_b.append(val_b)

                drop_g = rng.uniform(decay_lo, decay_hi)
                val_g = max(0.01, round(old_g[i] * (1.0 - drop_g), decs_g[i]))
                decayed_g.append(val_g)

            survivor.base_stats = tuple(decayed_b)
            survivor.growth_stats = tuple(decayed_g)
            survivor.clamp_stats()

            drop_gm = rng.uniform(decay_lo, decay_hi)
            survivor.growth_multiplier = max(0.01, round(old_gm * (1.0 - drop_gm), 4))

            stat_gains = {
                k: round(survivor.base_stats[i] - old_b[i], decs_b[i])
                for i, k in enumerate(db.STAT_KEYS)
            }
            growth_gains = {
                k: round(survivor.growth_stats[i] - old_g[i], decs_g[i])
                for i, k in enumerate(db.STAT_KEYS)
            }

            # Kehancuran Skill & Trait non-cursed (peluang 60% per item)
            destroy_rate = float(cfg.get("OVERLOAD_FAIL_ABILITY_DESTROY_RATE", 0.60))
            kept_skills = []
            for sk in list(survivor.skills):
                if not _is_cursed_skill(sk) and rng.random() < destroy_rate:
                    broken_skills.append(_make_skill_tag(sk))
                else:
                    kept_skills.append(_make_skill_tag(sk))
            survivor.skills[:] = kept_skills

            kept_traits = []
            for tr in list(survivor.traits):
                if not _is_cursed_trait(tr) and rng.random() < destroy_rate:
                    broken_traits.append(_make_trait_tag(tr))
                else:
                    kept_traits.append(_make_trait_tag(tr))
            survivor.traits[:] = kept_traits

            # Infeksi Cursed Skill (50%) & Cursed Trait (50%)
            cursed_sk_rate = float(cfg.get("CURSED_SKILL_GAIN_RATE", 0.50))
            if rng.random() < cursed_sk_rate:
                c_sk_pool = [
                    s["name"] for s in db.get_cursed_skills()
                    if s["name"] not in survivor.skills
                ]
                if c_sk_pool:
                    chosen_c_sk = _make_skill_tag(rng.choice(c_sk_pool))
                    survivor.skills.append(chosen_c_sk)
                    gained_cursed_skills.append(chosen_c_sk)

            cursed_tr_rate = float(cfg.get("CURSED_TRAIT_GAIN_RATE", 0.50))
            if rng.random() < cursed_tr_rate:
                c_tr_pool = [
                    t["name"] for t in db.get_cursed_traits()
                    if t["name"] not in survivor.traits
                ]
                if c_tr_pool:
                    chosen_c_tr = _make_trait_tag(rng.choice(c_tr_pool))
                    survivor.traits.append(chosen_c_tr)
                    gained_cursed_traits.append(chosen_c_tr)

            # Penalti Sanity Ekstrem (3.0x) & Update Counter
            drain_base = float(cfg["SANITY_DRAIN_BASE"])
            ego_factor = float(deceased.ego) / max(10.0, float(survivor.ego))
            fail_mult = float(cfg.get("OVERLOAD_FAIL_SANITY_MULT", 3.0))
            raw_sanity_loss = drain_base * dec_star * ego_factor * fail_mult
            sanity_loss = round(max(1.0, raw_sanity_loss), 1)
            survivor.sanity = max(0.0, min(100.0, round(survivor.sanity - sanity_loss, 1)))
            survivor.synth_count += 1
            survivor.absorbed_souls += 1 + max(0, int(deceased.absorbed_souls))
            deceased.alive = False
            survivor.refresh()

            return {
                "survivor": survivor,
                "deceased": deceased,
                "ego_override": ego_override,
                "overload": overload,
                "overload_success": False,
                "overload_failed": True,
                "resonance": resonance,
                "level_before": level_before,
                "level_after": level_after,
                "xp_gain": xp_gain,
                "stat_gains": stat_gains,
                "growth_gains": growth_gains,
                "inherited_skills": inherited_skills,
                "inherited_traits": inherited_traits,
                "broken_skills": broken_skills,
                "broken_traits": broken_traits,
                "gained_cursed_skills": gained_cursed_skills,
                "gained_cursed_traits": gained_cursed_traits,
                "sanity_loss": sanity_loss,
            }

        # =====================================================================
        # CABANG B: SINTESIS BERHASIL (NORMAL MAUPUN OVERLOAD SUKSES)
        # =====================================================================
        # 3) Transfer XP & Kenaikan Level (40%-60% dari akumulasi XP/level tumbal)
        acc_xp = sum(
            int(round(40 * (lv ** 1.5))) for lv in range(1, max(1, int(deceased.level)))
        ) + max(0, int(deceased.xp))
        base_soul_xp = 30 * max(1, int(deceased.star))
        xp_rate = rng.uniform(0.40, 0.60)
        xp_gain = max(1, int(round((acc_xp + base_soul_xp) * xp_rate)))
        level_before = survivor.level
        survivor.gain_xp(xp_gain)
        level_after = survivor.level

        # 4) Pewarisan Skill & Trait Tanpa Batas (No-Cap) + Evaluasi Resonansi
        valid_skill_cands = [sk for sk in deceased.skills if survivor.can_inherit_skill(sk)]
        valid_trait_cands = [tr for tr in deceased.traits if survivor.can_inherit_trait(tr)]
        total_valid_cands = len(valid_skill_cands) + len(valid_trait_cands)

        full_inherit_map = cfg.get("FULL_INHERIT_RATE_BY_STAR", {})
        full_inherit_prob = float(full_inherit_map.get(dec_star, 0.10))

        if total_valid_cands > 0 and rng.random() < full_inherit_prob:
            # Full Inheritance Jackpot: warisi SEMUA skill & trait valid dari tumbal
            for sk_name in valid_skill_cands:
                if survivor.can_inherit_skill(sk_name):
                    tag_sk = _make_skill_tag(sk_name)
                    survivor.skills.append(tag_sk)
                    inherited_skills.append(tag_sk)
            for tr_name in valid_trait_cands:
                ok_tr, _ = survivor.try_inherit_trait(tr_name)
                if ok_tr:
                    inherited_traits.append(_make_trait_tag(tr_name))
        else:
            # Roll individual untuk SETIAP skill valid & SETIAP trait valid (tanpa cap)
            sk_base = float(cfg.get("SINGLE_SKILL_INHERIT_BASE", 0.35))
            tr_base = float(cfg.get("SINGLE_TRAIT_INHERIT_BASE", 0.25))
            star_bonus = float(cfg.get("INHERIT_STAR_BONUS", 0.05))
            sk_prob = min(0.95, sk_base + star_bonus * dec_star)
            tr_prob = min(0.90, tr_base + star_bonus * dec_star)

            for sk_name in valid_skill_cands:
                if survivor.can_inherit_skill(sk_name) and rng.random() < sk_prob:
                    tag_sk = _make_skill_tag(sk_name)
                    survivor.skills.append(tag_sk)
                    inherited_skills.append(tag_sk)

            for tr_name in valid_trait_cands:
                if survivor.can_inherit_trait(tr_name) and rng.random() < tr_prob:
                    ok_tr, _ = survivor.try_inherit_trait(tr_name)
                    if ok_tr:
                        inherited_traits.append(_make_trait_tag(tr_name))

        total_inherited = len(inherited_skills) + len(inherited_traits)
        if total_valid_cands >= 1 and total_inherited == total_valid_cands:
            resonance = "full"
        elif total_inherited >= 1:
            resonance = "partial"
        else:
            resonance = "normal"

        # 5) Penyerapan base_stats, growth_stats, & Hidden Potential (GM)
        #    (TANPA potongan 85% saat overload berhasil; diperkuat oleh Resonansi)
        absorb_map = cfg["STAT_ABSORB_RATE_BY_STAR"]
        base_rate = float(absorb_map.get(dec_star, 0.25))
        if resonance == "full":
            absorb_rate = base_rate * float(cfg.get("FULL_RESONANCE_STAT_MULT", 1.50))
        elif resonance == "partial":
            absorb_rate = base_rate + float(cfg.get("PARTIAL_RESONANCE_STAT_BONUS", 0.10))
        else:
            absorb_rate = base_rate

        if dec_star < sur_star:
            absorb_rate *= 0.5 ** (sur_star - dec_star)
        eff_rate = min(1.0, absorb_rate)

        survivor.clamp_stats()
        old_b = tuple(survivor.base_stats)
        old_g = tuple(survivor.growth_stats)

        new_b_raw = []
        new_g_raw = []
        for i in range(len(db.STAT_KEYS)):
            pos_diff_b = max(0.0, float(deceased.base_stats[i]) - old_b[i])
            frac_b = float(deceased.base_stats[i]) * 0.12
            gain_b = (pos_diff_b * 0.65 + frac_b) * eff_rate
            new_b_raw.append(old_b[i] + gain_b)

            pos_diff_g = max(0.0, float(deceased.growth_stats[i]) - old_g[i])
            frac_g = float(deceased.growth_stats[i]) * 0.10
            gain_g = (pos_diff_g * 0.65 + frac_g) * eff_rate
            new_g_raw.append(old_g[i] + gain_g)

        survivor.base_stats = tuple(new_b_raw)
        survivor.growth_stats = tuple(new_g_raw)
        # Klem batas atas agar tidak pernah menembus STAT_BASE_MAX / STAT_GROWTH_RANGE
        survivor.clamp_stats()

        stat_gains = {
            k: round(max(0.0, survivor.base_stats[i] - old_b[i]), decs_b[i])
            for i, k in enumerate(db.STAT_KEYS)
        }
        growth_gains = {
            k: round(max(0.0, survivor.growth_stats[i] - old_g[i]), decs_g[i])
            for i, k in enumerate(db.STAT_KEYS)
        }

        # Serapan rahasia GM (Hidden Potential): diam-diam, maks 2.5
        if deceased.growth_multiplier > survivor.growth_multiplier:
            gm_diff = deceased.growth_multiplier - survivor.growth_multiplier
            if resonance == "full":
                gm_share = rng.uniform(0.50, 0.75)
            else:
                gm_share = rng.uniform(0.25, 0.35)
            survivor.growth_multiplier = min(
                2.5, round(survivor.growth_multiplier + gm_diff * gm_share, 4)
            )

        # 6) Pengurangan Sanity & Update Counter
        drain_base = float(cfg["SANITY_DRAIN_BASE"])
        ego_factor = float(deceased.ego) / max(10.0, float(survivor.ego))
        sanity_mult = float(cfg.get("OVERLOAD_SUCCESS_SANITY_MULT", 1.5)) if overload else 1.0
        raw_sanity_loss = drain_base * dec_star * ego_factor * sanity_mult
        sanity_loss = round(max(1.0, raw_sanity_loss), 1)
        survivor.sanity = max(0.0, min(100.0, round(survivor.sanity - sanity_loss, 1)))
        survivor.synth_count += 1
        survivor.absorbed_souls += 1 + max(0, int(deceased.absorbed_souls))
        deceased.alive = False
        survivor.refresh()

        return {
            "survivor": survivor,
            "deceased": deceased,
            "ego_override": ego_override,
            "overload": overload,
            "overload_success": True,
            "overload_failed": False,
            "resonance": resonance,
            "level_before": level_before,
            "level_after": level_after,
            "xp_gain": xp_gain,
            "stat_gains": stat_gains,
            "growth_gains": growth_gains,
            "inherited_skills": inherited_skills,
            "inherited_traits": inherited_traits,
            "broken_skills": broken_skills,
            "broken_traits": broken_traits,
            "gained_cursed_skills": gained_cursed_skills,
            "gained_cursed_traits": gained_cursed_traits,
            "sanity_loss": sanity_loss,
        }

    def _final_stat(self, idx, use_equip=True):
        v = self._base_stat(idx)
        # Trait stat modifier
        if idx == 1:  # ATK
            if self.has("Glass Cannon"):        v *= 1.40
            if self.has("Unlucky"):             v *= 1.40
            if self.has("Chosen One"):          v *= 1.10
            if self.has("Sharp Edge"):          v *= 1.15
            if self.has("Reckless Charge"):     v *= 1.25
            if self.has("Thick Armor"):         v *= 0.90
            if self.has("Fierce Grip"):         v *= 1.12
            if self.has("Bloodthirst"):         v *= 1.20
            if self.has("Wind Runner"):         v *= 1.10
            if self.has("Precision"):           v *= 1.18
            if self.has("Warlord"):             v *= 1.22
            if self.has("Soul Harvester"):      v *= 1.20
            if self.has("Shadow Step"):         v *= 1.15
            if self.has("Godslayer"):           v *= 1.35
            if self.has("Celestial Grace"):     v *= 1.18
            if self.has("Bloodlust Masochist"): v *= 1.20  # Cursed Trait: ATK +20%
            if getattr(self, "cursed_aura_active", False):
                v *= 0.90  # Cursed Aura dari rekan party: ATK -10%
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
            if self.has("Fragile Bones"):   v *= 0.60  # Cursed Trait: DEF -40%
            if getattr(self, "cursed_aura_active", False):
                v *= 0.90  # Cursed Aura dari rekan party: DEF -10%
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
            if self.has("Fragile Bones"):   v *= 1.15  # Cursed Trait: SPD +15%
            if self.has("Severed Nerves"):  v *= 0.65  # Cursed Trait: SPD -35%
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
            v *= max(0.1, 1 + self.buff_spd / 100.0)
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
        if self.has("Cracked Vessel"):  hp *= 0.75  # Cursed Trait: Max HP -25%
        hp += self._equipment_hp()
        return max(1, int(round(hp)))

    def _equipment_hp(self):
        return sum(eq.hp for eq in self.equipment.values() if eq is not None)

    @property
    def atk(self):
        # ATK dengan buff/debuff battle (additif %, dihitung dari ATK termasuk equip)
        return max(1, int(round(self._final_stat(1) * max(0.1, 1 + self.buff_atk / 100.0))))

    @property
    def dfn(self):
        # Flesh Sacrifice membuat DEF menjadi 0 selama durasi zero_def_turns
        if getattr(self, "zero_def_turns", 0) > 0:
            return 0
        # DEF final + buff/debuff DEF battle — additif %
        return max(1, int(round(self._final_stat(2) * max(0.1, 1 + self.buff_def / 100.0))))

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
        if self.has("Leaking Soul"):
            return 0  # Cursed Trait: MP Regen menjadi 0
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
        trait_list = [_make_trait_tag(t) for t in self.traits]
        skill_list = [_make_skill_tag(s) for s in self.skills]
        return {
            "name": self.name, "star": self.star, "cls": self.cls,
            "level": self.level, "xp": self.xp,
            "growth_multiplier": self.growth_multiplier,
            "traits": trait_list,
            "perks": list(trait_list),   # dipertahankan untuk backward compatibility
            "skills": skill_list,
            "base_stats": list(self.base_stats),
            "growth_stats": list(self.growth_stats),
            "mp_regen": self.mp_regen_base,
            "equipment": {s: (e.to_dict() if e else None) for s, e in self.equipment.items()},
            "alive": self.alive,
            "hp": self.hp,   # persist wound state (Heal/Rest jadi berarti)
            "blueprints": _safe_int(getattr(self, "blueprints", 0), 0),
            # Hero Synthesis (Tahap 1): kondisi jiwa & kapasitas vessel.
            # RAHASIA: ego TIDAK boleh ditampilkan di UI pemain.
            "sanity": float(self.sanity),
            "ego": float(self.ego),
            "synth_count": int(self.synth_count),
            "absorbed_souls": int(self.absorbed_souls),
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
            gm = max(0.01, float(d.get("growth_multiplier", 1.0)))
        except Exception:
            gm = 1.0
        has_traits_key = ("traits" in d) or ("perks" in d)
        raw_traits = d.get("traits") if d.get("traits") is not None else (d.get("perks") or [])
        traits = []
        for p in (raw_traits or []):
            t_tag = _make_trait_tag(p)
            if str(t_tag) in _TRAITS:
                traits.append(t_tag)
        # RNG deterministik berbasis nama untuk migrasi save lama tanpa stat/skill acak
        mig_rng = random.Random("pmu_hero_mig::" + name)
        raw_bs = d.get("base_stats")
        if isinstance(raw_bs, (list, tuple)) and len(raw_bs) == 5:
            try:
                base_stats = tuple(max(1.0, float(x)) for x in raw_bs)
            except Exception:
                base_stats = roll_random_base_stats(hero_cls, star, mig_rng)
        else:
            base_stats = roll_random_base_stats(hero_cls, star, mig_rng)
        raw_gs = d.get("growth_stats")
        if isinstance(raw_gs, (list, tuple)) and len(raw_gs) == 5:
            try:
                growth_stats = tuple(max(0.01, float(x)) for x in raw_gs)
            except Exception:
                growth_stats = roll_random_growth_stats(star, mig_rng)
        else:
            growth_stats = roll_random_growth_stats(star, mig_rng)
        raw_mpr = d.get("mp_regen")
        mp_regen_val = _safe_int(raw_mpr, 0) if raw_mpr is not None else 0
        if mp_regen_val <= 0:
            mp_regen_val = roll_random_mp_regen(star, mig_rng)
        has_skills_key = "skills" in d and isinstance(d.get("skills"), list)
        raw_skills = d.get("skills") or []
        skills = []
        for s in raw_skills:
            s_tag = _make_skill_tag(s)
            if str(s_tag) in _SKILLS:
                skills.append(s_tag)
        if not skills and not has_skills_key:
            skills = roll_random_skills(hero_cls, star, gm >= 1.5, mig_rng)
        h = cls(name, star, hero_cls, level, gm, traits,
                skills=skills, base_stats=base_stats,
                growth_stats=growth_stats, mp_regen_val=mp_regen_val)
        if has_skills_key and not skills:
            # Jika seluruh skill hancur akibat kegagalan Soul Overload, biarkan kosong
            h.skills = []
        if has_traits_key and not traits:
            h.traits = []
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
        h.blueprints = _safe_int(d.get("blueprints"), 0)
        # Hero Synthesis (Tahap 1): default aman + normalisasi tipe untuk
        # save lama yang belum punya keempat field ini.
        h.sanity = _clamp_float(d.get("sanity"), 100.0, 0.0, 100.0)
        h.ego = _clamp_float(d.get("ego"), 50.0, 10.0, 100.0)
        h.synth_count = max(0, _safe_int(d.get("synth_count"), 0))
        h.absorbed_souls = max(0, _safe_int(d.get("absorbed_souls"), 0))
        return h

    def detail_lines(self):
        """Detail hero untuk layar Detail Hero di menu Manage Hero.
        RAHASIA:
          - hidden potential (growth_multiplier) SENGAJA tidak ditampilkan.
          - tier normal dari Traits maupun Skills (Common/Rare/Epic/Legendary)
            SENGAJA tidak ditampilkan di UI.
          - KHUSUS Cursed Skill & Cursed Trait WAJIB diberi penanda [CURSED]."""
        eqs = [e.describe() for e in self.equipment.values() if e]
        tr_parts = []
        for t in self.traits:
            if _is_cursed_trait(t):
                tr_parts.append("%s [CURSED]" % t)
            else:
                tr_parts.append(str(t))
        sk_parts = []
        for s in self.skills:
            info = _SKILLS.get(s)
            cursed_tag = " [CURSED]" if _is_cursed_skill(s) else ""
            if info:
                sk_parts.append("%s%s (%d MP, CD %d)" % (
                    s, cursed_tag, self.skill_mp_cost(info["mp_cost"]), info["cd"]))
            else:
                sk_parts.append("%s%s" % (s, cursed_tag))
        return [
            "Nama   : %s" % self.name,
            "Class  : %s  |  Star: %s  |  Level: %d  (XP %d/%d)" % (
                self.cls, "*" * self.star, self.level, self.xp, self.xp_needed()),
            "Status : %s" % ("HIDUP" if self.alive else "GUGUR"),
            "Mental : %s  |  Vessel: %d/%d  |  Jiwa Terserap: %d" % (
                self.mental_status_label(), self.synth_count,
                self.vessel_cap(), self.absorbed_souls),
            "Traits : %s" % (", ".join(tr_parts) if tr_parts else "(tidak ada)"),
            "Skills : %s" % (" | ".join(sk_parts) if sk_parts else "(tidak ada)"),
            "HP %d/%d  ATK %d  DEF %d  SPD %d  MP %d/%d  (regen %d/ronde)" % (
                self.hp, self.max_hp, self.atk, self.dfn, self.spd,
                int(self.mana), self.max_mp, self.mp_regen),
            "Rise/Lv: HP +%.2f  ATK +%.2f  DEF +%.2f  SPD +%.3f  MP +%.2f" % (
                self.growth_stats[0], self.growth_stats[1], self.growth_stats[2],
                self.growth_stats[3], self.growth_stats[4]),
            "Equip  : %s" % ("; ".join(eqs) if eqs else "(kosong)"),
            "Harga Jual: %d coins%s" % (
                self.calc_sell_price(), " [MAGE PREMIUM 3x]" if str(self.cls).strip().lower() == "mage" else ""),
        ]

    def calc_sell_breakdown(self):
        """Hitung rincian harga jual hero dalam bentuk dict breakdown:
        - star_base : Nilai dasar bintang (1★ - 7★)
        - level_val : Nilai pertumbuhan level hero
        - stat_val  : Nilai stat efektif (HP, ATK, DEF, SPD, MP)
        - traits_val: Nilai akumulasi jumlah & kelangkaan (tier) trait
        - skills_val: Nilai akumulasi jumlah & kelangkaan (tier) skill
        - subtotal  : Nilai sebelum pengali class
        - is_mage   : Apakah hero bertipe Mage
        - mage_mult : Pengali 3.0x jika Mage, 1.0x jika class lain
        - total_price: Nilai akhir dalam satuan Coins
        """
        cfg = getattr(db, "HERO_SELL_CONFIG", None) or HERO_SELL_CONFIG or {}
        star_bases = cfg.get("BASE_PRICE_BY_STAR", {1: 150, 2: 400, 3: 1000, 4: 3000, 5: 8000, 6: 20000, 7: 50000})
        star_val = int(star_bases.get(self.star, 150))

        # 1) Level scaling (linear + eksponensial halus)
        lvl_base = cfg.get("LEVEL_MULT_BASE", 25)
        lvl_factor = cfg.get("LEVEL_EXP_FACTOR", 10.0)
        lvl_power = cfg.get("LEVEL_EXP_POWER", 1.3)
        lvl_val = int(self.level * lvl_base + (self.level ** lvl_power) * lvl_factor)

        # 2) Stat scaling
        sw = cfg.get("STAT_WEIGHTS", {"hp": 0.5, "atk": 3.0, "def": 2.5, "spd": 4.0, "mp": 0.8})
        stat_val = int(
            self.max_hp * sw.get("hp", 0.5) +
            self.atk * sw.get("atk", 3.0) +
            self.dfn * sw.get("def", 2.5) +
            self.spd * sw.get("spd", 4.0) +
            self.max_mp * sw.get("mp", 0.8)
        )

        # 3) Traits (jumlah + kelangkaan tier)
        trait_cnt_val = len(self.traits) * cfg.get("COUNT_VALUE_PER_TRAIT", 100)
        trait_tier_cfgs = cfg.get("TRAIT_TIER_VALUE", {"Common": 100, "Rare": 300, "Epic": 900, "Legendary": 3000, "Cursed": -100})
        trait_tier_val = 0
        for t in self.traits:
            tier = "Common"
            if hasattr(t, "tier"):
                tier = str(t.tier)
            else:
                t_info = _TRAITS.get(str(t))
                if t_info:
                    tier = t_info[0]
            if _is_cursed_trait(t):
                tier = "Cursed"
            trait_tier_val += trait_tier_cfgs.get(tier, 100)
        traits_val = trait_cnt_val + trait_tier_val

        # 4) Skills (jumlah + kelangkaan tier)
        skill_cnt_val = len(self.skills) * cfg.get("COUNT_VALUE_PER_SKILL", 75)
        skill_tier_cfgs = cfg.get("SKILL_TIER_VALUE", {"Common": 60, "Rare": 180, "Epic": 550, "Legendary": 1800, "Cursed": -50})
        skill_tier_val = 0
        for s in self.skills:
            tier = "Common"
            if hasattr(s, "tier"):
                tier = str(s.tier)
            else:
                s_info = _SKILLS.get(str(s))
                if s_info:
                    tier = s_info.get("tier", "Common")
            if _is_cursed_skill(s):
                tier = "Cursed"
            skill_tier_val += skill_tier_cfgs.get(tier, 60)
        skills_val = skill_cnt_val + skill_tier_val

        subtotal = max(cfg.get("MIN_PRICE", 100), star_val + lvl_val + stat_val + traits_val + skills_val)

        # 5) Mage multiplier (Canon Pick Me Up: Mage sangat langka & harganya 3x lipat)
        is_mage = (str(self.cls).strip().lower() == "mage")
        mage_mult = float(cfg.get("MAGE_MULTIPLIER", 3.0)) if is_mage else 1.0

        total_price = int(round(subtotal * mage_mult))
        min_p = cfg.get("MIN_PRICE", 100) * (int(mage_mult) if is_mage else 1)
        total_price = max(min_p, total_price)

        return {
            "star_base": star_val,
            "level_val": lvl_val,
            "stat_val": stat_val,
            "traits_val": traits_val,
            "skills_val": skills_val,
            "subtotal": subtotal,
            "is_mage": is_mage,
            "mage_multiplier": mage_mult,
            "total_price": total_price,
        }

    def calc_sell_price(self):
        """Kembalikan total harga jual hero dalam satuan Coins."""
        return self.calc_sell_breakdown()["total_price"]

    def talent_label(self):
        gm = self.growth_multiplier
        if gm >= 2.0: return "A - Terpilih (%.1fx)" % gm
        if gm >= 1.5: return "B - Bakat (%.1fx)" % gm
        return "C - Normal (%.1fx)" % gm


# ========================= HERO GENERATOR =========================
class HeroGenerator:
    """Generator hero prosedural — nama & data ditarik dari SQLite.
    ATURAN UNIK: tidak ada dua hero dengan (nama, growth, traits) identik.
    Duplikat -> regenerasi (maks 200 percobaan, lalu suffix serial)."""
    MAX_TRY = 200

    def __init__(self, db_path=None):
        self.db_path = db_path
        self.fingerprints = set()   # set of (name, growth_tuple, traits_tuple)
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
        + peluang trait Rare/Legendary ekstra. Inilah kenapa 1-star bisa
        melampaui 4-star bila dirawat (star bukan batas kekuatan)."""
        if rng.random() < HIDDEN_CHANCE:
            return rng.uniform(*HIDDEN_GM_RANGE), True
        return 1.0, False

    def _roll_perks(self, star, rare_bonus, rng):
        """Roll 1-3 trait normal (pool & tier dari tabel traits di database).
        Tier: Common 60% / Rare 30% / Epic 9% / Legendary 1%.
        Max 1 Legendary per hero saat gacha normal. 5-star dijamin minimal 1 Rare+.
        PENTING: Cursed Traits (cursed == True / tier == 'Cursed') TIDAK PERNAH
        masuk pool gacha normal."""
        n = weighted_choice([(1, 50), (2, 40), (3, 10)], rng)
        n = min(3, max(1, n))  # spesifikasi gacha awal: trait per hero 1-3
        if star >= 5:
            n = max(n, 2)
        perks = []
        used_leg = False
        for _ in range(n):
            tier = weighted_choice(list(TIER_WEIGHT.items()), rng)
            if tier == "Legendary" and used_leg:
                tier = "Epic"
            pool = [
                p for p, (t, _) in _TRAITS.items()
                if t == tier and not _is_cursed_trait(p) and p not in perks
            ]
            if not pool:
                continue
            perks.append(_make_trait_tag(rng.choice(pool)))
            if tier == "Legendary":
                used_leg = True
        if star >= 5 and len(perks) < 3 and not any(
                _TRAITS[p][0] in ("Rare", "Epic", "Legendary") for p in perks):
            pool = [
                p for p, (t, _) in _TRAITS.items()
                if t == "Rare" and not _is_cursed_trait(p) and p not in perks
            ]
            if pool:
                perks.append(_make_trait_tag(rng.choice(pool)))
        if rare_bonus and len(perks) < 3 and rng.random() < 0.5:
            pool = [
                p for p, (t, _) in _TRAITS.items()
                if t in ("Rare", "Legendary") and not _is_cursed_trait(p) and p not in perks
            ]
            if pool:
                p = rng.choice(pool)
                if p not in perks:
                    if _TRAITS[p][0] == "Legendary" and used_leg:
                        pass
                    else:
                        perks.append(_make_trait_tag(p))
                        if _TRAITS[p][0] == "Legendary":
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

    def _roll_ego(self, cls, star, traits, hidden=False, rng=None):
        """Roll kekuatan EGO jiwa hero (RAHASIA — hanya dipakai internal
        Hero Synthesis, TIDAK PERNAH ditampilkan di UI pemain).
        Pondasi mekanik: ego menentukan siapa memakan siapa saat sintesis
        (Reverse Absorption / Ego Override, ambang EGO_OVERRIDE_RATIO).
        Formula:
          dasar     : 24.0 + 6.0 * star (1★=30.0 .. 7★=66.0)
          trait     : +2.0 per tingkat tier internal trait (Common..Legendary),
                      +8.0 ekstra per trait Legendary
          hidden    : 1★ dengan Hidden Potential (GM 1.5-2.5x) -> LONJAKAN
                      80.0-98.0 (canon: jiwa kecil berbakat bisa melahap
                      tuan rumahnya saat sintesis)
          noise     : ±5.0 (karakter jiwa unik per individu)
        Hasil diklem rentang ego 10.0-100.0."""
        rng = rng or random
        s = max(1, min(MAX_STAR, int(star)))
        ego = 24.0 + 6.0 * s
        tier_rank = {"Common": 0, "Rare": 1, "Epic": 2, "Legendary": 3}
        for t in (traits or []):
            rank = tier_rank.get(Trait.tier_of(t), 0)
            ego += 2.0 * rank
            if rank == 3:
                ego += 8.0
        if hidden and s == 1:
            ego = rng.uniform(80.0, 98.0)
            return round(max(80.0, min(98.0, ego)), 1)
        ego += rng.uniform(-5.0, 5.0)
        return round(max(10.0, min(100.0, ego)), 1)

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
            ego_val = self._roll_ego(cls, star, traits, rare_extra, rng)
            hero = Hero(name, star, cls, 1, gm, traits,
                        skills=skills, base_stats=b_stats,
                        growth_stats=g_stats, mp_regen_val=mpr, ego=ego_val)
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
            ego_val = self._roll_ego(cls, star, traits, rare_extra, rng)
            hero = Hero(name, star, cls, 1, gm, traits,
                        skills=skills, base_stats=b_stats,
                        growth_stats=g_stats, mp_regen_val=mpr, ego=ego_val)
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
