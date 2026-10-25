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
_ITEMS = db.load_items()

CLASSES = list(_CLASS_STATS.keys()) if _CLASS_STATS else \
    ["Tanker", "Dealer", "Archer", "Healer", "Buffer", "Mage"]


def reload_db_data():
    """Paksa muat ulang cache dari database (mis. setelah re-seed manual)."""
    global _CLASS_STATS, _STAR_MULTS, _PERKS, _ITEMS, CLASSES
    _CLASS_STATS = db.load_class_stats()
    _STAR_MULTS = db.load_star_mults()
    _PERKS = db.load_perks()
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


# =============================== PERK ===============================
class Perk:
    """Representasi perk (data dari tabel perks di database)."""

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


# =============================== HERO ===============================
EQUIP_SLOTS = db.EQUIP_SLOTS


class Hero:
    """Satu hero. Semua stat final dihitung dari: base class x star mult
    + growth x (level-1) x growth_multiplier, lalu modifier perk/equip.
    Star awal TIDAK membatasi power akhir karena growth_multiplier
    (hidden potential) bisa menaikkan kurva 1-star secara drastis.
    Data stat diambil dari tabel class_stats & star_mults (SQLite)."""

    def __init__(self, name, star, cls, level=1, growth_multiplier=1.0, perks=None):
        self.name = name
        self.star = int(star)
        self.cls = cls
        self.level = max(1, int(level))
        self.xp = 0
        self.growth_multiplier = float(growth_multiplier)
        self.perks = list(perks) if perks else []
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

    # ---------- Fingerprint unik: (nama, tuple growth, tuple perks) ----------
    def fingerprint(self):
        g = self.growth_tuple()
        return (self.name, g, tuple(sorted(self.perks)))

    def growth_tuple(self):
        """Tuple growth final per class x star x GM (dibulatkan 3 desimal)."""
        gm = self.effective_gm()
        gs = self._cstats["growth"]
        sg = self._star_mults()[1]
        return tuple(round(v * sg * gm, 3) for v in gs)

    def effective_gm(self):
        """GM efektif = hidden potential GM + bonus Late Bloomer (+0.5 mulai L30)."""
        gm = self.growth_multiplier
        if "Late Bloomer" in self.perks and self.level >= 30:
            gm += 0.5
        return gm

    def has(self, perk):
        return perk in self.perks

    # ----------------------- Stat dasar per level -----------------------
    def _base_stat(self, idx):
        """Stat mentah = round(base[star] + growth[star] x (level-1) x GM)."""
        b = self._cstats["base"][idx] * self._star_mults()[0]
        g = self._cstats["growth"][idx] * self._star_mults()[1]
        return b + g * (self.level - 1) * self.effective_gm()

    def _final_stat(self, idx, use_equip=True):
        v = self._base_stat(idx)
        # Perk stat modifier (additif, % dari nilai dasar)
        if idx == 1:  # ATK
            if self.has("Glass Cannon"): v *= 1.40
            if self.has("Unlucky"): v *= 1.40
            if self.has("Chosen One"): v *= 1.10
            if self.has("Berserk") and self.hp < self.max_hp * 0.5:
                v *= 1.35
        if idx == 2:  # DEF
            if self.has("Iron Wall"): v *= 1.50
            if self.has("Glass Cannon"): v *= 0.70
        if idx == 3:  # SPD
            if self.has("Iron Wall"): v *= 0.85
            if self.has("Quick Step"): v *= 1.15
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
        if self.has("Iron Wall"): hp *= 1.10
        if self.has("Chosen One"): hp *= 1.10
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
        return int(round(self._base_stat(4)))

    @property
    def mp_regen(self):
        r = self._cstats["mp_regen"]
        if self.has("Mana Surge"): r *= 2
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
            "growth_multiplier": self.growth_multiplier, "perks": self.perks,
            "equipment": {s: (e.to_dict() if e else None) for s, e in self.equipment.items()},
            "alive": self.alive,
            "hp": self.hp,   # persist wound state (Heal/Rest jadi berarti)
            "blueprints": _safe_int(getattr(self, "blueprints", 0), 0),
        }

    @classmethod
    def from_dict(cls, d):
        """Load hero dari save (versi lama apapun) dengan default aman.
        Field baru yang hilang (growth_multiplier, perks, dll) diisi default."""
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
        perks = d.get("perks") or []
        perks = [str(p) for p in perks if p in _PERKS]
        h = cls(name, star, hero_cls, level, gm, perks)
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
        RAHASIA: hidden potential (growth_multiplier) SENGAJA tidak
        ditampilkan — pemain tidak boleh tahu hero mana yang terlahir
        istimewa; kejutannya terasa di pertumbuhan saat level naik."""
        eqs = [e.describe() for e in self.equipment.values() if e]
        return [
            "Nama   : %s" % self.name,
            "Class  : %s  |  Star: %s  |  Level: %d  (XP %d/%d)" % (
                self.cls, "*" * self.star, self.level, self.xp, self.xp_needed()),
            "Status : %s" % ("HIDUP" if self.alive else "GUGUR"),
            "Perks  : %s" % (", ".join(self.perks) if self.perks else "(tidak ada)"),
            "HP %d/%d  ATK %d  DEF %d  SPD %d  MP %d  (regen %d/ronde)" % (
                self.hp, self.max_hp, self.atk, self.dfn, self.spd,
                int(self.mana), self.mp_regen),
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

    def create(self, star, cls=None, rng=None):
        """Buat hero unik dari data database. Return instance Hero.
        Jika cls None, class di-roll sesuai bobot gacha (Mage langka ~3%)."""
        rng = rng or random
        if cls is None or cls not in _CLASS_STATS:
            cls = self.roll_class(rng)
        star = max(1, min(MAX_STAR, int(star)))
        rare_extra = False
        if star == 1:
            gm, rare_extra = self._roll_hidden(rng)
        else:
            # Hero 5-star pasti kuat: GM > 1 + jaminan perk bagus
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
            perks = self._roll_perks(star, rare_extra, rng)
            hero = Hero(name, star, cls, 1, gm, perks)
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
            hero = Hero(name, star, cls, 1, gm, self._roll_perks(star, rare_extra, rng))
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
