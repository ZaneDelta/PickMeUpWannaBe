# ======================================================================
#  DATABASE SETUP — Inisialisasi & Pengelolaan Database SQLite
#  Game: Auto-Battle Strategy RPG "Pick Me Up: Infinite Gacha" (CLI)
# ----------------------------------------------------------------------
#  Modul ini membuat & mengisi game_database.db:
#    - hero_names    : ribuan kombinasi (nama depan, belakang, gelar)
#    - traits        : nama, tier, deskripsi efek trait, & flag cursed
#    - skills        : skill class, universal, & cursed (beserta flag cursed)
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
DB_VERSION = "2.4.0"

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

# ==================== RANDOMISASI STAT & RISE RATE ====================
# Aturan baru randomisasi stat dasar (base_stats):
#   1. Batas MAKSIMUM tiap stat SAMA untuk semua class dan semua star.
#   2. Batas MINIMUM tiap stat BERBEDA-BEDA per class sesuai spesialisasi
#      (misal Tanker punya minimum DEF & HP lebih tinggi dibanding Dealer,
#      sedangkan Dealer/Mage punya minimum ATK lebih tinggi).
#   3. Makin tinggi nilai stat, makin kecil persentase peluang mendapatkannya.
#   4. Makin tinggi star grade hero, makin besar peluang mendapat stat sangat tinggi.
STAT_KEYS = ("hp", "atk", "def", "spd", "mp")

# Maksimum stat dasar UNIVERSAL (sama untuk semua class & semua star)
STAT_BASE_MAX = {
    "hp":  260.0,
    "atk":  32.0,
    "def":  24.0,
    "spd":  18.0,
    "mp":   90.0,
}

# Minimum stat dasar BERBEDA per class & per stat
STAT_BASE_MIN_BY_CLASS = {
    "Tanker": {"hp": 150.0, "atk":  9.0, "def": 13.0, "spd":  7.0, "mp": 25.0},
    "Dealer": {"hp": 110.0, "atk": 15.0, "def":  7.0, "spd": 10.0, "mp": 20.0},
    "Archer": {"hp":  95.0, "atk": 14.0, "def":  5.0, "spd": 12.0, "mp": 22.0},
    "Healer": {"hp": 105.0, "atk":  8.0, "def":  7.0, "spd":  9.0, "mp": 45.0},
    "Buffer": {"hp": 115.0, "atk":  9.0, "def":  8.0, "spd": 11.0, "mp": 40.0},
    "Mage":   {"hp":  85.0, "atk": 17.0, "def":  4.0, "spd":  8.0, "mp": 50.0},
}

# Fallback global range (min terendah lintas class s/d max universal)
STAT_BASE_RANGE = {
    "hp":  (85.0,  260.0),
    "atk": ( 8.0,   32.0),
    "def": ( 4.0,   24.0),
    "spd": ( 7.0,   18.0),
    "mp":  (20.0,   90.0),
}

# Aturan baru Rise Rate stat tiap naik level (growth_stats):
#   1. Batas MINIMUM dan MAKSIMUM rise rate tiap stat SAMA untuk semua star & class.
#   2. Yang berbeda tiap star HANYA persentase peluang mendapat rise rate bagus.
#   3. Makin tinggi nilai rise rate, makin kecil persentasenya.
#   4. Hero 1-star BISA mendapat rise rate maksimum, namun persentasenya sangat kecil.
STAT_GROWTH_RANGE = {
    "hp":  (8.0,   26.0),
    "atk": (0.8,    3.0),
    "def": (0.5,    1.6),
    "spd": (0.15,   0.45),
    "mp":  (1.5,    6.0),
}
MP_REGEN_RANGE = (3, 8)

# Pembagian 5 pita (band) proporsional dari rentang [min, max]:
#   Band 0: 0% - 20%  (Rendah)
#   Band 1: 20% - 40% (Menengah Bawah)
#   Band 2: 40% - 60% (Menengah)
#   Band 3: 60% - 80% (Tinggi)
#   Band 4: 80% - 100% (Sangat Tinggi / Maksimum)
STAT_BANDS = [
    (0.00, 0.20),
    (0.20, 0.40),
    (0.40, 0.60),
    (0.60, 0.80),
    (0.80, 1.00),
]

# Bobot persentase (per 1000 = 100.0%) tiap band berdasarkan Star (1..7):
# - Di SETIAP star, bobot selalu menurun dari Band 0 ke Band 4 (makin tinggi stat,
#   makin kecil persentasenya).
# - Makin tinggi star, makin besar bobot di Band 3 & Band 4 (stat / rise rate tinggi).
# - Hero 1-star tetap punya peluang di Band 4 (0.8%, dan ~0.12% menyentuh puncak
#   maksimum) sehingga 1-star bisa dapat rise rate maksimum dengan peluang sangat kecil.
STAR_STAT_BAND_WEIGHTS = {
    1: (580, 260, 110,  42,   8),   # Band 4 (80-100%): 0.8%
    2: (480, 275, 150,  75,  20),   # Band 4 (80-100%): 2.0%
    3: (390, 270, 190, 110,  40),   # Band 4 (80-100%): 4.0%
    4: (310, 255, 215, 150,  70),   # Band 4 (80-100%): 7.0%
    5: (250, 230, 210, 185, 125),   # Band 4 (80-100%): 12.5%
    6: (225, 215, 205, 190, 165),   # Band 4 (80-100%): 16.5%
    7: (212, 206, 200, 194, 188),   # Band 4 (80-100%): 18.8%
}
STAR_GROWTH_BAND_WEIGHTS = dict(STAR_STAT_BAND_WEIGHTS)

# Multiplier stat dasar & growth per star. Catatan canon: hidden potential
# membuat star awal TIDAK membatasi power akhir (1-star GM 2.5x bisa
# menyusul 4-star; promosi sampai 7-star untuk semua hero).
STAR_BASE_MULT = {1: 1.00, 2: 1.25, 3: 1.60, 4: 2.10, 5: 2.80, 6: 3.60, 7: 4.70}
STAR_GROWTH_MULT = {1: 1.00, 2: 1.20, 3: 1.45, 4: 1.75, 5: 2.15, 6: 2.60, 7: 3.20}

# ------------------------ TRAITS (d/h PERKS) ------------------------
# nama: (tier, deskripsi). Tier mengikuti TIER_WEIGHT di generate_hero.py.
# RAHASIA: Tier trait TIDAK ditampilkan di UI pemain!
TRAITS = {
    # Common (16)
    "Glass Cannon":    ("Common",    "ATK +40%, DEF -30%"),
    "Iron Wall":       ("Common",    "DEF +50%, SPD -15%"),
    "Quick Step":      ("Common",    "SPD +15%"),
    "Berserk":         ("Common",    "ATK +35% saat HP < 50%"),
    "Sturdy Body":     ("Common",    "Max HP +18%"),
    "Sharp Edge":      ("Common",    "ATK +15%"),
    "Stone Skin":      ("Common",    "DEF +20%"),
    "Deep Mind":       ("Common",    "Max MP +25%"),
    "Nimble Feet":     ("Common",    "SPD +10%, DEF +5%"),
    "Reckless Charge": ("Common",    "ATK +25%, Max HP -10%"),
    "Thick Armor":     ("Common",    "DEF +30%, ATK -10%"),
    "First Strike":    ("Common",    "+25% damage ke musuh HP > 80%"),
    "Calm Spirit":     ("Common",    "MP regen +2 per ronde"),
    "Battle Hardened": ("Common",    "Max HP +10%, DEF +10%"),
    "Fierce Grip":     ("Common",    "ATK +12%, Max HP +8%"),
    "Light Armor":     ("Common",    "SPD +12%, Max MP +10%"),
    # Rare (14)
    "Mana Surge":      ("Rare",      "MP regen +100%"),
    "Vampiric":        ("Rare",      "Heal diri 20% dari damage fisik"),
    "Focused Fire":    ("Rare",      "+20% damage ke musuh target"),
    "Guardian":        ("Rare",      "Saat ada ally taunt aktif, DEF diri +25%"),
    "Bloodthirst":     ("Rare",      "ATK +20% dan lifesteal +10%"),
    "Titan Blood":     ("Rare",      "Max HP +28%, DEF +12%"),
    "Wind Runner":     ("Rare",      "SPD +22%, ATK +10%"),
    "Arcane Well":     ("Rare",      "Max MP +40%, MP regen +3/ronde"),
    "Giant Slayer":    ("Rare",      "+25% damage terhadap Boss & Elite"),
    "Unyielding":      ("Rare",      "DEF +35% saat HP < 50%"),
    "Precision":       ("Rare",      "ATK +18%, serangan tidak pernah meleset"),
    "Vitality Aura":   ("Rare",      "Regen 5% Max HP tiap akhir ronde"),
    "Spell Weaver":    ("Rare",      "Biaya MP semua skill berkurang 15%"),
    "Counter Stance":  ("Rare",      "DEF +15%, ATK +10% saat terluka"),
    # Epic (10)
    "Executioner":     ("Epic",      "Damage x1.5 ke musuh HP < 25%"),
    "Last Stand":      ("Epic",      "Sekali per battle: bertahan di 1 HP, ATK +30%"),
    "Double Cast":     ("Epic",      "Skill AoE: 15% tanpa konsumsi MP"),
    "Miracle Hand":    ("Epic",      "Heal +30%, 10% crit heal (x2)"),
    "Warlord":         ("Epic",      "ATK +22%, Max HP +20%, DEF +15%"),
    "Soul Harvester":  ("Epic",      "Max MP +30%, ATK +20%"),
    "Aegis Heart":     ("Epic",      "DEF +35%, Max HP +15%"),
    "Overcharge":      ("Epic",      "Saat MP > 70%, damage skill +30%"),
    "Shadow Step":     ("Epic",      "SPD +28%, ATK +15%"),
    "Dragon Scales":   ("Epic",      "Max HP +30%, DEF +30%"),
    # Legendary (8)
    "Late Bloomer":    ("Legendary", "Growth +1.5% per level (kumulatif)"),
    "Unlucky":         ("Legendary", "15% serangannya meleset, ATK +40%"),
    "Chosen One":      ("Legendary", "GM +0.3, semua stat +10%"),
    "Phoenix":         ("Legendary", "Sekali per battle: revive 50% HP"),
    "Immortal Vessel": ("Legendary", "Max HP +45%, DEF +25%, regen 8% HP/ronde"),
    "Godslayer":       ("Legendary", "ATK +35%, +30% damage ke Boss"),
    "Infinite Mana":   ("Legendary", "Max MP +50%, MP regen +150%, biaya MP -20%"),
    "Celestial Grace": ("Legendary", "Semua stat +18%, efek heal +25%"),
}

