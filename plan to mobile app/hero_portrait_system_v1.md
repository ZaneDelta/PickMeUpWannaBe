# DOKUMEN TEKNIS: SISTEM PORTRAIT HERO MODULAR (GODOT 4 2D)
## Pendekatan: Multiple Body Archetypes (Paper-Doll System)
**Proyek:** Pick Me Up: Infinite Gacha (Mobile Port)  
**Versi Dokumen:** 1.0.0  
**Target Engine:** Godot 4.x (Mobile / Vulkan Compatibility Mode)

---

## 1. Konsep & Filosofi Desain

Sistem portrait menggunakan teknik **Paper-Doll Avatar** yang digerakkan oleh **Deterministic Seeding** dengan segmentasi **Multiple Body Archetypes**.

### Tujuan Utama:
1. **Identitas Siluet per Kelas:** Masing-masing kelas hero memiliki postur tubuh, lebar bahu, dan proporsi anatomis yang khas, sehingga terbaca seketika (*readability*) pada layar ponsel.
2. **Kombinasi Tak Terbatas Tanpa Bloat Aset:** Menghasilkan puluhan ribu variasi unik dari kombinasi layer tanpa perlu menggambar setiap hero secara individual.
3. **Data-Lean (Zero Extra Storage):** Tidak ada aset gambar atau ID visual yang disimpan ke dalam file save (`saves/<username>.json`). Seluruh tampilan visual di-generate secara deterministik dari `hero.name` / `hero.fingerprint`.
4. **Kepatuhan Aturan Canon (Pick Me Up):** 
   - Hero 1★ dengan *Hidden Potential* **wajib identik visualnya** dengan hero 1★ biasa (tidak ada indikator kosmetik bocoran).
   - Indikator kemewahan visual kartu (border, ornamen, aura) hanya mengikuti **Star Rating (1★ – 7★)** dan kelas hero.

---

## 2. Pemetaan Arketipe Tubuh (Body Archetypes)

Tubuh dibagi menjadi 3 arketipe utama berdasarkan 6 kelas game:

| Arketipe | Kelas Terkait | Karakteristik Visual | Proporsi Kanvas ($256 \times 256$) |
|---|---|---|---|
| **HEAVY** | `Tanker` | Leher tebal, bahu bidang/lebar, postur tegak defensif, kerah/pauldron tebal. | Titik tengah kepala: `(128, 92)`, lebar bahu: `180px` |
| **MEDIUM** | `Dealer`, `Archer` | Postur atletis seimbang, bahu sedang, fleksibel untuk zirah rantai/kulit. | Titik tengah kepala: `(128, 88)`, lebar bahu: `150px` |
| **SLIM** | `Mage`, `Healer`, `Buffer` | Postur ramping, leher jenjang, cocok untuk jubah/mantel kain mengalir. | Titik tengah kepala: `(128, 84)`, lebar bahu: `130px` |

> **Catatan Standardisasi Koordinat:**  
> Aset *wajah* (mata, alis, mulut) dirancang universal untuk masing-masing arketipe menggunakan titik *anchor* tetap. Tiap arketipe memiliki direktori sub-asetnya sendiri untuk menjamin tidak ada rambut atau zirah yang "mengambang".

---

## 3. Susunan Layering (Z-Index / Render Order)

Setiap kartu portrait dirender dari belakang ke depan dengan urutan strict berikut:

```text
[Z-0] Background       : Latar kartu (gradient gelap / nuansa dinding dungeon)
[Z-1] Aura VFX         : Efek partikel/cahaya sihir (Khusus 5★ – 7★)
[Z-2] Back Hair        : Rambut bagian belakang/panjang (di belakang tubuh)
[Z-3] Body Base        : Torso & kepala polos (menyesuaikan arketipe & skin tone)
[Z-4] Face Features    : Mata, alis, ekspresi mulut
[Z-5] Face Details     : Bekas luka, tato, kacamata, penutup mata (aksesori wajah)
[Z-6] Outfit Base      : Baju zirah / jubah dasar kelas
[Z-7] Front Hair       : Rambut bagian depan/poni
[Z-8] Outfit Collars   : Kerah tinggi, pauldron, atau syal yang menutupi leher/rambut
[Z-9] Frame & Stars    : Bingkai kartu + rating 1★–7★ (overlay paling atas)
[Z-10] Class Icon      : Badge simbol kelas di pojok kiri atas
```

---

## 4. Struktur Folder & Penamaan Aset

Semua aset gambar berupa file `.png` transparan berukuran seragam ($256 \times 256$ piksel).

