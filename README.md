# PICK ME UP: INFINITE GACHA — Auto-Battle Strategy RPG (CLI)

Game CLI bertema manhwa *Pick Me Up (Infinite Gacha)*. Python 3 stdlib ONLY
(tidak ada dependency eksternal). Versi game saat ini: **2.3.0**.

Dokumen ini adalah peta lengkap sistem game untuk developer berikutnya:
semua mekanik, angka, struktur data, keputusan desain, dan **aturan yang
tidak boleh dilanggar**.

---

## 1. Cara Menjalankan

```bash
cd /home/dhikskuy/game/pickmeup
python3 main.py
```

- Database `game_database.db` dibuat & di-seed otomatis saat pertama kali
  jalan (idempotent — aman dijalankan berulang).
- Login/daftar akun → semua progres tersimpan **per-akun** di `saves/`.
- Exit bersih: pilih Exit di lobby atau Ctrl+C (auto-save).

### Environment variable (untuk testing & konfigurasi)

| Variabel | Fungsi | Default |
|---|---|---|
| `PMU_DB_PATH` | override lokasi database SQLite | `<dir game>/game_database.db` |
| `PMU_SAVES_DIR` | override folder savegame per-akun | `<dir game>/saves/` |
| `PMU_SAVE_PATH` | override lokasi save lama single-file | `<dir game>/savegame.json` |
| `PMU_DELAY` | jeda battle antar aksi (detik) | `0.5` |

**WAJIB untuk pengujian:** set ketiga `PMU_*` ke path/folder sementara
SEBELUM mengimpor modul, agar data produksi (akun & savegame pemain)
tidak tersentuh. Lihat seksi "Testing".

---

## 2. Struktur File

```
pickmeup/
├── main.py              # Game loop, UI, BattleEngine, SaveSystem (v2.3.0)
├── database_setup.py    # Inisialisasi & pembacaan game_database.db (SQLite)
├── generate_hero.py     # Hero, Equipment, Perk, HeroGenerator, GachaSystem
├── game_database.db     # Database SQLite (jangan diedit manual)
├── game_database.db.bak # Backup otomatis (dibuat saat boot & setup)
├── savegame.json        # (legacy) save lama single-file; dimigrasi ke akun
├── savegame.json.migrated  # arsip save lama setelah dimigrasi
└── saves/               # savegame per-akun: saves/<username>.json
```

Alur dependensi satu arah (jangan dibuat melingkar):

```
database_setup.py  →  generate_hero.py  →  main.py
(SQLite + seed)      (Hero/Gacha/Equip)    (UI + battle + save)
```

---

## 3. Arsitektur: Dua Lapisan Data

Ini konsep TERPENTING untuk dipahami sebelum menyentuh kode:

| Lapisan | Isi | Lokasi | Saat update versi |
|---|---|---|---|
| **Master data** | nama hero (31.104 kombinasi), 48 traits (tabel `perks`), 240 skills (180 class + 60 universal), 48 item master, konstanta stat & bobot 6 class, pita probabilitas star 1–7, konstanta `SYNTHESIS_CONFIG` | tabel SQLite & konstanta seed | dikosongkan & **di-seed ulang otomatis** dari konstanta di `database_setup.py` — selalu kembali lengkap |
| **Data pemain** | inventory, equipment, Tas Battle, roster hero (termasuk `sanity`, `ego`, `synth_count`, `absorbed_souls`), coins/gems, progres tower, `total_synthesized`, pengaturan | `saves/<username>.json` | **tidak pernah disentuh** patcher |
| **Akun** | username, hash password, salt | tabel `accounts` SQLite | tidak pernah disentuh `force` |

Konsekuensinya: menambah item/nama/perk baru di versi berikutnya cukup
tambahkan ke konstanta seed di `database_setup.py` → `init_db(force=True)`
akan mengisi ulang tabel tanpa menyentuh akun & savegame.

---

## 4. Login & Sistem Akun

- Splash screen (ASCII + versi) → menu Login/Daftar.
- Password **tidak pernah disimpan plaintext**: `SHA-256(salt + ":" + password)`
  dengan salt acak per akun (`secrets.token_hex(8)`).
- Validasi: username min 3 karakter, password min 4.
- Satu akun = satu savegame (`saves/<username>.json`). Akun berbeda tidak
  saling mempengaruhi.
- **Migrasi save lama**: bila `savegame.json` single-file (versi < 2.2)
  ada, akun yang login PERTAMA kali ditawarkan memindahkan seluruh isinya
  (`y/n`). Setelah pindah, file lama di-rename `savegame.json.migrated`
  agar tidak ditawarkan lagi ke akun lain.
- Saat boot, `Game.__init__` menjalankan `dbs.backup_db()` → salinan
  `game_database.db.bak` sebagai jaring pengaman.

### API akun (database_setup.py)

```python
dbs.create_account(username, password)  # -> (ok, pesan)
dbs.verify_account(username, password)  # -> (ok, pesan), update last_login
dbs.account_exists(username)
dbs.backup_db()                         # salin db ke .bak (best-effort)
```

---

## 5. Gacha & Generator Hero (generate_hero.py)

