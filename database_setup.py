# ======================================================================
#  DATABASE SETUP — Inisialisasi & Pengelolaan Database SQLite
#  Game: Auto-Battle Strategy RPG "Pick Me Up: Infinite Gacha" (CLI)
# ----------------------------------------------------------------------
#  Modul ini membuat & mengisi game_database.db:
#    - hero_names    : ribuan kombinasi (nama depan, belakang, gelar)
#    - perks         : nama, tier, deskripsi efek perk
#    - items_master  : equipment (Senjata/Zirah/Aksesori), potion, material
#    - class_stats   : stat dasar & growth per class (Mage langka ~3%)
#    - star_mults    : multiplier stat per star 1-7
#    - meta          : info versi database
#  Semua modul lain (generate_hero.py, main.py) menarik data dari sini.
#  Python 3 stdlib ONLY.
# ======================================================================
import os
import sqlite3

DB_PATH = os.environ.get("PMU_DB_PATH") or \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_database.db")
DB_VERSION = "2.0.0"

# ---------------------- DATA SUMBER (seed) ----------------------
# Nama prosedural: 36 x 32 x 26 = 29.952 kombinasi nama unik
FIRST_NAMES = [
    "Loki", "Evelyn", "Kai", "Ragna", "Selena", "Ashura", "Midad", "Yura",
    "Cleo", "Dante", "Fiora", "Garen", "Hilda", "Iris", "Jin", "Karin",
    "Leon", "Mira", "Nero", "Orin", "Pyra", "Quill", "Rin", "Sora",
    "Talon", "Umi", "Vera", "Wren", "Xion", "Yuki", "Zed", "Aria",
    "Bram", "Citra", "Darius", "Elric",
]
LAST_NAMES = [
    "Wrathford", "Stormbane", "Ironhart", "Nightveil", "Ashgrove",
    "Duskwalker", "Flameheart", "Grimsong", "Hollowmoor", "Icestrike",
    "Jadewing", "Kingsley", "Larkspur", "Moonshade", "Nighthollow",
    "Oakenshield", "Palefire", "Quicksilver", "Ravenhold", "Silvermain",
    "Thornbury", "Umbraskye", "Vexley", "Wraithborn", "Yellowaxe",
    "Zephyrion", "Blackwell", "Cindervale", "Dragonmoor", "Emberlyn",
    "Frostweald", "Goldhelm",
]
TITLES = [
    "Cursed", "Brave", "Silent", "Eternal", "Radiant", "Fallen", "Wicked",
    "Gilded", "Unbroken", "Forsaken", "Blazing", "Hollow", "Verdant",
    "Crimson", "Twilight", "Boundless", "Merciless", "Gentle", "Stormborn",
    "Ashen", "Glorious", "Hidden", "Voracious", "Zenith", "Onyx", "Wandering",
]

# ------------- STAT DASAR & GROWTH (1-star) per class -------------
# Format: (HP, ATK, DEF, SPD, MP)
BASE_STAT = {
    "Tanker": (220.0, 14.0, 18.0,  8.0, 30.0),
    "Dealer": (150.0, 22.0, 10.0, 11.0, 20.0),
    "Archer": (120.0, 19.0,  7.0, 14.0, 25.0),
    "Healer": (130.0, 10.0,  8.0, 10.0, 50.0),
    "Buffer": (140.0, 12.0,  9.0, 12.0, 45.0),
    "Mage":   ( 90.0, 26.0,  5.0,  9.0, 70.0),
}
GROWTH_STAT = {
    "Tanker": (22.0, 1.2, 1.2, 0.15, 2.0),
    "Dealer": (15.0, 2.2, 1.0, 0.25, 1.5),
    "Archer": (11.0, 1.9, 0.7, 0.35, 2.0),
    "Healer": (12.0, 0.8, 0.8, 0.20, 4.0),
    "Buffer": (13.0, 1.0, 0.9, 0.30, 3.5),
    "Mage":   ( 8.0, 2.6, 0.5, 0.20, 5.0),
}
MP_REGEN = {"Tanker": 4, "Dealer": 3, "Archer": 3, "Healer": 8, "Buffer": 7, "Mage": 6}
# Bobot gacha per class: Mage sengaja DIBERATI SANGAT RENDAH (langka ~3%).
CLASS_GACHA_WEIGHT = {"Tanker": 20, "Dealer": 20, "Archer": 20,
                      "Healer": 20, "Buffer": 20, "Mage": 3}