# 10 Cursed Traits (cursed = 1, tier = "Cursed") — HANYA dari kegagalan Soul Overload!
CURSED_TRAITS_POOL = {
    "Cracked Vessel":      ("Cursed", "Max HP berkurang -25% dan menerima +15% damage tambahan dari semua serangan."),
    "Leaking Soul":        ("Cursed", "Tidak mendapat regenerasi MP per ronde di dalam battle, malahan kehilangan 5 MP setiap pergantian ronde."),
    "Schizophrenic Ego":   ("Cursed", "Peluang terpicunya Mental Instability (Soul Berserk / Memory Echo) menjadi 35% di setiap giliran meskipun sanity >= 40.0."),
    "Fragile Bones":       ("Cursed", "DEF total dipotong -40%, namun SPD meningkat +15%."),
    "Mana Parasite":       ("Cursed", "Biaya MP semua skill menjadi 2x lipat; jika MP sendiri kurang, sisanya disedot paksa dari MP rekan party acak."),
    "Cursed Aura":         ("Cursed", "Selama hero ini hidup di party, seluruh rekan satu party lainnya mengalami penurunan ATK dan DEF sebesar -10%."),
    "Bloodlust Masochist": ("Cursed", "ATK +20%, namun setiap kali melakukan aksi serangan (basic attack maupun skill ofensif), kehilangan 8% Max HP sendiri."),
    "Severed Nerves":      ("Cursed", "SPD dipotong -35% dan memiliki peluang 20% lumpuh (melewatkan giliran) saat gilirannya tiba di battle."),
    "Doomed Fate":         ("Cursed", "Menolak kebangkitan: saat HP mencapai 0, Revive Feather, Last Stand, dan Phoenix TIDAK AKAN AKTIF (langsung gugur)."),
    "Unstable Core":       ("Cursed", "Pemulihan sanity pasca-menang battle hanya +1.0; jika mati di tengah pertarungan, jiwanya meledak melukai seluruh rekan party hidup sebesar 25% Max HP."),
}
CURSED_TRAITS = CURSED_TRAITS_POOL

# Alias backward-compatibility untuk modul/kode lama
PERKS = TRAITS