- **Rate (RAHASIA — tidak ditampilkan ke pemain):** 1★ 84,9% · 2★ 10% ·
  3★ 4% · 4★ 1% · 5★ 0,1%. Diimplementasi `weighted_choice` bobot
  `(1,849),(2,100),(3,40),(4,10),(5,1)` per 1000 — akurat untuk 0,1%.
- **Mage langka ~3% dari total roll**: bobot class di tabel `class_stats`
  (Mage = 3, class lain = 20). Di-roll TERPISAH dari star agar 3%-nya global.
- **Hidden Potential (RAHASIA)**: hanya hero 1★, peluang 7% mendapat
  growth multiplier (GM) 1,5–2,5x + peluang perk Rare/Legendary ekstra,
  serta lonjakan `ego` internal sangat tinggi (`80.0–98.0`).
  Canon: 1★ bisa melampaui 4★/5★ — **star awal bukan batas kekuatan**.
- **Anti-duplikat ketat**: roster di-key by NAMA, jadi (a) nama wajib unik
  (`gen.names`), (b) fingerprint `(nama, base_tuple, growth_tuple, traits, skills)` wajib unik
  (`gen.fingerprints`). 200 percobaan lalu fallback suffix serial `[N]`.
  `gen.register_existing(roster)` dipanggil saat load — JANGAN lewatkan,
  kalau tidak, hero hasil gacha bisa menimpa hero lama.
- **Keunikan Penuh Per Hero (Traits, Skills Class + Universal, & Stat Random)**:
  - **Traits per hero (dahulu Perks)**: 1–3 acak (HARD CAP 3 di semua jalur, termasuk bonus 5★/hidden) dari pool **48 Traits** di tabel `perks` (`TRAITS`).
    Tier trait: Common 60 / Rare 30 / Epic 9 / Legendary 1 (maks 1 Legendary
    per hero). **RAHASIA: tier trait tidak pernah ditampilkan di UI pemain.**
  - **Skills per hero (240 Total Pool = 180 Class + 60 Universal)**:
    - **Pool Class**: 30 skill khusus untuk masing-masing dari 6 class (`Tanker`, `Dealer`, `Archer`, `Healer`, `Buffer`, `Mage` = `30 × 6 = 180` skill). Skill `Taunt` (dan seluruh variasi provokasi/aggro) **HANYA** ada di pool `Tanker` dan tidak pernah masuk Universal.
    - **Pool Universal**: 60 skill universal yang bisa dipelajari class apa pun (tanpa `Taunt`).
    - **Roll per hero**: tiap hero mendapat **1–2 skill sesuai class-nya** + **0–3 skill Universal** tergantung keberuntungan (dan tier Common 60 / Rare 30 / Epic 9 / Legendary 1). **RAHASIA: tier skill tidak pernah ditampilkan di UI pemain.**
  - **Stat Dasar (`base_stats`) & Rise Rate (`growth_stats`) Random per hero**:
    - **Base Stat (`base_stats`)**:
      - Batas **minimum** tiap stat berbeda-beda per class (`STAT_BASE_MIN_BY_CLASS`), sedangkan batas **maksimum** tiap stat **SAMA** untuk semua class dan semua star (`STAT_BASE_MAX`):

| Class | HP (Min – Max) | ATK (Min – Max) | DEF (Min – Max) | SPD (Min – Max) | MP (Min – Max) |
|---|---|---|---|---|---|
| **Tanker** | `150.0 – 260.0` | `9.0 – 32.0` | `13.0 – 24.0` | `7.0 – 18.0` | `25.0 – 90.0` |
| **Dealer** | `110.0 – 260.0` | `15.0 – 32.0` | `7.0 – 24.0` | `10.0 – 18.0` | `20.0 – 90.0` |
| **Archer** | `95.0 – 260.0` | `14.0 – 32.0` | `5.0 – 24.0` | `12.0 – 18.0` | `22.0 – 90.0` |
| **Healer** | `105.0 – 260.0` | `8.0 – 32.0` | `7.0 – 24.0` | `9.0 – 18.0` | `45.0 – 90.0` |
| **Buffer** | `115.0 – 260.0` | `9.0 – 32.0` | `8.0 – 24.0` | `11.0 – 18.0` | `40.0 – 90.0` |
| **Mage** | `85.0 – 260.0` | `17.0 – 32.0` | `4.0 – 24.0` | `8.0 – 18.0` | `50.0 – 90.0` |

      - Distribusi peluang miring (*skewed* 5 pita `STAT_BANDS` berukuran `20%` per pita + kurva pangkat `u ** 1.25` di dalam pita): **makin tinggi nilai stat, makin kecil persentase peluangnya**.
      - Makin tinggi star grade (`STAR_STAT_BAND_WEIGHTS`), makin besar persentase peluang mendapat stat tinggi/sangat tinggi.
    - **Rise Rate Stat per Level (`growth_stats`)**:
      - Batas **minimum dan maksimum** rise rate tiap naik level **SAMA** untuk semua star dan semua class (`STAT_GROWTH_RANGE`: HP `+8.0..26.0`, ATK `+0.8..3.0`, DEF `+0.5..1.6`, SPD `+0.15..0.45`, MP `+1.5..6.0`).
      - Yang berbeda antar star **HANYA persentase peluang** mendapat rise rate bagus (`STAR_GROWTH_BAND_WEIGHTS`). Hero 1★ tetap bisa mendapat rise rate maksimum, namun persentasenya sangat kecil (`0.8%` masuk pita 80–100%, dan `~0.10%` menyentuh puncak maksimum):