# Multiplier stat dasar & growth per star. Catatan canon: hidden potential
# membuat star awal TIDAK membatasi power akhir (1-star GM 2.5x bisa
# menyusul 4-star; promosi sampai 7-star untuk semua hero).
STAR_BASE_MULT = {1: 1.00, 2: 1.25, 3: 1.60, 4: 2.10, 5: 2.80, 6: 3.60, 7: 4.70}
STAR_GROWTH_MULT = {1: 1.00, 2: 1.20, 3: 1.45, 4: 1.75, 5: 2.15, 6: 2.60, 7: 3.20}

# ----------------------------- PERKS -----------------------------
# nama: (tier, deskripsi). Tier mengikuti TIER_WEIGHT di generate_hero.py.
PERKS = {
    "Glass Cannon": ("Common",    "ATK +40%, DEF -30%"),
    "Iron Wall":    ("Common",    "DEF +50%, SPD -15%"),
    "Quick Step":   ("Common",    "SPD +15%"),
    "Berserk":      ("Common",    "ATK +35% saat HP < 50%"),
    "Mana Surge":   ("Rare",      "MP regen +100%"),
    "Vampiric":     ("Rare",      "Heal diri 20% dari damage fisik"),
    "Focused Fire": ("Rare",      "+20% damage ke musuh HP terendah"),
    "Guardian":     ("Rare",      "Saat taunt aktif, DEF ally lain +25%"),
    "Executioner":  ("Epic",      "Damage x1.5 ke musuh HP < 25%"),
    "Last Stand":   ("Epic",      "Sekali per battle: bertahan di 1 HP"),
    "Double Cast":  ("Epic",      "Mage: 15% AoE tanpa konsumsi MP"),
    "Miracle Hand": ("Epic",      "Heal +30%, 10% crit heal (x2)"),
    "Late Bloomer": ("Legendary", "Growth +1.5% per level (kumulatif)"),
    "Unlucky":      ("Legendary", "15% serangannya meleset, ATK +40%"),
    "Chosen One":   ("Legendary", "GM +0.3, semua stat +10%"),
    "Phoenix":      ("Legendary", "Sekali per battle: revive 50% HP"),
}