# ----------------------------- SKILLS ----------------------------
# Sistem Skill:
#   - 30 skill khusus per class (6 class x 30 = 180 skill class)
#   - 60 skill Universal (TIDAK boleh ada Taunt di Universal!)
#   - Total pool = 240 skill unik.
#   - Tiap hero mendapat 1-2 skill class-nya + 0-3 skill Universal.
#   - RAHASIA: Tier skill TIDAK ditampilkan di UI pemain!
# Format per entri: nama: (tier, mp_cost, cd, kind, mult, deskripsi)
CLASS_SKILLS = {
    "Tanker": {
        "Taunt":              ("Common",    10, 3, "taunt",      30.0, "Paksa musuh menarget diri 2 ronde, DEF +30%"),
        "Shield Bash":        ("Common",    15, 4, "stun",       1.20, "Hantaman perisai 1.2x ATK + peluang stun 20%"),
        "Iron Taunt":         ("Common",    12, 3, "taunt",      35.0, "Teriakan baja 2 ronde paksa aggro, DEF +35%"),
        "Guard Stance":       ("Common",    14, 3, "buff_def",   20.0, "Perkuat pertahanan party DEF +20% (3 ronde)"),
        "Heavy Buckler":      ("Common",    14, 2, "single",     1.35, "Pukulan perisai berat 1.35x ATK"),
        "Stone Provoke":      ("Common",    11, 3, "taunt",      30.0, "Provokasi batu 2 ronde, DEF +30%"),
        "Fortress Slam":      ("Common",    16, 3, "single",     1.45, "Hantaman benteng 1.45x ATK"),
        "Anvil Strike":       ("Common",    15, 3, "stun",       1.25, "Pukulan paron 1.25x ATK + stun 20%"),
        "Vanguard Shout":     ("Common",    13, 3, "taunt",      32.0, "Teriakan garda depan 2 ronde, DEF +32%"),
        "Bulwark Smash":      ("Common",    16, 3, "single",     1.50, "Tebasan perisai raksasa 1.5x ATK"),
        "Aegis Provoke":      ("Rare",      14, 3, "taunt",      40.0, "Provokasi Aegis 2 ronde, DEF +40%"),
        "Shield Wall":        ("Rare",      20, 3, "buff_def",   28.0, "Dinding perisai party DEF +28% (3 ronde)"),
        "Tremor Stomp":       ("Rare",      22, 3, "aoe_slow",   0.65, "Injakan gempa AoE 0.65x ATK + slow musuh"),
        "Armor Crush":        ("Rare",      18, 3, "pierce",     1.40, "Remukkan zirah 1.4x ATK (ignore DEF)"),
        "Sentinel Bash":      ("Rare",      18, 3, "stun",       1.40, "Hantaman sentinel 1.4x ATK + stun 25%"),
        "Bastion Roar":       ("Rare",      15, 3, "taunt",      42.0, "Raungan bastion 2 ronde paksa aggro, DEF +42%"),
        "Tower Charge":       ("Rare",      19, 3, "single",     1.65, "Serudukan perisai menara 1.65x ATK"),
        "Spiked Shield":      ("Rare",      17, 2, "drain",      1.35, "Serangan perisai berduri 1.35x ATK + serap HP"),
        "Phalanx Guard":      ("Rare",      22, 4, "buff_def",   30.0, "Formasi Phalanx DEF party +30% (3 ronde)"),
        "Golem Fist":         ("Rare",      20, 3, "stun",       1.45, "Tinju golem 1.45x ATK + peluang stun 25%"),
        "Colossus Taunt":     ("Epic",      16, 3, "taunt",      50.0, "Provokasi kolosus 2 ronde, DEF +50%"),
        "Earthshaker":        ("Epic",      28, 4, "aoe_stun",   0.85, "Belah bumi AoE 0.85x ATK + stun 15%"),
        "Obsidian Fortress":  ("Epic",      25, 4, "buff_def",   35.0, "Benteng obsidian DEF party +35% (3 ronde)"),
        "Juggernaut Impact":  ("Epic",      24, 3, "stun",       1.75, "Tabrakan Juggernaut 1.75x ATK + stun 35%"),
        "Guardian Vow":       ("Epic",      22, 4, "cleanse_heal",1.30, "Sumpah pelindung: pulihkan HP & hapus stun ally"),
        "Steel Avalanche":    ("Epic",      26, 4, "aoe_slow",   0.80, "Longsoran baja AoE 0.8x ATK + slow 2 ronde"),
        "Titan Provoke":      ("Legendary", 18, 3, "taunt",      65.0, "Provokasi Titan 2 ronde, DEF +65%"),
        "Immortal Bastion":   ("Legendary", 32, 5, "buff_all",   30.0, "Berkah benteng abadi: ATK & SPD party +30%"),
        "Worldbreaker Slam":  ("Legendary", 38, 5, "aoe_stun",   1.35, "Hantaman penghancur AoE 1.35x ATK + stun 25%"),
        "Aegis of Dawn":      ("Legendary", 30, 4, "mass_heal",  1.10, "Cahaya Aegis: pulihkan HP seluruh party"),
    },
    "Dealer": {
        "Power Strike":       ("Common",    20, 3, "single",     1.80, "Serangan kuat 1.8x ATK ke 1 musuh"),
        "Savage Slash":       ("Common",    14, 2, "single",     1.55, "Tebasan buas 1.55x ATK ke 1 musuh"),
        "Double Edge":        ("Common",    16, 2, "single",     1.65, "Tebasan ganda 1.65x ATK"),
        "Blade Thrust":       ("Common",    15, 2, "pierce",     1.35, "Tusukan pedang 1.35x ATK menembus DEF"),
        "Brutal Cleave":      ("Common",    18, 3, "single",     1.70, "Ayunan brutal 1.7x ATK"),
        "Rending Cut":        ("Common",    15, 2, "single",     1.60, "Sayatan perobek 1.6x ATK"),
        "Crimson Bite":       ("Common",    18, 3, "drain",      1.35, "Tebasan merah 1.35x ATK + serap HP"),
        "Pommel Strike":      ("Common",    16, 3, "stun",       1.30, "Hantaman gagang pedang 1.3x ATK + stun 20%"),
        "Furious Lunge":      ("Common",    17, 2, "single",     1.68, "Terjangan murka 1.68x ATK"),
        "Razor Whirl":        ("Common",    22, 3, "aoe_slow",   0.60, "Putaran pisau AoE 0.6x ATK + slow"),
        "Shadow Fang":        ("Rare",      20, 2, "pierce",     1.55, "Taring bayangan 1.55x ATK ignore DEF"),
        "Blood Frenzy":       ("Rare",      22, 3, "drain",      1.55, "Amukan darah 1.55x ATK + serap 40% HP"),
        "Guillotine Blade":   ("Rare",      24, 3, "single",     1.95, "Tebasan guillotine 1.95x ATK"),
        "Whirlwind Slash":    ("Rare",      28, 3, "aoe_stun",   0.75, "Tebasan angin puyuh AoE 0.75x ATK + stun 10%"),
        "Armor Breaker":      ("Rare",      20, 2, "pierce",     1.60, "Penghancur zirah 1.6x ATK ignore DEF"),
        "Viper Strike":       ("Rare",      19, 2, "single",     1.85, "Sabetan berbisa 1.85x ATK"),
        "Skull Splitter":     ("Rare",      23, 3, "stun",       1.60, "Pembelah tengkorak 1.6x ATK + stun 25%"),
        "Phantom Cut":        ("Rare",      21, 2, "pierce",     1.58, "Tebasan hantu 1.58x ATK menembus DEF"),
        "Reaper Scythe":      ("Rare",      25, 3, "drain",      1.60, "Sabit pencabut nyawa 1.6x ATK + serap HP"),
        "Berserker Rush":     ("Rare",      24, 3, "single",     2.00, "Serbuan berserker 2.0x ATK"),
        "Assassinate":        ("Epic",      28, 3, "pierce",     1.90, "Eksekusi senyap 1.9x ATK ignore DEF"),
        "Blade Storm":        ("Epic",      36, 4, "aoe_pierce", 0.95, "Badai pedang AoE 0.95x ATK ignore DEF"),
        "Execution Slash":    ("Epic",      30, 3, "single",     2.25, "Tebasan algojo 2.25x ATK"),
        "Soul Rend":          ("Epic",      28, 3, "drain",      1.80, "Robekan jiwa 1.8x ATK + lifesteal 40%"),
        "Thunder Cleave":     ("Epic",      30, 3, "stun",       1.95, "Tebasan petir 1.95x ATK + stun 35%"),
        "Demonic Flurry":     ("Epic",      32, 4, "single",     2.35, "Rentetan iblis 2.35x ATK ke target"),
        "Abyssal Sever":      ("Legendary", 42, 4, "pierce",     2.40, "Tebasan jurang 2.4x ATK menembus DEF"),
        "Ragnarok Edge":      ("Legendary", 50, 5, "aoe_stun",   1.65, "Pedang Ragnarok AoE 1.65x ATK + stun 25%"),
        "Blood Moon Slash":   ("Legendary", 40, 4, "drain",      2.20, "Tebasan bulan darah 2.2x ATK + lifesteal"),
        "Godslayer Thrust":   ("Legendary", 45, 5, "pierce",     2.60, "Tusukan pembunuh dewa 2.6x ATK ignore DEF"),
    },
    "Archer": {
        "Piercing Shot":      ("Common",    18, 2, "pierce",     1.50, "Tembakan 1.5x ATK menembus DEF musuh"),
        "Quick Arrow":        ("Common",    12, 2, "single",     1.48, "Panah kilat 1.48x ATK"),
        "Aimed Shot":         ("Common",    16, 2, "single",     1.65, "Tembakan terbidik 1.65x ATK"),
        "Pinning Arrow":      ("Common",    16, 3, "stun",       1.25, "Panah pengunci 1.25x ATK + stun 20%"),
        "Barbed Bolt":        ("Common",    15, 2, "single",     1.58, "Anak panah berduri 1.58x ATK"),
        "Split Arrow":        ("Common",    22, 3, "aoe_slow",   0.55, "Panah bercabang AoE 0.55x ATK + slow"),
        "Hawk Shot":          ("Common",    17, 2, "pierce",     1.42, "Panah elang 1.42x ATK ignore DEF"),
        "Frost Arrow":        ("Common",    18, 3, "aoe_slow",   0.58, "Panah es AoE 0.58x ATK + slow musuh"),
        "Longbow Snipe":      ("Common",    19, 3, "single",     1.75, "Tembakan busur panjang 1.75x ATK"),
        "Wind Arrow":         ("Common",    14, 2, "single",     1.52, "Panah angin 1.52x ATK"),
        "Armor Piercer":      ("Rare",      20, 2, "pierce",     1.62, "Panah penembus baja 1.62x ATK ignore DEF"),
        "Arrow Rain":         ("Rare",      28, 3, "aoe_slow",   0.75, "Hujan panah AoE 0.75x ATK + slow 2 ronde"),
        "Heartseeker":        ("Rare",      24, 3, "single",     2.00, "Panah pencari jantung 2.0x ATK"),
        "Concussive Shot":    ("Rare",      22, 3, "stun",       1.55, "Tembakan gegar 1.55x ATK + stun 25%"),
        "Venom Volley":       ("Rare",      26, 3, "aoe_stun",   0.70, "Volley racun AoE 0.7x ATK + stun 10%"),
        "Gale Snipe":         ("Rare",      21, 2, "pierce",     1.65, "Snipe badai 1.65x ATK menembus DEF"),
        "Leech Arrow":        ("Rare",      22, 3, "drain",      1.50, "Panah penghisap 1.5x ATK + lifesteal"),
        "Rapid Volley":       ("Rare",      23, 3, "single",     1.92, "Tembakan beruntun 1.92x ATK"),
        "Silver Bolt":        ("Rare",      20, 2, "pierce",     1.60, "Pasak perak 1.6x ATK ignore DEF"),
        "Falcon Eye":         ("Rare",      20, 3, "buff_atk",   25.0, "Fokus mata elang: ATK party +25% (3 ronde)"),
        "Deadeye Snipe":      ("Epic",      30, 3, "pierce",     2.00, "Tembakan maut 2.0x ATK ignore DEF"),
        "Storm of Arrows":    ("Epic",      38, 4, "aoe_pierce", 1.00, "Badai panah AoE 1.0x ATK menembus DEF"),
        "Thunder Arrow":      ("Epic",      28, 3, "stun",       1.90, "Panah halilintar 1.9x ATK + stun 35%"),
        "Phantom Volley":     ("Epic",      34, 4, "aoe_stun",   0.95, "Volley bayangan AoE 0.95x ATK + stun 15%"),
        "Dragon Piercer":     ("Epic",      32, 3, "pierce",     2.10, "Penembus sisik naga 2.1x ATK ignore DEF"),
        "Moonlight Shot":     ("Epic",      28, 3, "drain",      1.80, "Panah cahaya bulan 1.8x ATK + lifesteal"),
        "Starfall Arrow":     ("Legendary", 48, 5, "aoe_pierce", 1.40, "Hujan panah bintang AoE 1.4x ATK ignore DEF"),
        "Astraea Bolt":       ("Legendary", 42, 4, "pierce",     2.50, "Panah dewi Astraea 2.5x ATK ignore DEF"),
        "Heavenly Barrage":   ("Legendary", 52, 5, "aoe_stun",   1.65, "Rentetan surga AoE 1.65x ATK + stun 25%"),
        "Void Snipe":         ("Legendary", 44, 4, "pierce",     2.55, "Tembakan kehampaan 2.55x ATK ignore DEF"),
    },
    "Healer": {
        "Heal":               ("Common",    25, 2, "heal",       2.00, "Pulihkan HP 1 ally kritis (2x ATK + 25)"),
        "Mending Light":      ("Common",    20, 2, "heal",       1.75, "Cahaya pemulih 1 ally (1.75x ATK + 25)"),
        "Gentle Prayer":      ("Common",    22, 2, "heal",       1.85, "Doa lembut pemulih HP 1 ally"),
        "Holy Bolt":          ("Common",    15, 2, "single",     1.45, "Bola cahaya suci 1.45x ATK ke musuh"),
        "Soothing Breeze":    ("Common",    24, 2, "heal",       1.95, "Angin penyejuk pemulih 1 ally"),
        "Purifying Touch":    ("Common",    22, 3, "cleanse_heal",1.60, "Pulihkan HP 1 ally & hapus efek stun"),
        "Minor Grace":        ("Common",    18, 2, "heal",       1.65, "Berkah pemulihan cepat 1 ally"),
        "Radiant Spark":      ("Common",    16, 2, "single",     1.50, "Percikan suci 1.5x ATK ke musuh"),
        "Blessing of Vita":   ("Common",    26, 2, "heal",       2.10, "Berkah kehidupan 1 ally (2.1x ATK + 25)"),
        "Sacred Mend":        ("Common",    23, 2, "heal",       1.90, "Jahitan suci pemulih luka ally"),
        "Greater Heal":       ("Rare",      30, 2, "heal",       2.45, "Pemulihan besar 1 ally (2.45x ATK + 25)"),
        "Circle of Healing":  ("Rare",      38, 4, "mass_heal",  1.05, "Lingkaran pemulih seluruh party"),
        "Cleanse Spirit":     ("Rare",      26, 3, "cleanse_heal",2.00, "Murnikan jiwa & pulihkan HP ally"),
        "Holy Barrier":       ("Rare",      22, 3, "buff_def",   28.0, "Perisai suci DEF party +28% (3 ronde)"),
        "Life Drain":         ("Rare",      22, 3, "drain",      1.50, "Serap energi musuh 1.5x ATK jadi HP"),
        "Sunbeam":            ("Rare",      24, 3, "stun",       1.50, "Sinar surya 1.5x ATK + peluang stun 25%"),
        "Prayer of Mending":  ("Rare",      32, 3, "heal",       2.55, "Doa kesembuhan 2.55x ATK ke 1 ally"),
        "Divine Dew":         ("Rare",      36, 4, "mass_heal",  1.00, "Embun ilahi pemulih seluruh party"),
        "Sanctuary Light":    ("Rare",      28, 3, "heal",       2.35, "Cahaya suaka pemulih ally kritis"),
        "Guiding Halo":       ("Rare",      22, 3, "buff_atk",   25.0, "Halo penuntun: ATK party +25% (3 ronde)"),
        "Mass Heal":          ("Epic",      45, 5, "mass_heal",  1.20, "Pulihkan HP seluruh party (1.2x ATK + 15)"),
        "Seraphim Embrace":   ("Epic",      36, 3, "heal",       3.00, "Pelukan Seraphim: heal besar 3.0x ATK ke 1 ally"),
        "Purge Evil":         ("Epic",      34, 4, "aoe_pierce", 0.90, "Cahaya pemurni AoE 0.9x ATK ignore DEF"),
        "Fountain of Life":   ("Epic",      42, 4, "mass_heal",  1.15, "Pancuran kehidupan untuk seluruh party"),
        "Sacred Renewal":     ("Epic",      34, 3, "cleanse_heal",2.60, "Pembaruan suci: heal kuat & hapus stun"),
        "Archangel Ward":     ("Epic",      30, 4, "buff_all",   24.0, "Perlindungan malaikat: ATK & SPD party +24%"),
        "Miracle Salvation":  ("Legendary", 52, 5, "mass_heal",  1.65, "Mujizat keselamatan: heal besar seluruh party"),
        "Tear of Goddess":    ("Legendary", 44, 3, "heal",       3.80, "Air mata dewi: pulihkan 3.8x ATK ke 1 ally"),
        "Heaven's Light":     ("Legendary", 50, 5, "aoe_stun",   1.55, "Cahaya surga AoE 1.55x ATK + stun 25%"),
        "Genesis Blessing":   ("Legendary", 48, 5, "mass_heal",  1.50, "Berkah penciptaan: pulihkan seluruh party"),
    },
    "Buffer": {
        "Attack Hymn":        ("Common",    20, 3, "buff_atk",   30.0, "Buff ATK seluruh party +30% (3 ronde)"),
        "Guard Hymn":         ("Common",    20, 3, "buff_def",   25.0, "Buff DEF seluruh party +25% (3 ronde)"),
        "March of Valor":     ("Common",    18, 3, "buff_atk",   25.0, "Mars keberanian: ATK party +25% (3 ronde)"),
        "Iron Chant":         ("Common",    18, 3, "buff_def",   22.0, "Nyanyian besi: DEF party +22% (3 ronde)"),
        "Swift Melody":       ("Common",    18, 3, "buff_spd",   20.0, "Melodi angin: SPD party +20% (3 ronde)"),
        "Sonic Note":         ("Common",    15, 2, "single",     1.45, "Nada sonik 1.45x ATK ke musuh"),
        "Courageous Beat":    ("Common",    19, 3, "buff_atk",   28.0, "Ketukan berani: ATK party +28% (3 ronde)"),
        "Shielding Tune":     ("Common",    19, 3, "buff_def",   24.0, "Nada pelindung: DEF party +24% (3 ronde)"),
        "Breeze Cadence":     ("Common",    17, 3, "buff_spd",   18.0, "Irama semilir: SPD party +18% (3 ronde)"),
        "Resonant Strike":    ("Common",    16, 2, "single",     1.50, "Serangan resonansi 1.5x ATK"),
        "Battle Ballad":      ("Rare",      22, 3, "buff_atk",   34.0, "Balada tempur: ATK party +34% (3 ronde)"),
        "Fortress Anthem":    ("Rare",      22, 3, "buff_def",   30.0, "Anthem benteng: DEF party +30% (3 ronde)"),
        "Gale Concerto":      ("Rare",      22, 3, "buff_spd",   25.0, "Konserto badai: SPD party +25% (3 ronde)"),
        "Mana Chorus":        ("Rare",      24, 4, "mana_gift",  20.0, "Koor mana: pulihkan +20 MP ke ally lain"),
        "Echoing Shock":      ("Rare",      24, 3, "aoe_slow",   0.70, "Gelombang gema AoE 0.7x ATK + slow"),
        "Inspiring Aria":     ("Rare",      24, 4, "buff_all",   20.0, "Aria inspirasi: ATK & SPD party +20%"),
        "Dissonant Chord":    ("Rare",      21, 3, "stun",       1.45, "Akord disonan 1.45x ATK + stun 25%"),
        "Hymn of Vigor":      ("Rare",      26, 3, "heal",       2.00, "Himne vitalitas: pulihkan HP 1 ally"),
        "Tactical Command":   ("Rare",      23, 3, "buff_atk",   35.0, "Komando taktis: ATK party +35% (3 ronde)"),
        "Aegis Serenade":     ("Rare",      23, 3, "buff_def",   32.0, "Serenade Aegis: DEF party +32% (3 ronde)"),
        "War Cry":            ("Epic",      25, 4, "buff_all",   25.0, "Buff ATK +25% & SPD +20% party (3 ronde)"),
        "Symphony of Wrath":  ("Epic",      28, 4, "buff_atk",   42.0, "Simfoni murka: ATK party +42% (3 ronde)"),
        "Bastion Oratorio":   ("Epic",      28, 4, "buff_def",   38.0, "Oratorio bastion: DEF party +38% (3 ronde)"),
        "Requiem Blast":      ("Epic",      34, 4, "aoe_stun",   0.90, "Ledakan Requiem AoE 0.9x ATK + stun 15%"),
        "Arcane Rhapsody":    ("Epic",      30, 4, "mana_gift",  30.0, "Rapsodi arkana: +30 MP ke semua ally"),
        "Heroic Overture":    ("Epic",      30, 4, "buff_all",   28.0, "Overture heroik: ATK & SPD party +28%"),
        "Sovereign Decree":   ("Legendary", 36, 5, "buff_all",   38.0, "Titah penguasa: ATK & SPD party +38% (3 ronde)"),
        "Celestial Choir":    ("Legendary", 42, 5, "mass_heal",  1.30, "Paduan suara langit: heal seluruh party"),
        "Anthem of Legends":  ("Legendary", 38, 5, "buff_atk",   50.0, "Anthem legenda: ATK party +50% (3 ronde)"),
        "Apocalypse Crescendo":("Legendary",46, 5, "aoe_pierce", 1.30, "Kresendo akhir zaman AoE 1.3x ATK ignore DEF"),
    },
    "Mage": {
        "Fireball":           ("Common",    30, 2, "aoe_stun",   0.75, "AoE 0.75x ATK ke semua musuh + stun 10%"),
        "Arcane Bolt":        ("Common",    16, 2, "single",     1.65, "Peluru arkana 1.65x ATK ke 1 musuh"),
        "Ice Shard":          ("Common",    22, 2, "aoe_slow",   0.55, "Pecahan es AoE 0.55x ATK + slow"),
        "Spark Wave":         ("Common",    24, 2, "aoe_stun",   0.62, "Gelombang listrik AoE 0.62x ATK + stun 10%"),
        "Flame Lance":        ("Common",    18, 2, "pierce",     1.48, "Tombak api 1.48x ATK menembus DEF"),
        "Wind Cutter":        ("Common",    22, 2, "aoe_slow",   0.58, "Pemotong angin AoE 0.58x ATK + slow"),
        "Dark Orb":           ("Common",    20, 2, "drain",      1.40, "Bola kegelapan 1.4x ATK + serap HP"),
        "Magma Splash":       ("Common",    26, 3, "aoe_stun",   0.68, "Percikan magma AoE 0.68x ATK + stun 10%"),
        "Mind Spike":         ("Common",    19, 2, "pierce",     1.50, "Pasak pikiran 1.5x ATK ignore DEF"),
        "Frost Bolt":         ("Common",    17, 2, "stun",       1.35, "Panah beku 1.35x ATK + peluang stun 20%"),
        "Chain Lightning":    ("Rare",      32, 3, "aoe_stun",   0.85, "Petir berantai AoE 0.85x ATK + stun 15%"),
        "Blizzard":           ("Rare",      34, 3, "aoe_slow",   0.80, "Badai salju AoE 0.8x ATK + slow 2 ronde"),
        "Void Ray":           ("Rare",      26, 3, "pierce",     1.75, "Sinar kehampaan 1.75x ATK ignore DEF"),
        "Inferno Pillar":     ("Rare",      34, 3, "aoe_stun",   0.88, "Pilar neraka AoE 0.88x ATK + stun 12%"),
        "Soul Siphon":        ("Rare",      26, 3, "drain",      1.65, "Penyedot jiwa 1.65x ATK + lifesteal 40%"),
        "Gravity Crush":      ("Rare",      32, 3, "aoe_slow",   0.82, "Tekanan gravitasi AoE 0.82x ATK + slow"),
        "Thunder Cage":       ("Rare",      25, 3, "stun",       1.68, "Penjara petir 1.68x ATK + stun 30%"),
        "Acid Tempest":       ("Rare",      35, 3, "aoe_pierce", 0.78, "Badai asam AoE 0.78x ATK ignore DEF"),
        "Plasma Burst":       ("Rare",      28, 3, "single",     2.05, "Ledakan plasma 2.05x ATK ke 1 musuh"),
        "Nether Flare":       ("Rare",      33, 3, "aoe_stun",   0.84, "Suar bawah tanah AoE 0.84x ATK + stun 12%"),
        "Frost Nova":         ("Epic",      40, 4, "aoe_slow",   0.95, "AoE es 0.95x ATK + slow -30% SPD (2 ronde)"),
        "Hellfire Storm":     ("Epic",      44, 4, "aoe_stun",   1.15, "Badai api neraka AoE 1.15x ATK + stun 18%"),
        "Arcane Barrage":     ("Epic",      42, 4, "aoe_pierce", 1.05, "Rentetan arkana AoE 1.05x ATK ignore DEF"),
        "Abyssal Vortex":     ("Epic",      40, 4, "aoe_slow",   1.00, "Pusaran jurang AoE 1.0x ATK + slow"),
        "Disintegrate":       ("Epic",      36, 3, "pierce",     2.25, "Sinar disintegrasi 2.25x ATK ignore DEF"),
        "Thunderstorm":       ("Epic",      45, 4, "aoe_stun",   1.18, "Badai petir AoE 1.18x ATK + stun 20%"),
        "Meteor":             ("Legendary", 60, 6, "aoe_stun",   2.00, "AoE 2.0x ATK + stun 25% ke semua musuh"),
        "Supernova":          ("Legendary", 58, 6, "aoe_pierce", 1.60, "Ledakan bintang AoE 1.6x ATK ignore DEF"),
        "Absolute Zero":      ("Legendary", 54, 5, "aoe_slow",   1.55, "Beku mutlak AoE 1.55x ATK + slow semua musuh"),
        "Cataclysm":          ("Legendary", 62, 6, "aoe_stun",   2.10, "Bencana kehancuran AoE 2.1x ATK + stun 25%"),
    },
}