| Star | Pita 1 (0–20%) | Pita 2 (20–40%) | Pita 3 (40–60%) | Pita 4 (60–80%) | Pita 5 / Puncak (80–100%) |
|---|---|---|---|---|---|
| **1★** | `58.0%` | `26.0%` | `11.0%` | `4.2%` | `0.8%` |
| **2★** | `48.0%` | `27.5%` | `15.0%` | `7.5%` | `2.0%` |
| **3★** | `39.0%` | `27.0%` | `19.0%` | `11.0%` | `4.0%` |
| **4★** | `31.0%` | `25.5%` | `21.5%` | `15.0%` | `7.0%` |
| **5★** | `25.0%` | `23.0%` | `21.0%` | `18.5%` | `12.5%` |
| **6★** | `22.5%` | `21.5%` | `20.5%` | `19.0%` | `16.5%` |
| **7★** | `21.2%` | `20.6%` | `20.0%` | `19.4%` | `18.8%` |

    - Formula stat per level:

```
stat = base_hero[idx] + growth_hero[idx] * (level-1) * GM_efektif
GM_efektif = GM + 0.3 (Chosen One) + 0.5 (Late Bloomer pada level >= 30)
```

- XP: `xp_needed = round(40 * level^1.5)`, carry-over, MAX_LEVEL 99.
- Rate & harga **tidak ditampilkan di UI** (rahasia). Jangan pernah
  menambahkan print persentase di menu.

---

## 6. Adventure (Sesi, Tanpa Depth)

- Level musuh mengikuti **level rata-rata party**. Tidak ada depth.
- **Tabel encounter (RAHASIA — persentase tidak pernah ditampilkan):**

| Jenis | Persen (internal) | Bentuk | Level |
|---|---|---|---|
| HIDDEN BOSS | 5% | 1 boss tunggal | party +1 |
| HIGH LEVEL MONSTER | 10% | acak 1–3 | party +2..+4 |
| MONSTER STANDAR | 50% | acak 1–3 | party |
| MONSTER LEMAH | 35% | acak 1–3 | party −1..−3 |

- **Banyak monster ACAK 1–3** untuk semua jenis (kecuali Hidden Boss yang
  selalu 1 unit — esensi boss tunggal). Jangan kembali ke angka pasti.
- Sesi: menu encounter → `1. Lawan / 2. Cari lawan lain / 3. Kabur`.
  **Setelah MENANG, tetap di adventure** (reward → encounter berikutnya).
  Sesi berakhir hanya jika: Kabur dipilih, atau seluruh party tumbang.
- Reward menang: XP `36 x level musuh`, coins `35 x level`, pulih `sanity +5.0` (clamp `100.0`) untuk tiap hero hidup di party, drop Potion
  30% (maks stack 5), drop Equipment 8% → masuk equip_bag.
- Mengalahkan Hidden Boss Adventure: +1 Gem.

---

## 7. Floor Climbing / Tower (NO ESCAPE)

- Level musuh lantai biasa = `2 x floor` (F2 → L4, F3 → L6).
- **Boss floor tiap kelipatan 5**: **boss = `3 x floor`** + 2 minion =
  `2 x floor` (permintaan user: boss lebih menakutkan). Contoh: F5 →
  boss L15 + 2 minion L10; F10 → boss L30 + 2 minion L20; F80 → boss
  L240 + 2 minion L160. Header lantai menampilkan level boss.
- Catatan balance: modifier boss (HP ×2.4, ATK ×1.35) di atas level 3F
  membuat boss floor jauh lebih keras dari lantai biasa.
- **NO ESCAPE absolut** — `BattleEngine(can_escape=False)`, battle wajib
  berakhir Victory atau Total Party Permadeath (draw ronde 50 = kalah).
- Lantai clear bisa diulang (farm) tanpa batas.
- Menu Tower: 1. Lantai berikutnya, 2. Ulangi lantai, 3. Promosi bintang,
  4. Craft Material, 5. Synthesis Chamber.

### Reward Tower

- Coins `35 x (2F)`, XP `36 x (2F)`, dan pulih `sanity +5.0` (clamp `100.0`) per hero hidup (berbasis floor, bukan
  level boss).
- Gem dijamin di floor kelipatan 5; 12% floor lainnya.
- Equipment: F%10 → 100% epic (tier 3–5); F%5 → 55% rare (tier 3–4);
  F%10 → +1 Core.
- **Raw Boss Material (boss floor kelipatan 5, drop 5% MURNI — tanpa
  jaminan, permintaan eksplisit user):**

| Floor | Raw material |
|---|---|
| 5–9 | Stone Vessel |
| 10–19 | Spirit Ore |
| 20–39 | Runic Core |
| 40+ | Ectoplasm Crystal |

- **Book of Oath / Book of Fate (END-GAME):** HANYA drop dari Boss Floor
  80+ (0,5% / 1%) dan Hidden Boss tingkat tinggi — party rata-rata L60+
  (0,5% / 1%). **Tidak dapat di-craft.** Jangan pindah ke resep craft.

---

## 8. Star Promotion (1★ → 7★, Skema Soul & Essence)