# --------------------------- EQUIPMENT ---------------------------
TIER_LABEL = {1: "Common", 2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary"}
EQUIP_SLOTS = ("Senjata", "Zirah", "Aksesori")
EQUIP_NAMES = {
    "Senjata": {1: ["Pedang Karat", "Tongkat Retak"], 2: ["Pedang Baja", "Busur Pemburu"],
                3: ["Pedang Runes", "Tombak Gempa"], 4: ["Pedang Naga", "Gada Titan"],
                5: ["Pedang Sang Fajar", "Trisula Kehampaan"]},
    "Zirah":   {1: ["Jubah Usang", "Zirah Kulit"], 2: ["Zirah Rantai", "Perisai Kayu"],
                3: ["Zirah Plat Runes", "Mantel Bayangan"], 4: ["Zirah Naga", "Perisai Titan"],
                5: ["Aegis Kehampaan", "Zirah Sang Fajar"]},
    "Aksesori": {1: ["Cincin Perunggu", "Jimat Tulang"], 2: ["Amulet Perak", "Mata Elang"],
                 3: ["Cincin Runes", "Liontin Koma"], 4: ["Mata Naga", "Liontin Titan"],
                 5: ["Cincin Kehampaan", "Mata Sang Fajar"]},
}

# Item non-equipment (potion & material promosi) untuk items_master
CONSUMABLE_ITEMS = [
    ("Potion HP", "potion", "Battle item: pulihkan 50% HP max (AI memakainya otomatis)."),
    ("Attack Elixir", "potion", "Battle item: ATK +30% selama 3 ronde (AI otomatis)."),
    ("Guard Elixir", "potion", "Battle item: DEF +30% selama 3 ronde (AI otomatis)."),
    ("Mana Philter", "potion", "Battle item: isi penuh MP satu hero (AI otomatis)."),
    ("Revive Feather", "potion", "Battle item: bangkitkan hero gugur dengan 40% HP (AI otomatis)."),
    ("StarFragment", "material", "Material lama (kini dikonversi Low Soulstone)."),
    ("Core", "material", "Material langka epic+ dari Tower & Hidden Boss."),
    ("Gacha Ticket", "ticket", "Menambah 1x gacha gratis."),
]
# Dict nama -> deskripsi (dipakai layar detail Inventory di main.py)
CONSUMABLE_DESCS = {name: desc for name, _, desc in CONSUMABLE_ITEMS}

# Tabel biaya Star Promotion 1->7 (eksponensial). Dipakai main.py.
# Naik ke star: (material_wajib, jumlah_material, coins, success_rate)
# Skema material Soul & Essence — tiap tier butuh Soulstone/Book spesifik.
PROMO_TABLE = {
    2: ("Low Soulstone",          1,   1000, 1.00),
    3: ("Intermediate Soulstone", 2,   5000, 1.00),
    4: ("High Soulstone",         3,  20000, 0.85),
    5: ("Perfect Soul Essence",   3,  75000, 0.55),
    6: ("Book of Oath",           2, 300000, 0.30),
    7: ("Book of Fate",           2,1500000, 0.12),
}

# Resep crafting Raw Boss Material -> Soulstone matang.
# SEMUA resep diratakan: 5 raw -> 1 Soulstone.
# Book of Oath / Book of Fate SENGAJA tidak ada di sini: material end-game
# yang hanya bisa didrop (Boss Floor 80+ & Hidden Boss tingkat tinggi),
# drop rate sangat kecil (0.1%-1%), TIDAK dapat di-craft.
CRAFT_RECIPES = {
    "Stone Vessel":      ("Low Soulstone", 5),
    "Spirit Ore":        ("Intermediate Soulstone", 5),
    "Runic Core":        ("High Soulstone", 5),
    "Ectoplasm Crystal": ("Perfect Soul Essence", 5),
}

# Item Soulstone / Raw / Book untuk tabel items_master.
# name: (category, craft_into, craft_qty, description)
SOULSTONE_ITEMS = {
    "Stone Vessel": ("material", "Low Soulstone", 5,
                     "Raw material dari Boss Golem (Floor 5-9, drop ~5%). "
                     "5 unit dapat di-craft menjadi 1 Low Soulstone."),
    "Spirit Ore": ("material", "Intermediate Soulstone", 5,
                   "Raw material dari boss Floor 10-19 (drop ~5%). "
                   "5 unit dapat di-craft menjadi 1 Intermediate Soulstone."),
    "Runic Core": ("material", "High Soulstone", 5,
                   "Raw material dari boss Floor 20-39 (drop ~5%). "
                   "5 unit dapat di-craft menjadi 1 High Soulstone."),
    "Ectoplasm Crystal": ("material", "Perfect Soul Essence", 5,
                          "Raw material dari boss Floor 40+ (drop ~5%). "
                          "5 unit dapat di-craft menjadi 1 Perfect Soul Essence."),
    "Low Soulstone": ("material", "", 0,
                      "Soulstone untuk Star Promotion 1★ → 2★."),
    "Intermediate Soulstone": ("material", "", 0,
                               "Soulstone untuk Star Promotion 2★ → 3★."),
    "High Soulstone": ("material", "", 0,
                       "Soulstone untuk Star Promotion 3★ → 4★."),
    "Perfect Soul Essence": ("material", "", 0,
                             "Essence murni untuk Star Promotion 4★ → 5★."),
    "Book of Oath": ("material", "", 0,
                     "END-GAME (tidak dapat di-craft): sumpah para pahlawan "
                     "kuno. Star Promotion 5★ → 6★. Hanya dari Boss Floor 80+ "
                     "dan Hidden Boss tingkat tinggi (drop <1%)."),
    "Book of Fate": ("material", "", 0,
                     "END-GAME (tidak dapat di-craft): takdir yang tertulis "
                     "dari zaman dewa. Star Promotion 6★ → 7★. Hanya dari "
                     "Boss Floor 80+ dan Hidden Boss tingkat tinggi (drop <1%)."),
}


# ===================== INISIALISASI DATABASE =====================
def get_db(path=None, timeout=5.0):
    """Buka koneksi SQLite (row factory dict-like). Database dibuat otomatis.
    timeout: batas tunggu bila file sedang dikunci proses lain."""
    p = path or DB_PATH
    conn = sqlite3.connect(p, timeout=timeout)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path=None, force=False, wipe_accounts=False):
    """Buat tabel + isi seed data. Return path database.

    AMAN UNTUK UPDATE VERSI:
      force=True -> refresh HANYA tabel data game (hero_names, perks,
        items_master, class_stats, star_mults) dari seed. Tabel accounts
        (username & password pemain) TIDAK PERNAH disentuh, dan file save
        pemain (saves/*.json) tidak ada hubungannya dengan database —
        jadi update data game tidak akan pernah menghilangkan akun/progress.
      wipe_accounts=True -> HAPUS juga semua akun. DESTRUKTIF; hanya untuk
        reset total yang disengaja (dipisah dari force agar tak terjadi
        kehilangan akun karena salah flag).
    Idempotent: seeding memakai INSERT OR IGNORE sehingga aman dipanggil ulang."""
    p = path or DB_PATH
    conn = get_db(p, timeout=10.0)
    try:
        cur = conn.cursor()
        _create_tables(conn)          # CREATE IF NOT EXISTS — tidak pernah drop
        if wipe_accounts:
            cur.execute("DELETE FROM accounts")
        if force:
            # Hapus isi tabel DATA GAME saja; accounts dibiarkan utuh.
            for t in ("hero_names", "perks", "items_master", "class_stats",
                      "star_mults"):
                cur.execute("DELETE FROM %s" % t)
        _seed_all(conn)
        conn.commit()
        cur.close()                   # lepaskan SEMUA statement aktif
    finally:
        conn.close()                  # tutup koneksi = lock benar-benar lepas
    return p