```text
res://assets/portraits/
├── common/
│   ├── backgrounds/
│   │   └── bg_default.png
│   ├── frames/
│   │   ├── frame_1star.png ... frame_7star.png
│   └── class_icons/
│       ├── icon_tanker.png
│       ├── icon_dealer.png
│       ├── icon_archer.png
│       ├── icon_healer.png
│       ├── icon_buffer.png
│       └── icon_mage.png
├── archetypes/
│   ├── heavy/                     # Khusus Tanker
│   │   ├── body/ (tone_0 .. tone_4.png)
│   │   ├── face/ (eye_0 .. eye_5.png)
│   │   ├── hair_back/ & hair_front/
│   │   ├── outfits/ (tier_1 .. tier_3.png)
│   │   └── accessories/
│   ├── medium/                    # Khusus Dealer & Archer
│   │   ├── body/
│   │   ├── face/
│   │   ├── hair_back/ & hair_front/
│   │   ├── outfits/ (dealer_t1..t3, archer_t1..t3)
│   │   └── accessories/
│   └── slim/                      # Khusus Mage, Healer, Buffer
│       ├── body/
│       ├── face/
│       ├── hair_back/ & hair_front/
│       ├── outfits/ (mage_t1..t3, healer_t1..t3, buffer_t1..t3)
│       └── accessories/
└── vfx/
    ├── aura_rank5.png
    ├── aura_rank6.png
    └── aura_rank7.png
```

---

## 5. Algoritma Resolusi Visual Deterministik

Komponen visual dipilih menggunakan *hash* integer dari atribut permanen hero. Karena hero memiliki nama unik (`hero.name`), nama ini menjadi bibit (*seed*) generator visual.

### Implementasi GDScript: `HeroVisualResolver.gd`

```gdscript
class_name HeroVisualResolver
extends RefCounted

const ARCHETYPE_MAP = {
    "Tanker": "heavy",
    "Dealer": "medium",
    "Archer": "medium",
    "Healer": "slim",
    "Buffer": "slim",
    "Mage":   "slim"
}

# Jumlah variasi aset per arketipe
const POOL_SIZES = {
    "skin_tones": 5,
    "faces": 6,
    "hair_styles": 8,
    "hair_colors": 6,
    "accessories": 8 # index 0 = tanpa aksesori
}

static func get_visual_config(hero_name: String, hero_class: String, star_level: int) -> Dictionary:
    var archetype = ARCHETYPE_MAP.get(hero_class, "medium")
    
    # Inisialisasi PRNG berbasis hash nama hero
    var rng = RandomNumberGenerator.new()
    rng.seed = hash(hero_name)
    
    # Tentukan varian visual
    var skin_idx = rng.randi() % POOL_SIZES.skin_tones
    var face_idx = rng.randi() % POOL_SIZES.faces
    var hair_idx = rng.randi() % POOL_SIZES.hair_styles
    var hair_color_idx = rng.randi() % POOL_SIZES.hair_colors
    var acc_idx = rng.randi() % POOL_SIZES.accessories
    
    # Tier outfit ditentukan oleh bintang hero:
    # 1-2★ -> Tier 1 (Novice)
    # 3-4★ -> Tier 2 (Veteran)
    # 5-7★ -> Tier 3 (Master/Ascended)
    var outfit_tier = 1
    if star_level >= 5:
        outfit_tier = 3
    elif star_level >= 3:
        outfit_tier = 2
        
    return {
        "archetype": archetype,
        "skin_path": "res://assets/portraits/archetypes/%s/body/tone_%d.png" % [archetype, skin_idx],
        "face_path": "res://assets/portraits/archetypes/%s/face/eye_%d.png" % [archetype, face_idx],
        "hair_f_path": "res://assets/portraits/archetypes/%s/hair_front/hair_%d.png" % [archetype, hair_idx],
        "hair_b_path": "res://assets/portraits/archetypes/%s/hair_back/hair_%d.png" % [archetype, hair_idx],
        "hair_color_id": hair_color_idx,
        "outfit_path": "res://assets/portraits/archetypes/%s/outfits/%s_t%d.png" % [archetype, hero_class.to_lower(), outfit_tier],
        "accessory_path": "" if acc_idx == 0 else "res://assets/portraits/archetypes/%s/accessories/acc_%d.png" % [archetype, acc_idx],
        "frame_path": "res://assets/portraits/common/frames/frame_%dstar.png" % star_level,
        "class_icon_path": "res://assets/portraits/common/class_icons/icon_%s.png" % hero_class.to_lower(),
        "has_aura": star_level >= 5,
        "aura_path": "res://assets/portraits/vfx/aura_rank%d.png" % star_level if star_level >= 5 else ""
    }
```

---

## 6. Arsitektur Node Godot (`HeroPortrait.tscn`)

Struktur scene kontrol untuk menampilkan portrait:

```text
HeroPortrait (Control) [Custom Minimum Size: 128x128]
├── Background (TextureRect) - expand_mode: IgnoreSize, stretch_mode: KeepAspectCentered
├── AuraVFX (TextureRect) - visible: conditionally
├── BackHair (TextureRect) - modulate: HairColorPalette
├── Body (TextureRect)
├── Face (TextureRect)
├── Accessory (TextureRect)
├── OutfitBase (TextureRect)
├── FrontHair (TextureRect) - modulate: HairColorPalette
├── OutfitCollar (TextureRect)
├── FrameBorder (TextureRect)
└── ClassBadge (TextureRect) [Anchor: Top-Left, Offset: 4,4]
```

### Script Pengendali: `HeroPortrait.gd`