- Material per tier (`PROMO_TABLE` di database_setup.py):

| Naik ke | Material (jumlah) | Coins | Success | Pity |
|---|---|---|---|---|
| 2★ | Low Soulstone (1) | 1.000 | 100% | — |
| 3★ | Intermediate Soulstone (2) | 5.000 | 100% | — |
| 4★ | High Soulstone (3) | 20.000 | 85% | +5%/gagal, cap 95% |
| 5★ | Perfect Soul Essence (3) | 75.000 | 55% | idem |
| 6★ | Book of Oath (2) | 300.000 | 30% | idem |
| 7★ | Book of Fate (2) | 1.500.000 | 12% | idem |

- **Cek kecukupan material & coins WAJIB sebelum star naik** (sudah ada —
  jangan hapus). Material & sacrifice hilang saat GAGAL, coins −50%.
- Sacrifice hero (tier ≥4): jumlah = target − 3 (4★→1, ..., 7★→4).
  Hero yang diorban HILANG PERMANEN (roster.pop + drop_hero_cache).
- Saat promosi sukses, `hero.promote_star(target)` dipanggil untuk menaikkan bintang sekaligus me-reroll/meningkatkan `base_stats` dan `growth_stats` mengikuti distribusi persentase star baru (tetap dibatasi maksimum universal `STAT_BASE_MAX` & `STAT_GROWTH_RANGE`), serta me-reset `hero.synth_count = 0` agar hero mendapat ruang kapasitas vessel baru di bintang yang lebih tinggi.
- Akses dari 2 tempat: Tower menu 3 (pilih hero dari daftar) dan
  Detail Hero → "3. Promote Star" (hero langsung ditentukan, target =
  star+1). Satu fungsi: `promotion_menu(hero=None)`.

### Hero Synthesis Chamber

Fitur penyatuan jiwa terinspirasi manhwa *Pick Me Up: Infinite Gacha* — menggabungkan **Hero Wadah (Base)** dengan **Hero Tumbal (Material)** secara permanen. Dapat diakses dari 2 tempat: **Tower → 5. Synthesis Chamber** (`synthesis_menu()`) dan **Detail Hero → 4. Synthesize Hero** (`synthesis_menu(hero=h)`).

- **Konstanta Master (`SYNTHESIS_CONFIG` di `database_setup.py`)**:
  - `VESSEL_CAP_BY_STAR`: `{1: 3, 2: 5, 3: 7, 4: 10, 5: 14, 6: 18, 7: 25}` — batas aman jumlah sintesis per bintang wadah.
  - `STAT_ABSORB_RATE_BY_STAR`: `{1: 0.25, 2: 0.32, 3: 0.40, 4: 0.50, 5: 0.60, 6: 0.72, 7: 0.85}` — rasio dasar penyerapan `base_stats` & `growth_stats` dari bintang hero tumbal.
  - `SANITY_DRAIN_BASE`: `8.0` — beban pengurangan sanity dasar per bintang hero tumbal.
  - `EGO_OVERRIDE_RATIO`: `1.6` — ambang rasio `ego_tumbal / ego_wadah` pemicu *Reverse Absorption / Ego Override*.
- **Atribut Jiwa & Vessel pada `Hero` (`generate_hero.py`)**:
  - `sanity` (`float`, `0.0–100.0`, default `100.0`): kondisi mental hero; ditampilkan deskriptif di UI melalui `mental_status_label()` (`Stabil` ≥ 80, `Gelisah` 40–79, `Retak / Kritis` < 40).
  - `ego` (`float`, `10.0–100.0`, default migrasi `50.0`): kekuatan ego jiwa (**RAHASIA**, dihitung di `HeroGenerator._roll_ego` dari bintang awal + jumlah/tier internal traits, dan melonjak ke `80.0–98.0` pada hero 1★ dengan Hidden Potential).
  - `synth_count` (`int`, default `0`): jumlah sintesis pada bintang saat ini (direset ke `0` saat `promote_star`).
  - `absorbed_souls` (`int`, default `0`): total akumulasi tumbal yang pernah diserap.