def _create_tables(conn):
    """Skema tabel. PRIMARY KEY teks mencegah duplikasi data seed."""
    cur = conn.cursor()
    # 1) hero_names: ribuan kombinasi (depan, belakang, gelar)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hero_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name  TEXT NOT NULL,
            title      TEXT,
            UNIQUE(first_name, last_name, title)
        )""")
    # 2) perks: nama unik + tier + deskripsi efek (efek nyata di BattleEngine)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS perks (
            name        TEXT PRIMARY KEY,
            tier        TEXT NOT NULL,
            description TEXT NOT NULL
        )""")
    # 3) items_master: semua item (equipment/potion/material/ticket)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items_master (
            name        TEXT PRIMARY KEY,
            category    TEXT NOT NULL,       -- equipment | potion | material | ticket
            slot        TEXT,                -- Senjata/Zirah/Aksesori (equipment saja)
            tier        INTEGER DEFAULT 1,   -- 1..5 (Common..Legendary)
            atk         INTEGER DEFAULT 0,
            dfn         INTEGER DEFAULT 0,
            hp          INTEGER DEFAULT 0,
            description TEXT DEFAULT ''
        )""")
    # 4) class_stats: stat dasar & growth per class + bobot gacha (Mage langka)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS class_stats (
            cls           TEXT PRIMARY KEY,
            base_hp REAL, base_atk REAL, base_def REAL, base_spd REAL, base_mp REAL,
            growth_hp REAL, growth_atk REAL, growth_def REAL, growth_spd REAL, growth_mp REAL,
            mp_regen      INTEGER DEFAULT 3,
            gacha_weight  INTEGER DEFAULT 20,
            description   TEXT DEFAULT ''
        )""")
    # 5) star_mults: multiplier stat & growth per star 1-7
    cur.execute("""
        CREATE TABLE IF NOT EXISTS star_mults (
            star         INTEGER PRIMARY KEY,
            base_mult    REAL NOT NULL,
            growth_mult  REAL NOT NULL
        )""")
    # 6) accounts: login multi-akun (password disimpan sebagai hash+salt,
    #    JANGAN pernah plaintext)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt          TEXT NOT NULL,
            created_at    TEXT DEFAULT (datetime('now')),
            last_login    TEXT
        )""")
    # 7) meta: versi database
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        )""")