# 60 Universal Skills (TIDAK ADA Taunt di sini — Taunt hanya milik Tanker!)
UNIVERSAL_SKILLS = {
    # Common (24)
    "Quick Slash":        ("Common",    12, 2, "single",     1.45, "Tebasan cepat 1.45x ATK ke musuh terlemah"),
    "Heavy Blow":         ("Common",    15, 2, "single",     1.55, "Pukulan berat 1.55x ATK"),
    "Lunging Thrust":     ("Common",    14, 2, "pierce",     1.30, "Tusukan menerjang 1.3x ATK ignore DEF"),
    "First Aid":          ("Common",    20, 2, "heal",       1.60, "Pertolongan pertama pemulih HP ally"),
    "Focus Breath":       ("Common",    16, 3, "buff_atk",   18.0, "Napas fokus: ATK party +18% (3 ronde)"),
    "Iron Skin Art":      ("Common",    16, 3, "buff_def",   18.0, "Teknik kulit besi: DEF party +18% (3 ronde)"),
    "Sprint Step":        ("Common",    15, 3, "buff_spd",   15.0, "Langkah cepat: SPD party +15% (3 ronde)"),
    "Low Kick":           ("Common",    14, 3, "stun",       1.20, "Tendangan bawah 1.2x ATK + stun 20%"),
    "Stone Throw":        ("Common",    12, 2, "single",     1.40, "Lemparan batu keras 1.4x ATK"),
    "Spinning Kick":      ("Common",    16, 2, "single",     1.58, "Tendangan berputar 1.58x ATK"),
    "Shoulder Tackle":    ("Common",    15, 3, "stun",       1.25, "Tabrakan bahu 1.25x ATK + stun 20%"),
    "Vigor Breathe":      ("Common",    18, 2, "heal",       1.55, "Pernapasan vitalitas pemulih HP"),
    "Keen Strike":        ("Common",    14, 2, "pierce",     1.32, "Serangan tajam 1.32x ATK ignore DEF"),
    "Leech Bite":         ("Common",    16, 2, "drain",      1.28, "Gigitan penghisap 1.28x ATK + lifesteal"),
    "Dust Sweep":         ("Common",    18, 3, "aoe_slow",   0.50, "Sapuan debu AoE 0.5x ATK + slow"),
    "Palm Strike":        ("Common",    13, 2, "single",     1.48, "Hantaman telapak 1.48x ATK"),
    "Knee Smash":         ("Common",    15, 2, "single",     1.52, "Hantaman lutut 1.52x ATK"),
    "Sand Toss":          ("Common",    14, 3, "stun",       1.18, "Lemparan pasir 1.18x ATK + stun 20%"),
    "Combat Roll":        ("Common",    16, 3, "buff_spd",   16.0, "Guling taktis: SPD party +16% (3 ronde)"),
    "Guard Up":           ("Common",    16, 3, "buff_def",   16.0, "Siaga bertahan: DEF party +16% (3 ronde)"),
    "Rally Call":         ("Common",    17, 3, "buff_atk",   20.0, "Seruan semangat: ATK party +20% (3 ronde)"),
    "Spark Slash":        ("Common",    15, 2, "single",     1.54, "Tebasan percikan 1.54x ATK"),
    "Frost Touch":        ("Common",    16, 2, "single",     1.50, "Sentuhan beku 1.5x ATK"),
    "Siphon Touch":       ("Common",    17, 2, "drain",      1.32, "Sentuhan serap 1.32x ATK + lifesteal"),
    # Rare (18)
    "Blood Drain":        ("Rare",      22, 3, "drain",      1.50, "Serang 1.5x ATK & serap 40% dmg jadi HP"),
    "Sonic Slash":        ("Rare",      20, 2, "pierce",     1.52, "Tebasan gelombang suara 1.52x ATK ignore DEF"),
    "Flame Slash":        ("Rare",      22, 2, "single",     1.82, "Tebasan api membara 1.82x ATK"),
    "Frost Slash":        ("Rare",      24, 3, "aoe_slow",   0.68, "Tebasan es AoE 0.68x ATK + slow"),
    "Shockwave":          ("Rare",      26, 3, "aoe_stun",   0.70, "Gelombang kejut AoE 0.7x ATK + stun 10%"),
    "Second Wind":        ("Rare",      26, 3, "heal",       2.15, "Napas kedua pemulih HP kritis"),
    "Battle Focus":       ("Rare",      22, 3, "buff_atk",   28.0, "Fokus tempur: ATK party +28% (3 ronde)"),
    "Steel Mentality":    ("Rare",      22, 3, "buff_def",   26.0, "Mental baja: DEF party +26% (3 ronde)"),
    "Haste Aura":         ("Rare",      22, 3, "buff_spd",   22.0, "Aura percepatan: SPD party +22% (3 ronde)"),
    "Crushing Blow":      ("Rare",      21, 3, "stun",       1.52, "Pukulan peremuk 1.52x ATK + stun 25%"),
    "Vital Pierce":       ("Rare",      21, 2, "pierce",     1.56, "Tusukan titik vital 1.56x ATK ignore DEF"),
    "Spirit Transfer":    ("Rare",      24, 4, "mana_gift",  18.0, "Transfer energi: +18 MP ke ally"),
    "Purify Herb":        ("Rare",      24, 3, "cleanse_heal",1.85, "Ramuan pemurni: heal & hapus stun ally"),
    "Gale Sweep":         ("Rare",      25, 3, "aoe_slow",   0.72, "Sapuan angin ribut AoE 0.72x ATK + slow"),
    "Vampiric Strike":    ("Rare",      23, 3, "drain",      1.55, "Serangan vampir 1.55x ATK + lifesteal"),
    "Lightning Jab":      ("Rare",      22, 3, "stun",       1.55, "Tusukan kilat 1.55x ATK + stun 25%"),
    "Armor Shatter":      ("Rare",      22, 2, "pierce",     1.58, "Pecahkan pelindung 1.58x ATK ignore DEF"),
    "Crimson Wave":       ("Rare",      27, 3, "aoe_stun",   0.72, "Gelombang merah AoE 0.72x ATK + stun 10%"),
    # Epic (12)
    "Thunder Bolt":       ("Epic",      28, 3, "stun",       1.90, "Petir 1.9x ATK ke 1 musuh + stun 35%"),
    "Soul Strike":        ("Epic",      30, 3, "pierce",     1.95, "Hantaman jiwa 1.95x ATK menembus DEF"),
    "Life Siphon":        ("Epic",      28, 3, "drain",      1.80, "Kuras nyawa 1.8x ATK + lifesteal 40%"),
    "Earth Cleave":       ("Epic",      34, 4, "aoe_stun",   0.92, "Belahan bumi AoE 0.92x ATK + stun 15%"),
    "Tempest Fury":       ("Epic",      34, 4, "aoe_slow",   0.90, "Amukan badai AoE 0.9x ATK + slow"),
    "Overdrive":          ("Epic",      28, 4, "buff_all",   24.0, "Overdrive: ATK & SPD party +24% (3 ronde)"),
    "Renewal Pulse":      ("Epic",      38, 4, "mass_heal",  1.10, "Denyut pembaruan: pulihkan seluruh party"),
    "Phantom Thrust":     ("Epic",      29, 3, "pierce",     1.92, "Tusukan bayangan 1.92x ATK ignore DEF"),
    "Gravity Wave":       ("Epic",      35, 4, "aoe_slow",   0.92, "Gelombang gravitasi AoE 0.92x ATK + slow"),
    "Dragon Fang":        ("Epic",      30, 3, "single",     2.20, "Taring naga 2.2x ATK ke 1 musuh"),
    "Mana Fountain":      ("Epic",      30, 4, "mana_gift",  28.0, "Pancuran mana: +28 MP ke seluruh party"),
    "Void Slash":         ("Epic",      36, 4, "aoe_pierce", 0.92, "Tebasan hampa AoE 0.92x ATK ignore DEF"),
    # Legendary (6)
    "Divine Judgment":    ("Legendary", 50, 5, "aoe_pierce", 1.35, "AoE 1.35x ATK menembus DEF semua musuh"),
    "Astral Nova":        ("Legendary", 52, 5, "aoe_stun",   1.65, "Nova astral AoE 1.65x ATK + stun 25%"),
    "Immortal Aura":      ("Legendary", 40, 5, "buff_all",   35.0, "Aura abadi: ATK & SPD party +35% (3 ronde)"),
    "Eternity Heal":      ("Legendary", 46, 5, "mass_heal",  1.40, "Cahaya keabadian: pulihkan seluruh party"),
    "Oblivion Strike":    ("Legendary", 42, 4, "pierce",     2.45, "Hantaman kehampaan 2.45x ATK ignore DEF"),
    "Soul Harvest":       ("Legendary", 40, 4, "drain",      2.15, "Panen jiwa 2.15x ATK + lifesteal 40%"),
}