- **Alur Logika Inti (`Hero.synthesize_with(material_hero, rng=None)`)**:
  1. **Ego Override / Reverse Absorption (Kasus Han Islat)**: bila `material.ego >= base.ego * EGO_OVERRIDE_RATIO`, terdapat peluang internal (berbasis selisih ego, cap 85%) tumbal membalikkan rantai *Synthesis Chamber* dan menelan tubuh wadah (`survivor = material`, `deceased = base`). Bila `base` tadinya berada di `Party`, posisi party otomatis ditempati oleh `survivor`.
  2. **Kapasitas Wadah & Soul Overload**: bila `survivor.synth_count >= VESSEL_CAP_BY_STAR[survivor.star]`, terjadi *Soul Overload* — rasio serapan stat dipotong 85% (`×0.15`) dan pengurangan `sanity` dikalikan `2.0`.
  3. **Transfer XP**: menyerap 40%–60% dari akumulasi XP/level tumbal menggunakan `gain_xp()` standar (hingga `MAX_LEVEL = 99`).
  4. **Penyerapan Stat & `GM` Rahasia**: menyerap proporsi `base_stats` dan `growth_stats` sesuai `STAT_ABSORB_RATE_BY_STAR[deceased.star]` (dengan *diminishing returns* `0.5 ** (survivor.star - deceased.star)` bila bintang tumbal lebih rendah), lalu wajib diklem dengan `clamp_stats()`. Bila `deceased.growth_multiplier > survivor.growth_multiplier`, sebagian selisihnya (25%–35%) terserap diam-diam (cap `2.5`).
  5. **Pewarisan Skill & Trait**: mewariskan maks 1–2 skill kandidat via `can_inherit_skill()` (total maks 6 skill; skill `taunt` **terkunci ketat** hanya untuk class `Tanker`) dan maks 1 trait kandidat via `try_inherit_trait()` (**HARD CAP 3 Traits** & maks 1 Legendary).
  6. **Beban Sanity & Pembersihan Tumbal**: mengurangi `sanity` sebesar `SANITY_DRAIN_BASE * star_tumbal * (ego_tumbal / ego_survivor)` (`×2.0` bila overload). Hero yang gugur (`deceased`) dibersihkan lewat `Game.sacrifice_hero_cleanup(deceased.name, salvage_equip=True)` sehingga seluruh equipment kembali ke `equip_bag` (`slot = None`, tanpa `.pop()`), keluar dari `Party`, serta terhapus dari `roster` dan `_hero_cache`.

### Crafting (CRAFT_RECIPES)

- **SEMUA resep seragam 5 raw → 1 Soulstone** (permintaan eksplisit user):

| Raw (5x) | Craft menjadi |
|---|---|
| Stone Vessel | Low Soulstone |
| Spirit Ore | Intermediate Soulstone |
| Runic Core | High Soulstone |
| Ectoplasm Crystal | Perfect Soul Essence |

- Craft bisa diakses dari: menu Tower (4) dan Inventory (pilih raw
  material → opsi 4. Craft Material). Mendukung craft berulang.
- **Material promosi TIDAK DIJUAL di Shop** — hanya drop + craft
  (permintaan eksplisit user). Jangan tambahkan soulstone/book ke shop.

---

## 9. Tas Battle (Item Bawaan, AI-Otomatis)

- **Kapasitas = 2 × jumlah hero di party** (1 hero → 2 item, maks 5 hero
  → 10 item). Method `battle_capacity()`.
- Dikelola lewat Inventory → `T` (Kelola Tas Battle): bawa item dari
  inventory (stok inventory terpotong), kembalikan item (stok kembali).
- Tersimpan per-akun: `state["battle_bag"]` = list nama item.
- **Item yang dibawa dipakai OTOMATIS oleh AI hero** — pemain tidak pernah
  memakai item manual. Logika di `BattleEngine._try_use_battle_item(h)`,
  dipanggil di awal `hero_act` sebelum aksi class (giliran terpakai bila
  item terpakai):

| Item | Syarat AI memakai |
|---|---|
| Potion HP | ada ally HP < 40% → target paling kritis (heal 50% max HP) |
| Mana Philter | MP pemakai < 30% max → MP penuh |
| Attack Elixir | ronde ≥ 2 & belum ada buff ATK party → ATK +30% 3 ronde |
| Guard Elixir | ronde ≥ 2 & belum ada buff DEF party → DEF +30% 3 ronde |
| Revive Feather | TIDAK lewat jalur ini — otomatis "detik terakhir" di `apply_damage_to_hero` saat hero akan mati (bangkit 40% HP) |

- **KRITIS**: `BattleEngine` memegang **referensi langsung** ke list tas
  pemain (`battle_items=self.battle_bag()` — TANPA copy). Item terpakai
  hilang dari tas & savegame. Jangan pernah mengganti dengan `list(...)`
  copy — pemain akan kehilangan item yang tidak pernah terpakai, atau
  sebaliknya item tak pernah berkurang.
- Tas dibawa ke SEMUA battle: Adventure, Tower, Hidden Boss.

---

## 10. Lobby & Auto-Heal (HP + MP)

- Menu utama bernama **LOBBY** (bukan "Menu Utama").
- **Auto-restore**: setiap kali masuk/kembali ke Lobby, SEMUA hero hidup
  pulih penuh — **HP penuh DAN MP/mana penuh** (`auto_heal_lobby()`:
  `h.refresh()` + `h.mana = h.max_mp`). Saat masuk battle berikutnya
  hero sudah membawa MP maksimal (permintaan user: mana TIDAK direset 0
  lagi). Notifikasi `[Lobby] N hero ter-restore penuh (HP & MP)` hanya
  tampil bila ada yang perlu di-restore.
  Tidak ada menu Heal/Rest — fitur itu SUDAH DIHAPUS (jangan dibuat ulang).
- Di dalam battle: skill tetap menghabiskan mana & regen per ronde
  (3–8/ronde per class) tetap berjalan — restore penuh hanya di Lobby.
- Tampilan Lobby: coins/gems/hero hidup/floor tertinggi, party N/5, status
  Tas Battle, menu 1–9.
- **Party maks 5 hero** (`PARTY_MAX = 5`, ditegakkan di `Party.add`).

---

## 11. Battle Engine (Auto-Battle)

- Ronde: semua unit hidup beraksi 1x, **urut SPD menurun** (tie: party
  dulu, lalu urutan masuk). `ROUND_CAP = 50` — draw dihitung KALAH.
