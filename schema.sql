-- ============================================================
-- schema.sql — skema database Postgres baru buat ITOMS
-- Jalankan sekali di database itoms_db yang udah dibikin.
-- ============================================================

-- Tabel user gabungan (whitelist bot + login dashboard + permissions)
CREATE TABLE IF NOT EXISTS whitelist (
    user_id         BIGINT PRIMARY KEY,          -- Telegram ID utama
    nama            TEXT NOT NULL,               -- dipake juga di jadwal
    no_hp           TEXT,
    telegram_id_2   BIGINT,                      -- akun telegram kedua (opsional)
    username        TEXT UNIQUE,                 -- login dashboard
    password_hash   TEXT,                        -- login dashboard
    is_superadmin   BOOLEAN NOT NULL DEFAULT FALSE,
    permissions     JSONB NOT NULL DEFAULT '[]'::jsonb,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Hari libur — DIPINDAH dari database lama, bukan direset
CREATE TABLE IF NOT EXISTS hari_libur (
    id       SERIAL PRIMARY KEY,
    tanggal  DATE NOT NULL UNIQUE,
    nama     TEXT NOT NULL
);

-- Jadwal OC/piket — reset kosong
CREATE TABLE IF NOT EXISTS jadwal (
    id          SERIAL PRIMARY KEY,
    nama        TEXT NOT NULL,
    tanggal     DATE NOT NULL,
    tipe        TEXT NOT NULL CHECK (tipe IN ('oc', 'piket', 'off')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (nama, tanggal, tipe)
);

-- Urutan piket — reset kosong
CREATE TABLE IF NOT EXISTS daftar_piket (
    id            SERIAL PRIMARY KEY,
    whitelist_id  BIGINT NOT NULL REFERENCES whitelist(user_id) ON DELETE CASCADE,
    urutan        INTEGER NOT NULL,
    UNIQUE (whitelist_id)
);

-- Request tanggal gak bisa (blackout) — reset kosong
CREATE TABLE IF NOT EXISTS blackout (
    id            SERIAL PRIMARY KEY,
    whitelist_id  BIGINT NOT NULL REFERENCES whitelist(user_id) ON DELETE CASCADE,
    tanggal       DATE NOT NULL,
    keterangan    TEXT,
    dibuat_oleh   BIGINT REFERENCES whitelist(user_id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (whitelist_id, tanggal)
);

-- State rolling generate jadwal — reset kosong
CREATE TABLE IF NOT EXISTS rolling_state (
    tipe               TEXT PRIMARY KEY,
    last_whitelist_id  BIGINT,
    updated_at         TIMESTAMPTZ
);

-- Komplain — DIPINDAH dari database lama, bukan direset
-- (pengirim disimpen sebagai teks nama, jadi aman dipindah walau user lama gak ada lagi)
CREATE TABLE IF NOT EXISTS komplain (
    id          SERIAL PRIMARY KEY,
    message_id  BIGINT NOT NULL,
    chat_id     BIGINT NOT NULL,
    grup_nama   TEXT,
    isi_pesan   TEXT,
    pengirim    TEXT,
    masuk_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Response komplain — DIPINDAH juga bareng komplain
CREATE TABLE IF NOT EXISTS response_komplain (
    id               SERIAL PRIMARY KEY,
    komplain_id      INTEGER REFERENCES komplain(id) ON DELETE CASCADE,
    message_id       BIGINT,
    chat_id          BIGINT,
    responder_id     BIGINT,
    responder_nama   TEXT,
    isi_balasan      TEXT,
    bales_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Task management — reset kosong
CREATE TABLE IF NOT EXISTS task (
    id           SERIAL PRIMARY KEY,
    judul        TEXT NOT NULL,
    deskripsi    TEXT,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'on_progress', 'done')),
    prioritas    TEXT NOT NULL DEFAULT 'normal' CHECK (prioritas IN ('low', 'normal', 'high')),
    deadline     DATE,
    dibuat_oleh  BIGINT REFERENCES whitelist(user_id),
    komplain_id  INTEGER REFERENCES komplain(id),
    progres      INTEGER DEFAULT 0 CHECK (progres BETWEEN 0 AND 100),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS task_assignee (
    id       SERIAL PRIMARY KEY,
    task_id  INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    user_id  BIGINT NOT NULL REFERENCES whitelist(user_id),
    UNIQUE (task_id, user_id)
);

CREATE TABLE IF NOT EXISTS task_comment (
    id          SERIAL PRIMARY KEY,
    task_id     INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    user_id     BIGINT NOT NULL REFERENCES whitelist(user_id),
    isi         TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Metadata storage (siapa upload/edit file) — reset kosong
CREATE TABLE IF NOT EXISTS file_meta (
    rel_path     TEXT PRIMARY KEY,
    uploaded_by  TEXT,
    uploaded_at  TEXT,
    edited_by    TEXT,
    edited_at    TEXT
);

-- Privasi folder storage — reset kosong (semua folder balik publik)
CREATE TABLE IF NOT EXISTS folder_perm (
    rel_path       TEXT PRIMARY KEY,
    mode           TEXT NOT NULL CHECK (mode IN ('public', 'private', 'password')),
    owner          TEXT,
    password_hash  TEXT,
    created_at     TEXT
);