# 15 Cursed Skills (cursed = 1, tier = "Cursed") — HANYA dari kegagalan Soul Overload!
# Format: nama: (tier, mp_cost, cd, kind, mult, description)
CURSED_SKILLS_POOL = {
    "Soul Hemorrhage":      ("Cursed", 18, 2, "cursed_self_dmg_pierce", 2.20, "Serang 1 musuh 220% ATK (abaikan DEF), namun menguras 25% Max HP pemakai."),
    "Discordant Wail":      ("Cursed", 15, 3, "cursed_aoe_ally_debuff", 0.60, "Serangan AoE 60% ATK ke semua musuh, namun menurunkan DEF seluruh rekan party -25% selama 2 ronde."),
    "Frenzied Betrayal":    ("Cursed", 12, 2, "cursed_betrayal_hit",    1.60, "Serang 1 target 160% ATK, namun peluang 40% salah sasaran menghantam rekan satu party sendiri."),
    "Abyssal Gluttony":     ("Cursed", 10, 3, "cursed_mp_leech_party",  1.10, "Menyedot 30% MP saat ini dari seluruh rekan party lain untuk memulihkan 25% Max HP pemakai dan menyerang 1 musuh 110% ATK."),
    "Shattered Mind Blast": ("Cursed", 20, 3, "cursed_aoe_sanity_drain",1.30, "Serangan AoE 130% ATK ke seluruh musuh, namun mengurangi sanity pemakai -10.0 dan memberi stun pada diri sendiri 1 ronde."),
    "Flesh Sacrifice":      ("Cursed", 14, 3, "cursed_zero_def_burst",  1.80, "Memangkas DEF pemakai menjadi 0 selama 2 ronde demi menaikkan ATK +80% (2 ronde) dan menerjang 1 musuh 180% ATK."),
    "Corrupted Heal":       ("Cursed", 16, 2, "cursed_poison_heal",     0.45, "Heal rekan party paling kritis 45% Max HP, namun membakar 20% Max HP pemakai dan menurunkan ATK target -20% (2 ronde)."),
    "Blind Rampage":        ("Cursed", 15, 3, "cursed_blind_multihit",  0.75, "Menyerang musuh acak 3 kali (75% ATK per hit); tiap tebasan peluang 50% meleset dan menguras 5% Max HP pemakai per ayunan."),
    "Parasitic Leech":      ("Cursed", 12, 3, "cursed_ally_hp_steal",   1.00, "Mencuri 15% Max HP dari rekan satu party lain yang memiliki HP tertinggi untuk menyembuhkan diri sendiri (jika sendirian, melukai diri sendiri 10% Max HP)."),
    "Mana Burnout":         ("Cursed", 10, 3, "cursed_all_mp_pierce",   1.50, "Menguras 100% sisa MP pemakai hingga 0 untuk melepaskan serangan tembus DEF 150% ATK ke 1 musuh."),
    "Death Wish Gamble":    ("Cursed", 20, 3, "cursed_gamble_strike",   3.00, "50% peluang menghasilkan tebasan 300% ATK ke 1 musuh, 50% peluang gagal total (0 damage) dan HP pemakai terpangkas menjadi 1 HP."),
    "Hollow Echo":          ("Cursed", 10, 2, "cursed_skip_self_harm",  0.00, "Jiwa gagal merespons; menghabiskan MP sia-sia, melewatkan giliran, dan melukai diri sendiri 8% Max HP."),
    "Cursed Provocation":   ("Cursed", 12, 3, "cursed_suicide_taunt",   0.00, "Memaksa seluruh musuh mengincar pemakai selama 2 ronde (efek Taunt), namun menurunkan DEF pemakai -35% selama 2 ronde."),
    "Rotting Miasma":       ("Cursed", 16, 3, "cursed_all_field_decay", 0.10, "Mengurangi 10% HP saat ini dari SEMUA unit yang hidup di medan tempur (seluruh musuh sekaligus seluruh rekan satu party)."),
    "Phantom Pain Strike":  ("Cursed", 15, 2, "cursed_recoil_stun",     1.40, "Menyerang 1 musuh 140% ATK + peluang stun, namun pemakai menerima 50% dari damage yang masuk sebagai recoil ke diri sendiri."),
}
CURSED_SKILLS = CURSED_SKILLS_POOL