- **Damage = max(1, ATK_total − DEF_total)** dikali variance (1 − k),
  k ~ U(0,05; 0,10) — serangan selalu sedikit lemah dari nilai mentah.
- **AI berbasis skill unik hero (`use_hero_skill`)** (fallback basic attack jika MP kurang / cooldown) — mendukung seluruh 240 skill secara dinamis berdasarkan `kind`:
  - Prioritas 1 (Heal): `mass_heal` (≥2 ally HP < 60%) → `heal` (1 ally HP < 60% paling kritis)
  - Prioritas 2 (Tank): `taunt` (khusus pool class `Tanker`, paksa aggro musuh 2 ronde & buff DEF)
  - Prioritas 3 (Buff Party): `buff_all` (buff ATK + DEF + SPD party) → `buff_atk` (buff ATK party) → `buff_def` (buff DEF party)
  - Prioritas 4 (Ofensif / AoE / CC): dipilih skor dampak tertinggi dari `aoe_cc` (AoE + stun/slow), `aoe` (serangan seluruh musuh), `stun_hit` (single-target + peluang stun), `drain` (serangan + lifesteal HP), `pierce` (serangan abaikan DEF), dan `single` (burst single-target). Trait `Double Cast` (20%) & `Infinite Mana` (+15%) memberi peluang pakai skill tanpa menguras MP; Trait `Overcharge` memperkuat damage skill +30% saat MP > 70%.
- **Ketidakstabilan Mental (`sanity < 40.0` di `BattleEngine.hero_act`)**: sebelum aksi normal, terdapat peluang `20%` hero mengalami *Mental Instability*:
  - **50% *Soul Berserk***: menerjang musuh acak dengan serangan fisik brutal (`ATK × 1.35`, mengabaikan 50% DEF musuh).
  - **50% *Memory Echo***: mengeksekusi salah satu skill ofensif milik hero tanpa menguras MP (`mana`); fallback ke *Soul Berserk* bila tidak memiliki skill ofensif.
  - Menyelesaikan kemenangan di Adventure maupun Tower memulihkan `sanity +5.0` (clamp `100.0`) bagi seluruh hero hidup di party (`recover_party_sanity`).
- **AI musuh**: serang Tanker yang sedang Taunt dulu, selain itu random.
  Caster: 50% splash 50% dmg ke hero acak lain.
- **Permadeath**: HP hero 0 = mati PERMANEN. Urutan penyelamat:
  Revive Feather (tas) → perk Last Stand (1 HP, ATK+30) → perk Phoenix
  (revive 50%). Tanpa semuanya: mati, SEMUA EQUIPMENT HANCUR, hero
  dikeluarkan dari roster & party (`cleanup_after_battle`).
- **Kabur**: HANYA menu encounter Adventure SEBELUM memilih Lawan.
  `can_escape=False` untuk semua battle (Tower/Hidden Boss memang tanpa
  kabur; Adventure kini eksplisit lewat menu encounter). TIDAK ADA prompt
  kabur di dalam battle — jangan tambahkan lagi.
- **Pengaturan cepat** (menu Lobby 9): "Battle Tanpa Delay Antar Aksi"
  tersimpan per-akun (`settings.no_action_delay`). Saat aktif:
  jeda antar aksi unit = 0 (`action_delay()`), **jeda ganti ronde tetap
  0,5s**. Implementasi global: `BATTLE_FAST` + `action_delay()`.

---

## 12. Save System & Migrasi (BACA SEBELUM MENGUBAH)

- Save per-akun: `saves/<username>.json`, versi `"game_version": "2.3.0"`.
- **Migrasi otomatis** (`SaveSystem.load`):
  1. File korup → coba `.bak` → kalau gagal, state default (TIDAK crash).
  2. `deep_merge(default_state, data_lama)` — key baru otomatis dapat
     fallback (`equip_bag`, `battle_bag`, `settings`, `total_synthesized`, dll).
  3. `ensure_hero_fields(hd)` per hero — field baru diisi default (termasuk `sanity: 100.0`, `ego: 50.0`, `synth_count: 0`, `absorbed_souls: 0`),
     tipe salah dinormalisasi (mis. star "3" → 3).
  4. Migrasi spesifik: `StarFragment` (material lama) → `Low Soulstone`
     konversi 1:1.
  5. `state["game_version"]` dinaikkan segera setelah load.
- **Aturan emas: data pemain tidak pernah hilang saat update.** Menambah
  field baru = tambah di `default_state()` + (bila perlu) logika migrasi.
  JANGAN PERNAH menghapus savegame pemain di kode.
- **Hero cache (identity map)**: `Game._hero_cache` — `roster()` mengembali-
  kan objek yang sama selama sesi. Mutasi objek (XP, luka, level, equipment,
  star) ter-serialisasi saat `autosave()`. Hero mati/diorban wajib
  `drop_hero_cache(nama)`. **JANGAN kembali ke pola "re-parse dict tiap
  akses"** — bug lama: perubahan tidak pernah tersimpan.
- `autosave()` dipanggil setelah battle, gacha, transaksi shop, perubahan
  party/equipment, toggle settings.

---

## 13. Database (database_setup.py)

