-- Migration 001: Initial Schema cho Lovira-Facebook Manager
-- Tuân thủ Đặc tả Kỹ thuật Mục 13.2 & Mục 13.3

-- 1. Tài khoản Facebook
CREATE TABLE IF NOT EXISTS facebook_accounts (
    id TEXT PRIMARY KEY,
    facebook_user_id TEXT UNIQUE,
    name TEXT NOT NULL,
    avatar_url TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    last_checked_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 2. Nhóm Page
CREATE TABLE IF NOT EXISTS page_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#3B82F6',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 3. Fanpage Facebook
CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    facebook_page_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    avatar_url TEXT,
    group_id TEXT REFERENCES page_groups(id) ON DELETE SET NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'ready',
    last_synced_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 4. Liên kết Tài khoản và Page (một Page có thể được quản lý bởi nhiều tài khoản)
CREATE TABLE IF NOT EXISTS account_page_links (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES facebook_accounts(id) ON DELETE CASCADE,
    page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    token_ref TEXT NOT NULL, -- Tham chiếu tới Secret Store, không lưu token thô
    granted_tasks TEXT, -- JSON array các quyền tác vụ: CREATE_CONTENT, MANAGE, etc.
    checked_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    UNIQUE(account_id, page_id)
);

-- 5. Tham chiếu bí mật (Secret Store Reference metadata)
CREATE TABLE IF NOT EXISTS secret_refs (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL, -- 'keyring' hoặc 'local_vault'
    keyring_service TEXT NOT NULL,
    keyring_username TEXT NOT NULL,
    encrypted_payload_ref TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 6. Kho tài nguyên Media
CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    source_platform TEXT NOT NULL, -- 'douyin', 'tiktok', 'bilibili', 'local'
    source_id TEXT,
    source_url TEXT,
    local_path TEXT NOT NULL,
    checksum TEXT NOT NULL, -- SHA-256
    duration REAL, -- giây
    width INTEGER,
    height INTEGER,
    size_bytes INTEGER NOT NULL,
    thumbnail_path TEXT,
    tags TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);
CREATE INDEX IF NOT EXISTS idx_media_assets_checksum ON media_assets(checksum);

-- 7. Tác vụ Tải Video
CREATE TABLE IF NOT EXISTS download_jobs (
    id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    source_platform TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued', -- 'queued', 'downloading', 'completed', 'failed', 'cancelled'
    progress REAL DEFAULT 0.0,
    temp_path TEXT,
    media_id TEXT REFERENCES media_assets(id) ON DELETE SET NULL,
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 8. Bài nháp (Drafts)
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    title TEXT,
    content_type TEXT NOT NULL DEFAULT 'video', -- 'text', 'photo', 'video', 'reels'
    caption TEXT,
    media_refs TEXT, -- JSON array các media_assets(id)
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 9. Ghi đè cấu hình nháp theo từng Page đích
CREATE TABLE IF NOT EXISTS draft_targets (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    caption_override TEXT,
    settings TEXT, -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    UNIQUE(draft_id, page_id)
);

-- 10. Hàng đợi Công việc Đăng bài (Publish Jobs)
CREATE TABLE IF NOT EXISTS publish_jobs (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    client_request_id TEXT NOT NULL, -- Chống đăng trùng khi người dùng bấm đúp
    page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE RESTRICT,
    content_snapshot TEXT NOT NULL, -- Bản chụp JSON độc lập với nháp gốc
    revision INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'scheduled_local',
    schedule_mode TEXT NOT NULL DEFAULT 'local', -- 'local' hoặc 'remote'
    scheduled_at_utc TEXT NOT NULL, -- ISO-8601 UTC
    timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    worker_lease_until TEXT,
    remote_scheduled_id TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error_code TEXT,
    blocked_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    UNIQUE(batch_id, page_id)
);
CREATE INDEX IF NOT EXISTS idx_publish_jobs_state_scheduled ON publish_jobs(state, scheduled_at_utc);
CREATE INDEX IF NOT EXISTS idx_publish_jobs_request ON publish_jobs(client_request_id);

-- 11. Chi tiết lần thử Đăng bài (Publish Attempts)
CREATE TABLE IF NOT EXISTS publish_attempts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES publish_jobs(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    upload_id TEXT,
    video_id TEXT,
    post_id TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    ended_at TEXT,
    outcome TEXT NOT NULL, -- 'success', 'failed_retryable', 'failed_final', 'unknown'
    error_detail TEXT
);

-- 12. Nhật ký sự kiện công việc (Job Events Audit)
CREATE TABLE IF NOT EXISTS job_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES publish_jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    redacted_detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 13. Bộ nhớ đệm bài viết Facebook (Posts Cache)
CREATE TABLE IF NOT EXISTS posts_cache (
    id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    remote_post_id TEXT NOT NULL,
    post_type TEXT,
    metadata TEXT, -- JSON
    synced_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    UNIQUE(page_id, remote_post_id)
);

-- 14. Bộ nhớ đệm bình luận (Comments Cache)
CREATE TABLE IF NOT EXISTS comments_cache (
    id TEXT PRIMARY KEY,
    page_id TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    remote_comment_id TEXT NOT NULL,
    post_id TEXT,
    metadata TEXT, -- JSON
    synced_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    UNIQUE(page_id, remote_comment_id)
);

-- 15. Mẫu phản hồi bình luận
CREATE TABLE IF NOT EXISTS reply_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    group_id TEXT REFERENCES page_groups(id) ON DELETE SET NULL,
    page_scope TEXT, -- JSON array các page_id hoặc NULL nếu áp dụng tất cả
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 16. Cài đặt cục bộ (App Settings)
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- 17. Trạng thái License Client
CREATE TABLE IF NOT EXISTS license_state (
    id INTEGER PRIMARY KEY CHECK (id = 1), -- Chỉ duy nhất 1 hàng metadata
    device_id TEXT NOT NULL,
    masked_key_hint TEXT,
    session_id TEXT,
    generation INTEGER DEFAULT 0,
    expires_at TEXT,
    config_version INTEGER DEFAULT 1,
    is_free_mode INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);