# Gabungan seluruh 240 skill normal: nama -> (cls, tier, mp_cost, cd, kind, mult, description)
SKILLS = {}
for _cls_name, _sdict in CLASS_SKILLS.items():
    for _sname, (_t, _mp, _cd, _k, _m, _d) in _sdict.items():
        SKILLS[_sname] = (_cls_name, _t, _mp, _cd, _k, _m, _d)
for _sname, (_t, _mp, _cd, _k, _m, _d) in UNIVERSAL_SKILLS.items():
    SKILLS[_sname] = ("Universal", _t, _mp, _cd, _k, _m, _d)

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


# ===================== HERO SYNTHESIS (MASTER KONSTANTA) =====================
# Konstanta master mekanik Hero Synthesis (terinspirasi manhwa "Pick Me Up:
# Infinite Gacha"). Sesuai arsitektur Dua Lapisan Data (README seksi 3):
# SEMUA angka di bawah adalah master data (di sini); data pemain tetap di
# saves/<username>.json. RAHASIA: nilai-nilai ini TIDAK pernah ditampilkan
# ke pemain di UI apapun (aturan seksi 14).
VESSEL_CAP_BY_STAR = {1: 3, 2: 5, 3: 7, 4: 10, 5: 14, 6: 18, 7: 25}
STAT_ABSORB_RATE_BY_STAR = {
    1: 0.25,
    2: 0.32,
    3: 0.40,
    4: 0.50,
    5: 0.60,
    6: 0.72,
    7: 0.85,
}
SANITY_DRAIN_BASE = 8.0
EGO_OVERRIDE_RATIO = 1.6