Tabel: `hero_names` (31.104 baris), `perks` (48 traits), `skills` (240 skills = 180 class + 60 universal), `items_master` (48),
`class_stats` (6), `star_mults` (7), `accounts`, `meta`.

- **Seeding idempotent**: `INSERT OR IGNORE` + PRIMARY KEY/UNIQUE teks.
  PELAJARAN PENTING: SQLite `UNIQUE` memperlakukan NULL sebagai berbeda
  per baris — kolom unique nullable WAJIB disimpan `''` (string kosong),
  bukan NULL. (Bug historis: duplikasi 31.104 → 32.256.)
- **`init_db(force=True)` TIDAK PERNAH menghapus file database** — hanya
  DELETE isi tabel data game lalu re-seed. Tabel `accounts` tidak disentuh.
  Menghapus akun butuh flag eksplisit `wipe_accounts=True` (atau CLI
  `--wipe-accounts`) — DESTRUKTIF, dipisah agar tak salah flag.
- `get_db(timeout=5.0)`; `init_db` menutup koneksi segera agar lock lepas.
- `backup_db()` memakai `shutil.copyfile` + guard SameFile — BUKAN
  `sqlite3.backup()` (versi lama deadlock saat backup diri-sendiri).
- DB_PATH bisa dioverride env `PMU_DB_PATH` (isolasi testing).

---

## 14. Hal yang TIDAK DIPERBOLEHKAN (keputusan desain user)

Daftar ini adalah permintaan eksplisit user — melanggarnya = regresi:

1. **Jangan menampilkan persentase gacha** (rate bintang, Mage ~3%) di UI.
2. **Jangan menampilkan persentase encounter Adventure** (5/10/50/35) di UI.
3. **Jangan menampilkan Hidden Potential** (label tier, angka GM, marker
   hasil gacha). Mekaniknya bekerja diam-diam; pemain tidak boleh tahu
   hero mana yang istimewa.
3b. **Jangan menampilkan tier dari Traits maupun Skills** (Common/Rare/Epic/Legendary), persentase peluang sintesis, maupun nilai **`ego`** di UI pemain — seluruhnya bersifat rahasia dan hanya untuk kalkulasi internal (roll & Hero Synthesis).
4. **Jangan menghapus progres pemain saat update** — tidak boleh ada kode
   yang menghapus savegame/akun otomatis; migrasi harus selalu additive.
5. **Jangan menjamin drop raw boss material** (harus 5% murni).
6. **Jangan menjual material promosi** (soulstone/book) di Shop.
7. **Jangan mengubah resep craft** dari 5 raw → 1 Soulstone.
8. **Jangan menambah opsi kabur di dalam battle** (kabur hanya menu
   encounter Adventure sebelum Lawan).
9. **Jangan membuat ulang menu Heal/Rest** (sudah diganti auto-heal Lobby).
10. **Jangan menampilkan prompt kabur tiap ronde.**
11. **Jangan membuat jumlah monster Adventure pasti** (harus acak 1–3;
    Hidden Boss tetap 1 unit).
11b. **Jangan ubah formula level Tower**: biasa 2×floor; boss floor =
    boss 3×floor + 2 minion 2×floor.
12. **Jangan pakai deepcopy/list() pada battle_bag** yang dipindahkan ke
    BattleEngine (harus referensi langsung).
13. **Jangan menaruh stat master di savegame** atau data pemain di database
    — ikuti pemisahan dua lapisan (seksi 3).
14. **Jangan mengubah batas party** dari 5 hero, kapasitas tas battle dari
    2×hero, atau perk cap dari 3.

---

## 15. Testing (WAJIB ikuti pola ini)

Skrip tes harus **mengisolasi seluruh data** lewat env var SEBELUM import:

```python
import os, tempfile
TEST_DIR = tempfile.mkdtemp(prefix="pmu_test_")
os.environ["PMU_DB_PATH"]    = os.path.join(TEST_DIR, "test.db")
os.environ["PMU_SAVES_DIR"]  = os.path.join(TEST_DIR, "saves")
os.environ["PMU_SAVE_PATH"]  = os.path.join(TEST_DIR, "s.json")
os.environ["PMU_DELAY"]      = "0"
sys.path.insert(0, "/home/dhikskuy/game/pickmeup")
import database_setup as dbs
import main as M
```

- `init_db(force=True)` di lingkungan tes AMAN (hanya re-seed data game;
  akun di DB tes ikut hilang tidak masalah — itu DB sementara).
- **Pelajaran darurat**: skrip tes yang dulu memanggil `init_db(force=True)`
  tanpa isolasi MENGHAPUS database produksi (akun pemain hilang). Kini
  force aman, tapi tetap biasakan isolasi.
- Game dibuat via `M.Game.__new__(M.Game)` + set atribut manual untuk
  unit test tanpa login; jangan lupa `game._hero_cache = {}` dan
  `game.apply_settings()`.
- Stub input: **gunakan antrean jawaban berujung "0"** — stub yang selalu
  menjawab sama akan membuat loop menu tak pernah keluar (timeout tes).
- E2E: `subprocess.run([sys.executable, "main.py"], input=..., env=...,
  cwd=GAME_DIR)` dengan input tersimulasi. Desain input **branch-aligned**
  untuk event acak (mis. hidden boss muncul/tidak: pola "2","0","0" aman
  di dua cabang).