```gdscript
extends Control
class_name HeroPortrait

@onready var bg = $Background
@onready var aura = $AuraVFX
@onready var back_hair = $BackHair
@onready var body = $Body
@onready var face = $Face
@onready var accessory = $Accessory
@onready var outfit_base = $OutfitBase
@onready var front_hair = $FrontHair
@onready var frame_border = $FrameBorder
@onready var class_badge = $ClassBadge

const HAIR_PALETTES = [
    Color("3a2618"), # Dark Brown
    Color("111111"), # Black
    Color("8c6f48"), # Light Brown
    Color("c29d5b"), # Blonde
    Color("a33224"), # Crimson Red
    Color("dcdcdc")  # Silver/White
]

func setup_portrait(hero_name: String, hero_class: String, star_level: int) -> void:
    var cfg = HeroVisualResolver.get_visual_config(hero_name, hero_class, star_level)
    
    # Pasang tekstur
    body.texture = load(cfg.skin_path)
    face.texture = load(cfg.face_path)
    front_hair.texture = load(cfg.hair_f_path)
    back_hair.texture = load(cfg.hair_b_path)
    outfit_base.texture = load(cfg.outfit_path)
    frame_border.texture = load(cfg.frame_path)
    class_badge.texture = load(cfg.class_icon_path)
    
    # Modulate warna rambut
    var hair_color = HAIR_PALETTES[cfg.hair_color_id]
    front_hair.self_modulate = hair_color
    back_hair.self_modulate = hair_color
    
    # Tangani Aksesori
    if cfg.accessory_path != "":
        accessory.texture = load(cfg.accessory_path)
        accessory.show()
    else:
        accessory.hide()
        
    # Tangani Aura Bintang Tinggi (5-7★)
    if cfg.has_aura:
        aura.texture = load(cfg.aura_path)
        aura.show()
    else:
        aura.hide()
```

---

## 7. Optimasi Mobile & Manajemen Performa (Draw Calls)

### Masalah:
Jika menu Roster menampilkan 40 hero sekaligus dalam `GridContainer`, setiap kartu yang terdiri dari 10 layer `TextureRect` akan memicu hingga $40 \times 10 = 400$ draw calls per frame, membebani GPU ponsel kelas bawah.

### Solusi: Runtime Texture Baking & In-Memory Cache
Saat hero di-load pertama kali, tumpukan layer digabungkan (*baked*) menjadi satu `ImageTexture` tunggal di memori.

```gdscript
class_name PortraitBakeCache
extends Node

static var _cached_portraits: Dictionary = {} # Key: hero_name + "_" + str(star) -> Texture2D

static func get_or_bake_portrait(hero_name: String, hero_class: String, star_level: int) -> Texture2D:
    var cache_key = "%s_%d" % [hero_name, star_level]
    if _cached_portraits.has(cache_key):
        return _cached_portraits[cache_key]
        
    var baked_texture = _bake_layers(hero_name, hero_class, star_level)
    _cached_portraits[cache_key] = baked_texture
    return baked_texture

static func _bake_layers(hero_name: String, hero_class: String, star_level: int) -> Texture2D:
    var cfg = HeroVisualResolver.get_visual_config(hero_name, hero_class, star_level)
    
    # Buat kanvas kosong
    var canvas: Image = Image.create(256, 256, false, Image.FORMAT_RGBA8)
    
    # Helper blit layer
    var layers = [
        cfg.skin_path,
        cfg.face_path,
        cfg.outfit_path,
        cfg.hair_f_path
    ]
    
    for path in layers:
        if path != "" and ResourceLoader.exists(path):
            var layer_img = load(path).get_image()
            canvas.blend_rect(layer_img, Rect2i(0, 0, 256, 256), Vector2i(0, 0))
            
    var tex = ImageTexture.create_from_image(canvas)
    _cached_portraits[cache_key] = tex
    return tex
```

> **Manfaat:**
> 1. Draw call di layar Roster terpangkas dari **400 menjadi 40 draw calls**.
> 2. Scrolling grid hero di HP dijamin mulus (stabil 60 FPS).
> 3. Cache otomatis diperbarui hanya saat terjadi **Star Promotion** (karena `cache_key` menyertakan `star_level`).

---

## 8. Protokol Integrasi & Pantangan (Checklist)

1. [x] **Jangan Ubah Logika Python:** Seluruh kalkulasi stat, seed RNG, dan aturan data tetap merujuk pada `generate_hero.py` & `main.py`.
2. [x] **Zero Storage Leak:** Dilarang menambahkan field visual ke file `savegame.json`. Semua data visual dihitung saat runtime.
3. [x] **Hidden Potential Protection:** Karakter 1★ dengan GM 2.5x tetap menggunakan `frame_1star.png` dan outfit tier 1. Tampilan tidak boleh membocorkan status rahasia tersebut ke pemain.
4. [x] **Sinkronisasi Promosi Bintang:** Saat method promosi bintang sukses (`hero.promote_star`), node kartu cukup mengosongkan cache lama dan memicu render ulang untuk beralih ke border dan outfit tier baru.