# Soul Overload & Penalti Kegagalan (Vessel Breakdown)
OVERLOAD_SUCCESS_CURVE = (0.95, 0.89, 0.81, 0.72, 0.62, 0.51, 0.39, 0.26, 0.15, 0.08, 0.05)
OVERLOAD_FAIL_STAT_DECAY_RANGE = (0.30, 0.99)
OVERLOAD_FAIL_ABILITY_DESTROY_RATE = 0.60
CURSED_SKILL_GAIN_RATE = 0.50
CURSED_TRAIT_GAIN_RATE = 0.50
OVERLOAD_FAIL_SANITY_MULT = 3.0
OVERLOAD_SUCCESS_SANITY_MULT = 1.5

# Pewarisan Skill & Trait Tanpa Cap + Resonance Stat
FULL_INHERIT_RATE_BY_STAR = {1: 0.10, 2: 0.12, 3: 0.15, 4: 0.18, 5: 0.22, 6: 0.26, 7: 0.30}
SINGLE_SKILL_INHERIT_BASE = 0.35
SINGLE_TRAIT_INHERIT_BASE = 0.25
INHERIT_STAR_BONUS = 0.05
FULL_RESONANCE_STAT_MULT = 1.50
PARTIAL_RESONANCE_STAT_BONUS = 0.10

SYNTHESIS_CONFIG = {
    "VESSEL_CAP_BY_STAR": dict(VESSEL_CAP_BY_STAR),
    "STAT_ABSORB_RATE_BY_STAR": dict(STAT_ABSORB_RATE_BY_STAR),
    "SANITY_DRAIN_BASE": SANITY_DRAIN_BASE,
    "EGO_OVERRIDE_RATIO": EGO_OVERRIDE_RATIO,
    "OVERLOAD_SUCCESS_CURVE": OVERLOAD_SUCCESS_CURVE,
    "OVERLOAD_FAIL_STAT_DECAY_RANGE": OVERLOAD_FAIL_STAT_DECAY_RANGE,
    "OVERLOAD_FAIL_ABILITY_DESTROY_RATE": OVERLOAD_FAIL_ABILITY_DESTROY_RATE,
    "CURSED_SKILL_GAIN_RATE": CURSED_SKILL_GAIN_RATE,
    "CURSED_TRAIT_GAIN_RATE": CURSED_TRAIT_GAIN_RATE,
    "OVERLOAD_FAIL_SANITY_MULT": OVERLOAD_FAIL_SANITY_MULT,
    "OVERLOAD_SUCCESS_SANITY_MULT": OVERLOAD_SUCCESS_SANITY_MULT,
    "FULL_INHERIT_RATE_BY_STAR": dict(FULL_INHERIT_RATE_BY_STAR),
    "SINGLE_SKILL_INHERIT_BASE": SINGLE_SKILL_INHERIT_BASE,
    "SINGLE_TRAIT_INHERIT_BASE": SINGLE_TRAIT_INHERIT_BASE,
    "INHERIT_STAR_BONUS": INHERIT_STAR_BONUS,
    "FULL_RESONANCE_STAT_MULT": FULL_RESONANCE_STAT_MULT,
    "PARTIAL_RESONANCE_STAT_BONUS": PARTIAL_RESONANCE_STAT_BONUS,
}

# ==================== HERO SELL (BURSA PAHLAWAN) CONFIG ====================
# Harga jual hero bergantung pada:
# 1. Star dasar & Level (semakin tinggi level, semakin berharga)
# 2. Stat efektif/akumulatif (HP, ATK, DEF, SPD, MP)
# 3. Jumlah trait & skill yang dimiliki (banyak kemampuan = nilai tinggi)
# 4. Kelangkaan (tier) tiap trait (Common, Rare, Epic, Legendary; Cursed)
# 5. Kelangkaan (tier) tiap skill
# 6. Pengali khusus class Mage: 3.0x lipat (Canon Pick Me Up: Mage sangat langka & mahal)
HERO_SELL_CONFIG = {
    "BASE_PRICE_BY_STAR": {
        1: 150,
        2: 400,
        3: 1000,
        4: 3000,
        5: 8000,
        6: 20000,
        7: 50000,
    },
    "LEVEL_MULT_BASE": 25,
    "LEVEL_EXP_FACTOR": 10.0,
    "LEVEL_EXP_POWER": 1.3,
    "STAT_WEIGHTS": {
        "hp": 0.5,
        "atk": 3.0,
        "def": 2.5,
        "spd": 4.0,
        "mp": 0.8,
    },
    "COUNT_VALUE_PER_TRAIT": 100,
    "COUNT_VALUE_PER_SKILL": 75,
    "TRAIT_TIER_VALUE": {
        "Common": 100,
        "Rare": 300,
        "Epic": 900,
        "Legendary": 3000,
        "Cursed": -100,
    },
    "SKILL_TIER_VALUE": {
        "Common": 60,
        "Rare": 180,
        "Epic": 550,
        "Legendary": 1800,
        "Cursed": -50,
    },
    "MAGE_MULTIPLIER": 3.0,
    "MIN_PRICE": 100,
}