- Skenario wajib lulus sebelum rilis: login/persist antar-run, akun
  terpisah, migrasi save lama (termasuk StarFragment→Low Soulstone),
  fuzz input kotor (200+ baris) tanpa traceback, TTK battle > 5 ronde,
  uniqueness 400+ hero, rate gacha ±toleransi.

---

## 16. Gotchas & Pelajaran Teknis (baca, jangan diulang)

- **SQLite UNIQUE + NULL**: nullable unique column → simpan `''`, bukan
  NULL (INSERT OR IGNORE tidak menghalangi duplikat NULL).
- **Identity map untuk state**: render ulang dari dict per akses = mutasi
  objek hilang saat save (bug persistensi historis).
- **`pop()` key pada menu pemilihan slot**: key hilang dari daftar pilihan
  berikutnya. Set `None`, jangan pop. (Bug historis: slot equipment
  hilang setelah dilepas.)
- **`%%` di string tanpa formatting `%`** tampil literal `%%` di layar.
- **Backup diri-sendiri**: `backup_db(p)` mengisi dest dengan path sumber
  → SameFileError (copyfile) / deadlock (sqlite backup API). Guard +
  panggil `backup_db()` tanpa argumen.
- **f-string/`%` dgn `.center()`**: `"%s" % v.center(62)` centering dulu
  baru format — biasanya bukan yang dimaksud; bungkus: `("..." % v).center(62)`.
- **Stub test yang selalu menjawab sama** → infinite loop menu (game loop
  benar, test-nya salah). Selalu akhiri antrean dengan "0".
- **Permadeath menghabiskan party tes**: jangan kirim party baru ke konten
  sulit lalu mengklaim bug; verifikasi ladder kesulitan dulu.
- Saat menambah menu: setiap `ask_choice` yang MENAWARKAN "0" wajib
  menanganinya (`if c == "0": return`). Bug historis: input 0 memilih item
  terakhir (indeks -1) dan pemain terjebak di menu.

---

## 17. Peta Fungsi Penting (main.py)

| Fungsi/Class | Peran |
|---|---|
| `splash_screen`, `login_menu` | splash + login/register |
| `account_save_path`, `claim_legacy_save` | save per-akun + migrasi lama |
| `SaveSystem` | save/load JSON + migrasi + backup .bak |
| `deep_merge`, `ensure_hero_fields` | util migrasi |
| `Game.__init__(username)` | boot: init_db, load, hero cache, settings |
| `Game.run` | loop Lobby (auto-restore HP+MP di awal tiap iterasi) |
| `auto_heal_lobby`, `battle_capacity`, `battle_bag` | fitur Lobby |
| `gacha_menu`, `do_gacha`, `announce` | gacha (tanpa persen di UI) |
| `manage_hero_menu` → `hero_menu` → `hero_detail_menu` | Manage Hero |
| `equip_item_flow`, `unequip_flow` | pasang/lepas equipment |
| `inventory_menu` → `item_detail_flow` | Inventory + opsi T (tas) |
| `battle_bag_flow`, `_try_use_battle_item` (BattleEngine) | Tas Battle + AI |
| `adventure` | sesi adventure + tabel encounter rahasia |
| `tower_menu`, `tower_floor`, `reward_tower` | Tower NO ESCAPE (boss 3F + minion 2F) |
| `promotion_menu(hero=None)` | star promotion 1→7 |
| `synthesis_menu(hero=None)` | Hero Synthesis Chamber (Tower & Detail Hero) |
| `Hero.synthesize_with` (`generate_hero.py`) | logika inti sintesis, Ego Override, serapan stat/XP/skill/trait & sanity |
| `craft_menu` | crafting raw → soulstone |
| `shop_menu` | potion, gacha ticket, mystery box (TANPA material) |
| `post_battle_events` | Hidden Boss raid pasca-clear Tower |
| `settings_menu`, `apply_settings` | battle fast mode per-akun |
| `BattleEngine.run/run_round`, `_trigger_mental_instability` | auto-battle core + efek sanity kritis (`Soul Berserk` / `Memory Echo`) |
| `cleanup_after_battle`, `drop_hero_cache` | permadeath |
| `sacrifice_hero_cleanup`, `recover_party_sanity` | salvage equipment tumbal & hapus permanen; pemulihan sanity pasca-menang |

---

## 18. Checklist Sebelum Rilis Update

- [ ] `python3 -m py_compile database_setup.py generate_hero.py main.py`
- [ ] Item/perk/nama baru ditambahkan via seed di `database_setup.py`
      (bukan lewat edit db manual) → `init_db(force=True)` mengisi ulang.
- [ ] Key state baru ada di `default_state()` (fallback migrasi otomatis).
- [ ] Tidak ada print persentase rate/encounter/hidden potential.
- [ ] Tidak ada kode yang menghapus saves/ atau tabel accounts.
- [ ] E2E: login → persist antar-run → akun terpisah → migrasi → fuzz.
- [ ] Backup `.bak` tercipta; pemulihan dari `.bak` teruji.
- [ ] Semua aturan di seksi 14 tidak dilanggar.

---

*Dokumentasi terakhir diperbarui pada versi game 2.3.0. Simpan file ini
bersama kode; perbarui setiap mengubah mekanik.*