def _seed_all(conn):
    """Isi semua tabel seed. INSERT OR IGNORE = idempotent, tidak pernah duplikat."""
    cur = conn.cursor()
    # hero_names: gabungkan SEMUA kombinasi (36 x 32 x 26 = 29.952 + 1.152
    # tanpa gelar = 31.104 baris). CATATAN: title disimpan STRING KOSONG
    # (bukan NULL) karena UNIQUE SQLite memperlakukan NULL sebagai nilai
    # yang berbeda-beda -> INSERT OR IGNORE tidak akan menghalangi duplikat.
    rows = []
    for f in FIRST_NAMES:
        for l in LAST_NAMES:
            rows.append((f, l, ""))
            for t in TITLES:
                rows.append((f, l, t))
    cur.executemany(
        "INSERT OR IGNORE INTO hero_names (first_name, last_name, title) VALUES (?,?,?)",
        rows)
    # perks
    cur.executemany(
        "INSERT OR IGNORE INTO perks (name, tier, description) VALUES (?,?,?)",
        [(n, t, d) for n, (t, d) in PERKS.items()])
    # items_master: seluruh equipment per slot & tier
    eq_rows = []
    for slot, tiers in EQUIP_NAMES.items():
        for tier, names in tiers.items():
            for nm in names:
                # Stat template per slot mengikuti kurva Equipment.random()
                atk = dfn = hp = 0
                if slot == "Senjata":
                    atk = 3 * tier + tier  # nilai tengah rentang random
                    dfn = tier // 2
                elif slot == "Zirah":
                    dfn = 3 * tier + tier
                    hp = 8 * tier + 2 * tier
                else:
                    atk = 2 * tier + tier // 2
                    dfn = 1 * tier + tier // 2
                    hp = 5 * tier + 1 * tier
                eq_rows.append((nm, "equipment", slot, tier, atk, dfn, hp,
                                "Equipment %s tier %d." % (TIER_LABEL[tier], tier)))
    cur.executemany(
        "INSERT OR IGNORE INTO items_master (name, category, slot, tier, atk, dfn, hp, description)"
        " VALUES (?,?,?,?,?,?,?,?)", eq_rows)
    # items_master: potion, material, ticket
    cur.executemany(
        "INSERT OR IGNORE INTO items_master (name, category, description) VALUES (?,?,?)",
        CONSUMABLE_ITEMS)
    # items_master: soulstone, raw boss material, book end-game (craft info
    # disimpan di kolom description; resep hidup di CRAFT_RECIPES)
    cur.executemany(
        "INSERT OR IGNORE INTO items_master (name, category, description) VALUES (?,?,?)",
        [(n, cat, desc) for n, (cat, _into, _q, desc) in SOULSTONE_ITEMS.items()])
    # class_stats
    cls_rows = []
    for c in BASE_STAT:
        b, g = BASE_STAT[c], GROWTH_STAT[c]
        desc = "Class %s. " % c
        if c == "Mage":
            desc += ("Class LANGKA (~3%% roll): skill AoE + CC game changer, "
                     "HP/DEF paling rapuh.")
        cls_rows.append((c, b[0], b[1], b[2], b[3], b[4],
                         g[0], g[1], g[2], g[3], g[4],
                         MP_REGEN[c], CLASS_GACHA_WEIGHT[c], desc))
    cur.executemany(
        "INSERT OR IGNORE INTO class_stats (cls, base_hp, base_atk, base_def, base_spd, base_mp,"
        " growth_hp, growth_atk, growth_def, growth_spd, growth_mp, mp_regen, gacha_weight,"
        " description) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", cls_rows)
    # star_mults (1-7: termasuk hasil Star Promotion)
    cur.executemany(
        "INSERT OR IGNORE INTO star_mults (star, base_mult, growth_mult) VALUES (?,?,?)",
        [(s, STAR_BASE_MULT[s], STAR_GROWTH_MULT[s]) for s in STAR_BASE_MULT])
    # meta
    cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('db_version', ?)",
                (DB_VERSION,))
    cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('seeded_at', datetime('now'))")