def get_overload_success_rate(synth_count_or_hero, vessel_cap=None, star=None):
    """Hitung peluang keberhasilan sintesis (RAHASIA, 0.05..1.0):
      - Selama synth_count < vessel_cap -> 1.0 (100% berhasil).
      - Saat masuk fase Soul Overload (synth_count >= vessel_cap) ->
        OVERLOAD_SUCCESS_CURVE[min(delta, len(curve)-1)] di mana
        delta = synth_count - vessel_cap.
    Mendukung pemanggilan fleksibel:
      - get_overload_success_rate(hero_obj)
      - get_overload_success_rate(synth_count, vessel_cap)
      - get_overload_success_rate(synth_count, star=1)
      - get_overload_success_rate(delta)  (bila hanya 1 argumen int diberikan)."""
    curve = SYNTHESIS_CONFIG["OVERLOAD_SUCCESS_CURVE"]
    if hasattr(synth_count_or_hero, "synth_count"):
        sc = int(getattr(synth_count_or_hero, "synth_count", 0))
        if hasattr(synth_count_or_hero, "vessel_cap"):
            cap = int(synth_count_or_hero.vessel_cap())
        else:
            s = max(1, min(7, int(getattr(synth_count_or_hero, "star", 1))))
            cap = int(VESSEL_CAP_BY_STAR.get(s, 3))
        delta = sc - cap
    elif vessel_cap is not None:
        delta = int(synth_count_or_hero) - int(vessel_cap)
    elif star is not None:
        s = max(1, min(7, int(star)))
        cap = int(VESSEL_CAP_BY_STAR.get(s, 3))
        delta = int(synth_count_or_hero) - cap
    else:
        delta = int(synth_count_or_hero)
    if delta < 0:
        return 1.0
    idx = min(delta, len(curve) - 1)
    return float(curve[idx])


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
      force=True -> refresh HANYA tabel data game (hero_names, traits, skills,
        items_master, class_stats, star_mults) dari seed. Tabel accounts
        (username & password pemain) TIDAK PERNAH disentuh, dan file save
        pemain (saves/*.json) tidak ada hubungannya dengan database —
        jadi update data game tidak akan pernah menghilangkan akun/progress.
      wipe_accounts=True -> HAPUS juga semua akun. DESTRUKTIF; hanya untuk
        reset total yang disengaja (dipisah dari force agar tak terjadi
        kehilangan akun karena salah flag).
    Idempotent: seeding memakai INSERT OR IGNORE/REPLACE sehingga aman dipanggil ulang."""
    p = path or DB_PATH
    conn = get_db(p, timeout=10.0)
    try:
        cur = conn.cursor()
        _create_tables(conn)
        if wipe_accounts:
            cur.execute("DELETE FROM accounts")
        if force:
            # Hapus isi tabel DATA GAME saja; accounts dibiarkan utuh.
            for t in ("hero_names", "traits", "skills", "items_master",
                      "class_stats", "star_mults"):
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
    # Bersihkan tabel lama `perks` (telah digantikan oleh tabel `traits`)
    cur.execute("DROP TABLE IF EXISTS perks")
    # 1) hero_names: ribuan kombinasi (depan, belakang, gelar)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS hero_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name  TEXT NOT NULL,
            title      TEXT,
            UNIQUE(first_name, last_name, title)
        )""")
    # 2) traits: nama unik + tier + deskripsi efek + kolom boolean cursed (0/1)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS traits (
            name        TEXT PRIMARY KEY,
            tier        TEXT NOT NULL,
            description TEXT NOT NULL,
            cursed      INTEGER NOT NULL DEFAULT 0
        )""")
    trait_cols = [r[1] for r in cur.execute("PRAGMA table_info(traits)").fetchall()]
    if "cursed" not in trait_cols:
        cur.execute("ALTER TABLE traits ADD COLUMN cursed INTEGER NOT NULL DEFAULT 0")
    # 2b) skills: pool 240 skill normal + 15 cursed skill (beserta kolom cursed 0/1)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            name        TEXT PRIMARY KEY,
            cls         TEXT NOT NULL DEFAULT 'Universal',
            tier        TEXT NOT NULL,
            mp_cost     INTEGER NOT NULL,
            cd          INTEGER NOT NULL,
            kind        TEXT NOT NULL,
            mult        REAL NOT NULL,
            description TEXT NOT NULL,
            cursed      INTEGER NOT NULL DEFAULT 0
        )""")
    skill_cols = [r[1] for r in cur.execute("PRAGMA table_info(skills)").fetchall()]
    if "cls" not in skill_cols:
        cur.execute("ALTER TABLE skills ADD COLUMN cls TEXT NOT NULL DEFAULT 'Universal'")
    if "cursed" not in skill_cols:
        cur.execute("ALTER TABLE skills ADD COLUMN cursed INTEGER NOT NULL DEFAULT 0")
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
    """Isi semua tabel seed. INSERT OR IGNORE/REPLACE = idempotent."""
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
    # traits: 48 normal traits (cursed=0) + 10 cursed traits (cursed=1)
    trait_rows = [(n, t, d, 0) for n, (t, d) in TRAITS.items()]
    trait_rows += [(n, t, d, 1) for n, (t, d) in CURSED_TRAITS_POOL.items()]
    cur.executemany(
        "INSERT OR REPLACE INTO traits (name, tier, description, cursed) VALUES (?,?,?,?)",
        trait_rows)
    # skills: 240 normal skills (cursed=0) + 15 cursed skills (cursed=1)
    skill_rows = [(n, c, t, mp, cd, k, m, d, 0) for n, (c, t, mp, cd, k, m, d) in SKILLS.items()]
    skill_rows += [("Cursed", t, mp, cd, k, m, d, n) for n, (t, mp, cd, k, m, d) in CURSED_SKILLS_POOL.items()]
    cur.executemany(
        "INSERT OR REPLACE INTO skills (name, cls, tier, mp_cost, cd, kind, mult, description, cursed) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [(n, c, t, mp, cd, k, m, d, 0) for n, (c, t, mp, cd, k, m, d) in SKILLS.items()] +
        [(n, "Cursed", t, mp, cd, k, m, d, 1) for n, (t, mp, cd, k, m, d) in CURSED_SKILLS_POOL.items()])
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


def get_traits(path=None, include_cursed=True):
    """Return list of dict dari tabel traits:
    [{'name': str, 'tier': str, 'description': str, 'cursed': bool}, ...]."""
    by_name = {}
    try:
        conn = get_db(path)
        try:
            for r in conn.execute("SELECT name, tier, description, cursed FROM traits"):
                is_c = bool(r["cursed"])
                if not include_cursed and is_c:
                    continue
                by_name[r["name"]] = {
                    "name": r["name"],
                    "tier": r["tier"],
                    "description": r["description"],
                    "cursed": is_c,
                }
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    for n, (t, d) in TRAITS.items():
        by_name.setdefault(n, {"name": n, "tier": t, "description": d, "cursed": False})
    if include_cursed:
        for n, (t, d) in CURSED_TRAITS_POOL.items():
            by_name.setdefault(n, {"name": n, "tier": t, "description": d, "cursed": True})
    return list(by_name.values())


# Alias backward-compatibility
get_perks = get_traits


def get_cursed_traits(path=None):
    """Return list of dict seluruh Cursed Traits (cursed == True)."""
    return [t for t in get_traits(path, include_cursed=True) if t.get("cursed")]


def load_traits(path=None, include_cursed=True):
    """Return {nama_trait: (tier, deskripsi)} dari tabel traits dengan fallback seed."""
    out = {}
    for item in get_traits(path, include_cursed=include_cursed):
        out[item["name"]] = (item["tier"], item["description"])
    return out


# Alias backward-compatibility untuk kode lama
load_perks = load_traits


def get_skills(path=None, include_cursed=True):
    """Return list of dict dari tabel skills (dengan kolom boolean 'cursed')."""
    return list(load_skills(path, include_cursed=include_cursed).values())


def get_cursed_skills(path=None):
    """Return list of dict seluruh Cursed Skills (cursed == True)."""
    return [s for s in get_skills(path, include_cursed=True) if s.get("cursed")]


def load_skills(path=None, include_cursed=True):
    """Return {nama_skill: {name, cls, tier, mp_cost, cd, kind, mult, description, cursed}}
    dengan fallback konstanta seed bila database belum ter-update."""
    out = {}
    try:
        conn = get_db(path)
        try:
            for r in conn.execute(
                    "SELECT name, cls, tier, mp_cost, cd, kind, mult, description, cursed FROM skills"):
                is_c = bool(r["cursed"])
                if not include_cursed and is_c:
                    continue
                out[r["name"]] = {
                    "name": r["name"],
                    "cls": r["cls"] or "Universal",
                    "tier": r["tier"],
                    "mp_cost": int(r["mp_cost"]),
                    "cd": int(r["cd"]),
                    "kind": r["kind"],
                    "mult": float(r["mult"]),
                    "description": r["description"],
                    "cursed": is_c,
                }
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    # Pastikan seluruh 240 skill normal dari seed selalu tersedia
    for n, (c, t, mp, cd, k, m, d) in SKILLS.items():
        out.setdefault(n, {
            "name": n, "cls": c, "tier": t, "mp_cost": mp, "cd": cd,
            "kind": k, "mult": m, "description": d, "cursed": False,
        })
    if include_cursed:
        for n, (t, mp, cd, k, m, d) in CURSED_SKILLS_POOL.items():
            out.setdefault(n, {
                "name": n, "cls": "Cursed", "tier": t, "mp_cost": mp, "cd": cd,
                "kind": k, "mult": m, "description": d, "cursed": True,
            })
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
    print("  traits       : %d trait (termasuk %d cursed)" % (
        len(load_traits(p)), len(get_cursed_traits(p))))
    print("  skills       : %d skill (termasuk %d cursed)" % (
        len(load_skills(p)), len(get_cursed_skills(p))))
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