# ========================= API PEMBACAAN =========================
def load_class_stats(path=None):
    """Return {cls: {base: (hp,atk,def,spd,mp), growth: (...), mp_regen, gacha_weight}}.
    Fallback ke konstanta seed bila database hilang/rusak (tidak pernah crash)."""
    out = {}
    try:
        conn = get_db(path)
        try:
            for r in conn.execute("SELECT * FROM class_stats"):
                out[r["cls"]] = {
                    "base": (r["base_hp"], r["base_atk"], r["base_def"],
                             r["base_spd"], r["base_mp"]),
                    "growth": (r["growth_hp"], r["growth_atk"], r["growth_def"],
                               r["growth_spd"], r["growth_mp"]),
                    "mp_regen": r["mp_regen"],
                    "gacha_weight": r["gacha_weight"],
                }
        finally:
            conn.close()
    except sqlite3.Error:
        pass  # DB bermasalah -> pakai seed konstanta
    if not out:  # fallback dari konstanta seed (DB tidak ada / kosong)
        for c in BASE_STAT:
            out[c] = {"base": BASE_STAT[c], "growth": GROWTH_STAT[c],
                      "mp_regen": MP_REGEN[c], "gacha_weight": CLASS_GACHA_WEIGHT[c]}
    return out


def load_star_mults(path=None):
    """Return {star: (base_mult, growth_mult)} dengan fallback konstanta seed."""
    out = {}
    try:
        conn = get_db(path)
        try:
            for r in conn.execute("SELECT star, base_mult, growth_mult FROM star_mults"):
                out[int(r["star"])] = (r["base_mult"], r["growth_mult"])
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    if not out:
        out = {s: (STAR_BASE_MULT[s], STAR_GROWTH_MULT[s]) for s in STAR_BASE_MULT}
    return out


def load_perks(path=None):
    """Return {nama_perk: (tier, deskripsi)} dengan fallback konstanta seed."""
    out = {}
    try:
        conn = get_db(path)
        try:
            for r in conn.execute("SELECT name, tier, description FROM perks"):
                out[r["name"]] = (r["tier"], r["description"])
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    if not out:
        out = dict(PERKS)
    return out


def load_items(path=None):
    """Return list dict seluruh items_master (equipment + consumable + material)."""
    rows = []
    try:
        conn = get_db(path)
        try:
            for r in conn.execute("SELECT * FROM items_master ORDER BY category, tier, name"):
                rows.append(dict(r))
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return rows


def pick_name_row(path=None, rng=None):
    """Ambil 1 baris nama acak dari hero_names (ribuan kombinasi).
    Return (first, last, title|None). Fallback: pilih dari konstanta seed."""
    rng = rng or __import__("random")
    try:
        conn = get_db(path)
        try:
            r = conn.execute(
                "SELECT first_name, last_name, title FROM hero_names "
                "ORDER BY RANDOM() LIMIT 1").fetchone()
            if r:
                # "" berarti tanpa gelar -> dikembalikan sebagai None
                return (r["first_name"], r["last_name"],
                        r["title"] if r["title"] else None)
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return (rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES),
            rng.choice(TITLES) if rng.random() < 0.35 else None)


def count_names(path=None):
    """Jumlah baris hero_names (untuk verifikasi seeding)."""
    try:
        conn = get_db(path)
        try:
            return conn.execute("SELECT COUNT(*) FROM hero_names").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


# ========================= AKUN & PASSWORD =========================
# Password TIDAK pernah disimpan plaintext: SHA-256(password + salt) dengan
# salt acak unik per akun. Cukup untuk game offline; tanpa dependency luar.
def _hash_password(password, salt):
    import hashlib
    return hashlib.sha256((salt + ":" + password).encode("utf-8")).hexdigest()


def create_account(username, password, path=None):
    """Buat akun baru. Return (ok: bool, pesan)."""
    username = (username or "").strip()
    if not username or len(username) < 3:
        return False, "Username minimal 3 karakter."
    if not password or len(password) < 4:
        return False, "Password minimal 4 karakter."
    import secrets
    salt = secrets.token_hex(8)
    try:
        conn = get_db(path)
        try:
            conn.execute(
                "INSERT INTO accounts (username, password_hash, salt) VALUES (?,?,?)",
                (username, _hash_password(password, salt), salt))
            conn.commit()
            return True, "Akun '%s' berhasil dibuat." % username
        finally:
            conn.close()
    except sqlite3.IntegrityError:
        return False, "Username '%s' sudah dipakai. Pilih yang lain." % username
    except sqlite3.Error as e:
        return False, "Gagal membuat akun: %s" % e


def verify_account(username, password, path=None):
    """Cek kredensial. Return (ok: bool, pesan)."""
    username = (username or "").strip()
    try:
        conn = get_db(path)
        try:
            r = conn.execute(
                "SELECT password_hash, salt FROM accounts WHERE username = ?",
                (username,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return False, "Database akun bermasalah: %s" % e
    if r is None:
        return False, "Username tidak ditemukan."
    if _hash_password(password or "", r["salt"]) == r["password_hash"]:
        # Catat waktu login terakhir (gagal diam-diam tidak masalah)
        try:
            conn = get_db(path)
            try:
                conn.execute("UPDATE accounts SET last_login = datetime('now') "
                             "WHERE username = ?", (username,))
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error:
            pass
        return True, "Selamat datang kembali, %s!" % username
    return False, "Password salah."


def backup_db(dest_path=None, src=None):
    """Salin database ke file backup (<db>.bak). Jaring pengaman: bila file
    database rusak/terhapus karena faktor luar, akun masih bisa dipulihkan.
    Memakai salinan file langsung (bukan sqlite backup API) — cepat, tanpa
    risiko menggantung pada lock, dan aman karena dipanggil saat koneksi
    game sudah tertutup. Best-effort: gagal backup tidak menggagalkan program."""
    src = src or DB_PATH
    dest = dest_path or (src + ".bak")
    try:
        # Guard: jangan pernah menimpa sumber dengan dirinya sendiri
        if os.path.abspath(dest) == os.path.abspath(src):
            return False
        import shutil
        shutil.copyfile(src, dest)
        return True
    except Exception:
        return False


def account_exists(username, path=None):
    try:
        conn = get_db(path)
        try:
            return conn.execute("SELECT 1 FROM accounts WHERE username = ?",
                                (username,)).fetchone() is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


# ============================ CLI ============================
if __name__ == "__main__":
    # Jalankan langsung: python3 database_setup.py [--force] [--wipe-accounts]
    # --force         : refresh data game dari seed (AKUN AMAN, tidak disentuh)
    # --wipe-accounts : HAPUS semua akun (DESTRUKTIF — reset total disengaja)
    import sys
    force = "--force" in sys.argv
    wipe = "--wipe-accounts" in sys.argv
    p = init_db(force=force, wipe_accounts=wipe)
    print("Database siap: %s" % p)
    print("  hero_names   : %d kombinasi nama" % count_names(p))
    print("  perks        : %d perk" % len(load_perks(p)))
    print("  items_master : %d item" % len(load_items(p)))
    print("  class_stats  : %d class" % len(load_class_stats(p)))
    print("  star_mults   : %d star" % len(load_star_mults(p)))
    try:
        conn = get_db(p)
        n = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        conn.close()
        print("  accounts     : %d akun%s" % (n, " (DIHAPUS!)" if wipe else " (utuh)"))
    except sqlite3.Error:
        pass
    if backup_db():
        print("  backup       : %s.bak" % p)
